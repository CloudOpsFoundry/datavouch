"""Offline workflow gate with explicit UNKNOWN handling and safe report projections."""

import copy
import hashlib
import html
import json
from pathlib import Path
from typing import Any

from datavouch.core.configuration import _object
from datavouch.core.models import Status
from datavouch.verification.evaluation import verify
from datavouch.verification.reliability import ReliabilityPolicy


def encoded(value: Any) -> str:
    return json.dumps(value, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(value: Any) -> str:
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def evaluate(document: Any, policy: Any) -> dict[str, Any]:
    config = _object(
        policy, {"schema_version", "unknown", "comparison", "required_checks", "reliability"}
    )
    if config["schema_version"] != "workflow-policy-0.1" or config["unknown"] not in (
        "block",
        "allow",
    ):
        raise ValueError("Unsupported workflow policy")
    names = config["required_checks"]
    if (
        not isinstance(names, list)
        or not 1 <= len(names) <= 100
        or any(not isinstance(n, str) or not n.strip() or len(n) > 300 for n in names)
    ):
        raise ValueError("Declare 1 to 100 bounded check names")
    thresholds = _object(config["reliability"], {"max_failure_percent", "max_increase_points"})
    ReliabilityPolicy(complete=False, **thresholds)
    effective = copy.deepcopy(_object(document, {"comparison", "assurance"}))
    comparison = _object(effective["comparison"], {"experiment", "policy"})
    comparison["policy"] = config["comparison"]
    assurance = _object(
        effective["assurance"],
        {"required_checks"},
        {"evidence", "windows", "completed_at", "started_at", "reliability"},
    )
    assurance["required_checks"] = names
    reliability = _object(
        assurance.get("reliability", {"complete": False}),
        {"complete"},
        {"max_failure_percent", "max_increase_points"},
    )
    assurance["reliability"] = {"complete": reliability["complete"], **thresholds}
    report = verify(effective)
    status = report["overall_status"]
    exit_code = {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 3}[status]
    if status == "UNKNOWN" and config["unknown"] == "allow":
        exit_code = 0
    gate = (
        status
        if status != "UNKNOWN"
        else ("ALLOWED_UNKNOWN" if exit_code == 0 else "BLOCKED_UNKNOWN")
    )
    metric = report["performance"]["results"][0]
    return {
        "schema_version": "workflow-0.1",
        "evidence_status": status,
        "gate_status": gate,
        "exit_code": exit_code,
        "unknown_policy": config["unknown"],
        "input_sha256": digest(document),
        "policy_sha256": digest(policy),
        "effective_input_sha256": report["input_sha256"],
        "checks": [{"name": c["name"], "status": c["status"]} for c in report["checks"]],
        "performance": {
            k: metric[k]
            for k in ("check", "unit", "baseline_mean", "candidate_mean", "regression_percent")
        },
        "limitations": report["limitations"]
        + [
            "An allowed UNKNOWN is not verified evidence or approval to merge.",
            "Report labels are supplied by the policy or input; review before sharing.",
        ],
    }


def markdown(report: dict[str, Any]) -> str:
    # Numeric entities prevent labels from injecting Markdown, links or mentions.
    def label(value: object) -> str:
        return "".join(f"&#{ord(c)};" for c in str(value))

    rows = "\n".join(f"| {label(c['name'])} | {c['status']} |" for c in report["checks"])
    return (
        "## DataVouch verification\n\n"
        f"Evidence: **{report['evidence_status']}** · Gate: **{report['gate_status']}**\n\n"
        f"UNKNOWN policy: `{report['unknown_policy']}` · Exit code: {report['exit_code']}\n\n"
        "| Required check | Result |\n| --- | --- |\n" + rows + "\n\n"
        "PASS applies only to configured checks. Allowed UNKNOWN is not a pass. "
        "No approval, causal improvement or realized savings is established.\n\n"
        f"Policy SHA256: `{report['policy_sha256']}`\n"
    )


def html_report(report: dict[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{html.escape(c['name'])}</td><td>{c['status']}</td></tr>"
        for c in report["checks"]
    )
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta http-equiv="Content-Security-Policy" content="default-src &#39;none&#39;; '
        'base-uri &#39;none&#39;">'
        "<title>DataVouch verification</title><body><main><h1>DataVouch verification</h1>"
        f"<p>Evidence: <strong>{report['evidence_status']}</strong> · "
        f"Gate: <strong>{report['gate_status']}</strong></p>"
        f"<p>UNKNOWN policy: {report['unknown_policy']}; exit code: {report['exit_code']}</p>"
        "<table><thead><tr><th>Required check</th><th>Result</th></tr></thead><tbody>"
        + rows
        + "</tbody></table><p>PASS applies only to configured checks. "
        "Allowed UNKNOWN is not a pass. No approval, causal improvement or realized "
        "savings is established.</p>"
        f"<p>Policy SHA256: <code>{report['policy_sha256']}</code></p></main></body></html>\n"
    )


def write_reports(directory: Path, report: dict[str, Any]) -> None:
    """Write only to a newly created explicit directory; never replace existing evidence."""
    outputs = {
        "report.json": encoded(report),
        "summary.md": markdown(report),
        "report.html": html_report(report),
    }
    directory.mkdir()  # Existing directories and symlinks are intentionally rejected.
    for name, content in outputs.items():
        (directory / name).write_text(content, encoding="utf-8")
