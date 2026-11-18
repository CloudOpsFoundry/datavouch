"""Collect explicit BigQuery cohorts and assemble replayable verification inputs."""

import copy
import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from datavouch.adapters.bigquery.files import decode_config, load_fixture, render_collection
from datavouch.adapters.bigquery.models import Collection, CollectionConfig, CollectionError
from datavouch.core.configuration import MAX_INPUT_BYTES, _object, read_json
from datavouch.core.models import Execution, Observation, Status
from datavouch.verification.evaluation import verify
from datavouch.verification.windows import Windows


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def prepare(document: Any) -> tuple[CollectionConfig, CollectionConfig, dict[str, Any], bool]:
    """Validate the complete plan before any filesystem mutation or cloud request."""
    root = _object(
        document,
        {
            "schema_version",
            "id",
            "baseline",
            "candidate",
            "change",
            "policy",
            "assurance",
            "synthetic",
        },
        {"comparability"},
    )
    if root["schema_version"] != "bigquery-experiment-0.1" or type(root["synthetic"]) is not bool:
        raise ValueError("Unsupported experiment schema or synthetic flag")
    before, after = decode_config(root["baseline"]), decode_config(root["candidate"])
    if (before.project, before.location, before.workload) != (
        after.project,
        after.location,
        after.workload,
    ):
        raise ValueError("Both cohorts require the same project, location and registered workload")
    if set(before.job_ids) & set(after.job_ids):
        raise ValueError("Baseline and candidate job IDs overlap")
    change = _object(root["change"], {"id", "description", "at"})
    windows = Windows(
        before.start.isoformat(),
        before.end.isoformat(),
        change["at"],
        after.start.isoformat(),
        after.end.isoformat(),
    )
    assurance = copy.deepcopy(
        _object(root["assurance"], {"required_checks"}, {"evidence", "reliability"})
    )
    assurance.update(windows=asdict(windows), started_at={}, completed_at={})
    experiment = {
        "id": root["id"],
        "baseline": {"observations": []},
        "candidate": [],
        "change": {"id": change["id"], "description": change["description"]},
    }
    if "comparability" in root:
        experiment["comparability"] = copy.deepcopy(root["comparability"])
    assembled = {
        "comparison": {"experiment": experiment, "policy": copy.deepcopy(root["policy"])},
        "assurance": assurance,
    }
    verify(assembled)
    for label in (before.workload.id, root["id"]):
        if len(label) > 300:
            raise ValueError("Viewer labels must not exceed 300 characters")
    return before, after, assembled, root["synthetic"]


def assemble(
    template: dict[str, Any], before: Collection, after: Collection
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Never promote a partial or out-of-window collection into a passing cohort."""
    document = copy.deepcopy(template)
    assurance = document["assurance"]
    experiment = document["comparison"]["experiment"]
    scopes: dict[str, Any] = {}
    for name, collection in (("baseline", before), ("candidate", after)):
        contained = all(
            job.started_at is not None
            and job.completed_at is not None
            and collection.config.start
            <= job.started_at
            <= job.completed_at
            < collection.config.end
            for job in collection.jobs
        )
        usable = collection.reliability_eligible and contained
        scopes[name] = {
            "eligible": collection.eligible,
            "reliability_eligible": collection.reliability_eligible,
            "fully_contained": contained,
            "used": usable,
            "requested_count": len(collection.config.job_ids),
            "returned_count": len(collection.jobs),
            "reason": (
                "Complete eligible cohort"
                if collection.eligible
                else "Complete cohort includes failed executions; performance unavailable"
            )
            if usable
            else "Cohort withheld: missing, excluded, mixed-fingerprint or out-of-window jobs",
        }
        observations = []
        if usable:
            for job in collection.jobs:
                if job.started_at is None or job.completed_at is None:
                    raise ValueError("Eligible job is missing execution evidence")
                execution = job.observation or Observation(
                    collection.config.workload,
                    Execution(
                        f"{collection.config.project}/{collection.config.location}/{job.job_id}",
                        successful=False,
                    ),
                    (),
                )
                observation = asdict(execution)
                observation["measurements"] = list(observation["measurements"])
                observations.append(observation)
                key = execution.execution.id
                assurance["started_at"][key] = job.started_at.isoformat()
                assurance["completed_at"][key] = job.completed_at.isoformat()
        if name == "baseline":
            experiment["baseline"]["observations"] = observations
        else:
            experiment["candidate"] = observations
    if not all(scope["used"] for scope in scopes.values()):
        assurance.setdefault("reliability", {"complete": False})["complete"] = False
    return document, scopes


def run_command(path: Path, output_dir: Path, fixtures: list[Path] | None, live: bool) -> int:
    """Run one bounded experiment. Exit 0=PASS, 1=FAIL, 2=error, 3=UNKNOWN."""
    try:
        before, after, template, synthetic = prepare(read_json(path))
        if (live and fixtures is not None) or (
            not live and (fixtures is None or len(fixtures) != 2)
        ):
            raise ValueError("Select exactly one source")
        if live:
            now = datetime.now(UTC)
            before.validate_live_window(now)
            after.validate_live_window(now)
        # Reserve a new directory before billable calls. Never overwrite an existing experiment.
        output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
        if live:
            from datavouch.adapters.bigquery.client import collect_live

            baseline, candidate = collect_live(before), collect_live(after)
        else:
            if fixtures is None:
                raise ValueError("Fixture paths are required")
            baseline = load_fixture(fixtures[0], before)
            candidate = load_fixture(fixtures[1], after)
        document, scopes = assemble(template, baseline, candidate)
        input_json = encoded(document)
        if len(input_json.encode()) > MAX_INPUT_BYTES:
            raise ValueError("Assembled input exceeds replay input limit")
        report = verify(document)
        output = encoded(report)
        catalog = {
            "workloads": [
                {
                    "id": "workload",
                    "name": before.workload.id,
                    "description": "Selected BigQuery workload experiment",
                    "experiments": [
                        {
                            "id": "experiment",
                            "title": document["comparison"]["experiment"]["id"],
                            "recorded_at": after.end.isoformat(),
                            "kind": "verify",
                            "input": "input.json",
                            "synthetic": synthetic,
                        }
                    ],
                }
            ]
        }
        artifacts = {
            "input.json": input_json,
            "report.json": output,
            "baseline-collection.json": render_collection(baseline, include_times=True),
            "candidate-collection.json": render_collection(candidate, include_times=True),
            "collection-status.json": encoded(scopes),
            # Write the viewer entry point last. On exit 2, discard any partial output directory.
            "catalog.json": encoded(catalog),
        }
        for name, contents in artifacts.items():
            with (output_dir / name).open("x", encoding="utf-8") as destination:
                destination.write(contents)
    except CollectionError as error:
        print(str(error), file=sys.stderr)
        return 2
    except ValueError, TypeError, OSError, OverflowError, RecursionError:
        print(
            "BigQuery experiment error: check the plan, sources and a new output directory. "
            "Discard partial output on error.",
            file=sys.stderr,
        )
        return 2
    print(output, end="")
    return {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 3}[report["overall_status"]]
