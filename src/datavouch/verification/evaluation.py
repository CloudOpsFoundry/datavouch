"""Combine required checks with conservative failure and missing-evidence precedence."""

import hashlib
import json
from dataclasses import asdict
from typing import Any

from datavouch.analysis.comparison import compare
from datavouch.core.configuration import _object, decode
from datavouch.core.models import Status, nonempty
from datavouch.reports.json_report import render
from datavouch.verification.correctness import CheckResult, decode_check, instant
from datavouch.verification.correctness import evaluate as correctness
from datavouch.verification.reliability import ReliabilityPolicy
from datavouch.verification.reliability import evaluate as reliability
from datavouch.verification.windows import Windows, select


def aggregate(results: tuple[CheckResult, ...]) -> Status:
    """A known failure dominates missing evidence. PASS applies only to configured checks."""
    statuses = {result.status for result in results}
    if Status.FAIL in statuses:
        return Status.FAIL
    if not results or Status.UNKNOWN in statuses:
        return Status.UNKNOWN
    return Status.PASS


def verify(document: Any) -> dict[str, Any]:
    """Evaluate a bounded input decoded by the CLI, without external access."""
    root = _object(document, {"comparison", "assurance"})
    experiment, policy = decode(root["comparison"])
    assurance = _object(
        root["assurance"],
        {"required_checks"},
        {"evidence", "windows", "completed_at", "started_at", "reliability"},
    )
    names = assurance["required_checks"]
    if not isinstance(names, list) or not names:
        raise ValueError("Declare at least one required correctness check")
    for name in names:
        nonempty(name, "required check name")
        if name in {"performance", "reliability", "windows"}:
            raise ValueError("Reserved check name")
    if len(set(names)) != len(names):
        raise ValueError("Duplicate required checks")
    evidence = assurance.get("evidence", [])
    if not isinstance(evidence, list) or not all(isinstance(item, dict) for item in evidence):
        raise ValueError("Expected correctness evidence array")
    decoded = [decode_check(item) for item in evidence]
    by_name = {item.name: item for item in decoded}
    if len(by_name) != len(decoded) or set(by_name) - set(names):
        raise ValueError("Duplicate or unrequested correctness evidence")
    excluded: tuple[str, ...] = ()
    window_data = assurance.get("windows")
    if window_data is None:
        window_result = CheckResult("windows", Status.UNKNOWN, "Observation windows are missing")
    else:
        windows = Windows(
            **_object(
                window_data,
                {"baseline_start", "baseline_end", "change_at", "candidate_start", "candidate_end"},
            )
        )
        times = assurance.get("completed_at")
        starts = assurance.get("started_at")
        if times is None or starts is None:
            window_result = CheckResult(
                "windows", Status.UNKNOWN, "Completion timestamps are missing"
            )
        else:
            if not isinstance(times, dict) or not isinstance(starts, dict):
                raise ValueError("Expected completion timestamp mapping")
            # Missing timestamps are incomplete evidence, not proof of eligibility.
            expected_ids = {
                o.execution.id for o in experiment.baseline.observations + experiment.candidate
            }
            if set(times) != expected_ids or set(starts) != expected_ids:
                window_result = CheckResult(
                    "windows",
                    Status.UNKNOWN,
                    "Completion timestamps do not cover the execution cohorts",
                )
            else:
                experiment, excluded = select(experiment, windows, times, starts)
                window_result = CheckResult(
                    "windows", Status.PASS, "Chronological completion windows selected"
                )
    performance_report = compare(experiment, policy)
    metric = performance_report.results[0]
    results = [window_result, CheckResult("performance", metric.status, metric.reason)]
    for name in sorted(names):
        results.append(
            correctness(by_name[name], experiment)
            if name in by_name
            else CheckResult(name, Status.UNKNOWN, "Required correctness evidence is missing")
        )
    for index, result in enumerate(results):
        check = by_name.get(result.name)
        if (
            check is not None
            and check.kind == "freshness"
            and check.as_of is not None
            and window_result.status == Status.PASS
            and experiment.candidate
        ):
            latest = max(
                instant(assurance["completed_at"][o.execution.id]) for o in experiment.candidate
            )
            if instant(check.as_of) < latest:
                results[index] = CheckResult(
                    check.name, Status.UNKNOWN, "Freshness evaluation precedes candidate completion"
                )
    reliability_config = _object(
        assurance.get("reliability", {"complete": False}),
        {"complete"},
        {"max_failure_percent", "max_increase_points"},
    )
    reliability_result, rates = reliability(
        experiment, ReliabilityPolicy(**reliability_config), policy.minimum_samples
    )
    if window_result.status != Status.PASS:
        reliability_result = CheckResult(
            "reliability", Status.UNKNOWN, "Reliable observation windows are unavailable"
        )
    results.append(reliability_result)
    performance = json.loads(render(performance_report))
    performance["results"] = performance["results"][:1]
    performance["limitations"] = performance["limitations"][:2]
    encoded = json.dumps(document, sort_keys=True, allow_nan=False)
    return {
        "schema_version": "verification-0.1",
        "overall_status": aggregate(tuple(results)),
        "checks": [asdict(result) for result in results],
        "performance": performance,
        "reliability_metrics": rates,
        "excluded_execution_ids": excluded,
        "evidence_quality": {
            status.value: sum(r.status == status for r in results) for status in Status
        },
        "input_sha256": hashlib.sha256(encoded.encode()).hexdigest(),
        "source": document,
        "limitations": [
            "PASS applies only to the declared checks, not whole-system correctness.",
            "Evidence references, coverage and completeness are caller attestations, "
            "not authenticated proofs.",
            "Execution timestamps and change time are supplied by the evidence producer.",
            "No causation, statistical significance or financial savings conclusion is supported.",
        ],
    }
