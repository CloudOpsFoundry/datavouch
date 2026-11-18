"""Bounded, read-only startup snapshots of explicitly selected experiments."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from datavouch.analysis.comparison import compare
from datavouch.core.configuration import _object, decode, read_json
from datavouch.core.models import nonempty
from datavouch.financial.evaluation import assess
from datavouch.reports.json_report import render
from datavouch.verification.correctness import instant
from datavouch.verification.evaluation import verify


@dataclass(frozen=True, slots=True)
class Section:
    title: str
    rows: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class ExperimentView:
    id: str
    title: str
    recorded_at: str
    kind: str
    synthetic: bool
    status: str
    available: bool
    sections: tuple[Section, ...]
    notes: tuple[str, ...]
    digest: str
    raw: bytes

    @property
    def label(self) -> str:
        return {
            "compare": "Metric comparison",
            "verify": "Verification",
            "finance": "Financial evidence",
        }[self.kind]


@dataclass(frozen=True, slots=True)
class WorkloadView:
    id: str
    name: str
    description: str
    experiments: tuple[ExperimentView, ...]


def identifier(value: Any) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", value):
        raise ValueError("Catalog IDs must be lowercase URL-safe names of at most 64 characters")
    return value


def text(value: Any) -> str:
    nonempty(value, "catalog text")
    if len(value) > 300:
        raise ValueError("Catalog text exceeds 300 characters")
    return str(value)


def calculate(kind: str, document: Any) -> tuple[dict[str, Any], bytes]:
    """Use the same engines and serialization as CLI commands."""
    if kind == "compare":
        experiment, policy = decode(document)
        output = render(compare(experiment, policy))
        return json.loads(output), output.encode()
    report = verify(document) if kind == "verify" else assess(document)
    return report, (json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n").encode()


def value(number: Any) -> str:
    if isinstance(number, float):
        return format(number, ".6g")
    return "Unavailable" if number is None else str(number)


def sections(kind: str, report: dict[str, Any]) -> tuple[Section, ...]:
    """Allowlist display fields. Never expose source documents, references or execution IDs."""
    result = []
    if kind in ("compare", "verify"):
        performance = report if kind == "compare" else report["performance"]
        metric = performance["results"][0]
        result.append(
            Section(
                "Performance",
                (
                    ("Metric", metric["check"]),
                    ("Unit", metric["unit"]),
                    ("Baseline mean", value(metric["baseline_mean"])),
                    ("Candidate mean", value(metric["candidate_mean"])),
                    ("Regression (%)", value(metric["regression_percent"])),
                ),
            )
        )
        checks = report["results"] if kind == "compare" else report["checks"]
        result.append(
            Section(
                "Checks",
                tuple((c.get("name", c.get("check", "Check")), c["status"]) for c in checks),
            )
        )
        if kind == "verify":
            result.append(
                Section(
                    "Reliability",
                    tuple(
                        (key.replace("_", " ").capitalize(), value(v))
                        for key, v in report["reliability_metrics"].items()
                    ),
                )
            )
            result.append(
                Section(
                    "Evidence quality",
                    tuple((key, str(v)) for key, v in report["evidence_quality"].items())
                    + (("Excluded executions", str(len(report["excluded_execution_ids"]))),),
                )
            )
    else:
        result.append(
            Section(
                "Financial interpretation",
                (("Pricing model", report["pricing_model"]), ("Currency", report["currency"])),
            )
        )
        for field, label in (
            ("estimated_costs", "Estimated costs"),
            ("observed_spending", "Supplied spending"),
        ):
            evidence = report[field]
            rows = [("Classification", evidence["classification"])]
            if evidence["values"] is not None:
                rows.extend(
                    (key.replace("_", " ").capitalize(), value(v))
                    for key, v in evidence["values"].items()
                )
            result.append(Section(label, tuple(rows)))
        result.append(
            Section(
                "Attribution",
                (
                    ("Classification", report["attribution"]["classification"]),
                    (
                        "Normalized difference",
                        value(report["attribution"]["normalized_difference"]),
                    ),
                    (
                        "Eligible for aggregation",
                        "Yes" if report["eligible_for_aggregation"] else "No",
                    ),
                    ("Conflicting claims", str(len(report["overlapping_claim_ids"]))),
                    ("Registry conflicts", str(report["registry_conflict_count"])),
                ),
            )
        )
    return tuple(result)


def load_catalog(path: Path) -> tuple[WorkloadView, ...]:
    """Load at most 100 reports, 20 MB total input and 50 MB rendered output."""
    path = path.resolve(strict=True)
    root = path.parent
    manifest = _object(read_json(path), {"workloads"})
    workloads = manifest["workloads"]
    if not isinstance(workloads, list) or len(workloads) > 50:
        raise ValueError("Catalog supports at most 50 workloads")
    result = []
    workload_ids: set[str] = set()
    input_bytes = output_bytes = report_count = 0
    for item in workloads:
        data = _object(item, {"id", "name", "description", "experiments"})
        workload_id = identifier(data["id"])
        if workload_id in workload_ids:
            raise ValueError("Duplicate workload ID")
        workload_ids.add(workload_id)
        name, description = text(data["name"]), text(data["description"])
        if not isinstance(data["experiments"], list):
            raise ValueError("Expected experiment array")
        experiments = []
        experiment_ids: set[str] = set()
        for entry in data["experiments"]:
            report_count += 1
            if report_count > 100:
                raise ValueError("Catalog supports at most 100 experiments")
            spec = _object(entry, {"id", "title", "recorded_at", "kind", "input", "synthetic"})
            key = identifier(spec["id"])
            if key in experiment_ids:
                raise ValueError("Duplicate experiment ID in workload")
            experiment_ids.add(key)
            title = text(spec["title"])
            recorded = instant(spec["recorded_at"]).isoformat()
            if (
                spec["kind"] not in ("compare", "verify", "finance")
                or type(spec["synthetic"]) is not bool
            ):
                raise ValueError("Unsupported experiment kind or synthetic flag")
            nonempty(spec["input"], "input path")
            relative = Path(spec["input"])
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Input paths must stay within the catalog directory")
            target = (root / relative).resolve()
            if not target.is_relative_to(root):
                raise ValueError("Input symlink escapes the catalog directory")
            try:
                size = target.stat().st_size
                input_bytes += size
                if input_bytes > 20_000_000:
                    raise OverflowError("Catalog input budget exceeded")
                report, raw = calculate(spec["kind"], read_json(target))
                output_bytes += len(raw)
                if output_bytes > 50_000_000:
                    raise OverflowError("Catalog output budget exceeded")
                status = (
                    report["results"][0]["status"]
                    if spec["kind"] == "compare"
                    else report["overall_status"]
                    if spec["kind"] == "verify"
                    else report["status"]
                )
                notes = list(report["limitations"])
                if spec["kind"] == "finance":
                    notes += report["attribution"]["reasons"]
                else:
                    checks = report["results"] if spec["kind"] == "compare" else report["checks"]
                    notes += [c["reason"] for c in checks]
                view = ExperimentView(
                    key,
                    title,
                    recorded,
                    spec["kind"],
                    spec["synthetic"],
                    status,
                    True,
                    sections(spec["kind"], report),
                    tuple(notes),
                    hashlib.sha256(raw).hexdigest(),
                    raw,
                )
            except (ValueError, TypeError, OSError, RecursionError):
                view = ExperimentView(
                    key,
                    title,
                    recorded,
                    spec["kind"],
                    spec["synthetic"],
                    "UNKNOWN",
                    False,
                    (),
                    ("Input is unavailable or invalid. Correct the input and restart the viewer.",),
                    "",
                    b"",
                )
            experiments.append(view)
        result.append(
            WorkloadView(
                workload_id,
                name,
                description,
                tuple(sorted(experiments, key=lambda e: (e.recorded_at, e.id), reverse=True)),
            )
        )
    return tuple(result)
