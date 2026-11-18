"""Guided, bounded experiment planning without cloud or filesystem writes."""

import re
import secrets
from datetime import UTC, datetime
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from datavouch.adapters.bigquery.experiments import encoded, prepare
from datavouch.web.connections import Connection

# name, label, help, default. Real execution identifiers are never prefilled.
FIELDS = (
    ("id", "Experiment name", "A stable name for this comparison, such as sales-rewrite-1.", ""),
    ("workload", "Workload name", "The query or pipeline being changed.", ""),
    ("environment", "Environment", "Name the environment, such as staging or production.", ""),
    ("snapshot", "Input snapshot", "Identify the same input data used by both versions.", ""),
    ("description", "What changed?", "Describe the SQL rewrite or configuration change.", ""),
    ("reference", "Comparability reference", "A document or ticket supporting the comparison.", ""),
    (
        "statement",
        "Why are these runs comparable?",
        "Describe matching data, parameters and conditions.",
        "",
    ),
    (
        "baseline_start",
        "Baseline start",
        "Choose the start date and time in UTC.",
        "",
    ),
    (
        "baseline_end",
        "Baseline end",
        "Exclusive end of the original version's execution window.",
        "",
    ),
    (
        "baseline_jobs",
        "Baseline job IDs",
        "One BigQuery job ID per line, up to 100. Include failures.",
        "",
    ),
    (
        "change_at",
        "Change time",
        "Choose a UTC date and time between the baseline and candidate windows.",
        "",
    ),
    (
        "candidate_start",
        "Candidate start",
        "Start of the changed version's execution window, in UTC.",
        "",
    ),
    (
        "candidate_end",
        "Candidate end",
        "Exclusive end in UTC. Live collection needs a closed window.",
        "",
    ),
    ("candidate_jobs", "Candidate job IDs", "One job ID per line. Do not reuse baseline IDs.", ""),
    (
        "minimum_samples",
        "Minimum runs per version",
        "Fewer eligible runs leave performance UNKNOWN.",
        "3",
    ),
    (
        "max_regression_percent",
        "Maximum runtime regression (%)",
        "Allowed increase in runtime; lower is better.",
        "5",
    ),
    (
        "required_checks",
        "Required correctness checks",
        "One name per line, such as business_total. Evidence is supplied separately.",
        "business_total",
    ),
    (
        "max_failure_percent",
        "Maximum failure rate (%)",
        "Allowed failed executions in the candidate cohort.",
        "0",
    ),
    (
        "max_increase_points",
        "Maximum failure-rate increase (percentage points)",
        "Allowed increase from baseline to candidate.",
        "0",
    ),
    (
        "maximum_bytes_billed",
        "Metadata query byte limit",
        "Per collection query, not a price or workload execution limit.",
        "100000000",
    ),
    (
        "timeout_seconds",
        "Collection timeout (seconds)",
        "Between 1 and 300 seconds per query.",
        "60",
    ),
)
MULTILINE = {"baseline_jobs", "candidate_jobs", "required_checks", "description", "statement"}


TIME_FIELDS = {"baseline_start", "baseline_end", "change_at", "candidate_start", "candidate_end"}


def picker_timestamp(value: str, label: str) -> str:
    """Interpret explicit UTC calendar selections without using the host time zone."""
    if not re.fullmatch(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}(?::[0-9]{2}(?:\.[0-9]{1,3})?)?", value
    ):
        raise ValueError(f"{label}: select a UTC date and time (up to milliseconds).")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{label}: select a valid UTC date and time.") from exc
    return parsed.replace(tzinfo=UTC).isoformat().replace("+00:00", "Z")


def build_plan(values: dict[str, str], connection: Connection) -> dict[str, Any]:
    """Translate explicit form choices and delegate semantics to the CLI validator."""
    for name, label, _, _ in FIELDS:
        if not values.get(name, "").strip():
            raise ValueError(f"{label} is required.")
    times = {
        name: picker_timestamp(values[name], label)
        for name, label, _, _ in FIELDS
        if name in TIME_FIELDS
    }
    integers: dict[str, int] = {}
    for name in ("minimum_samples", "maximum_bytes_billed", "timeout_seconds"):
        try:
            integers[name] = int(values[name])
        except ValueError as exc:
            raise ValueError(f"{name.replace('_', ' ')} must be a whole number.") from exc
    numbers: dict[str, float] = {}
    for name in ("max_regression_percent", "max_failure_percent", "max_increase_points"):
        try:
            numbers[name] = float(values[name])
        except ValueError as exc:
            raise ValueError(f"{name.replace('_', ' ')} must be a number.") from exc
    checks = values["required_checks"].splitlines()
    checks = [check.strip() for check in checks if check.strip()]
    if not checks or len(checks) > 100 or len(checks) != len(set(checks)):
        raise ValueError("Provide between 1 and 100 distinct required correctness checks.")
    plan: dict[str, Any] = {
        "schema_version": "bigquery-experiment-0.1",
        "id": values["id"],
        "change": {
            "id": values["id"] + "-change",
            "description": values["description"],
            "at": times["change_at"],
        },
        "comparability": {"reference": values["reference"], "statement": values["statement"]},
        "policy": {
            "metric": {"name": "runtime", "unit": "ms", "direction": "lower"},
            "minimum_samples": integers["minimum_samples"],
            "max_regression_percent": numbers["max_regression_percent"],
        },
        "assurance": {
            "required_checks": checks,
            "evidence": [],
            "reliability": {
                "complete": values.get("complete") == "yes",
                "max_failure_percent": numbers["max_failure_percent"],
                "max_increase_points": numbers["max_increase_points"],
            },
        },
        "synthetic": values.get("synthetic") == "yes",
    }
    for side in ("baseline", "candidate"):
        plan[side] = {
            "project": connection.project,
            "location": connection.location,
            "start": times[side + "_start"],
            "end": times[side + "_end"],
            "job_ids": [job.strip() for job in values[side + "_jobs"].splitlines() if job.strip()],
            "workload": {
                "id": values["workload"],
                "environment": values["environment"],
                "input_snapshot": values["snapshot"],
            },
            "maximum_bytes_billed": integers["maximum_bytes_billed"],
            "timeout_seconds": integers["timeout_seconds"],
        }
    if integers["maximum_bytes_billed"] > connection.maximum_bytes_billed:
        raise ValueError("Byte limit exceeds the deployment connection limit.")
    if integers["timeout_seconds"] > connection.timeout_seconds:
        raise ValueError("Timeout exceeds the deployment connection limit.")
    prepare(plan)
    return plan


def planning_router(templates: Jinja2Templates, connections: tuple[Connection, ...]) -> APIRouter:
    """Create authenticated form routes; app dependencies apply to both routes."""
    router = APIRouter()
    token = secrets.token_urlsafe(32)

    def render(
        request: Request, values: dict[str, str], error: str = "", plan: str = ""
    ) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="planner.html",
            context={
                "title": "Plan a BigQuery experiment",
                "fields": FIELDS,
                "connections": connections,
                "values": values,
                "multiline": MULTILINE,
                "time_fields": TIME_FIELDS,
                "csrf": token,
                "error": error,
                "plan": plan,
            },
            status_code=422 if error else 200,
        )

    @router.get("/experiments/new")
    def new_plan(request: Request) -> Response:
        return render(request, {name: default for name, _, _, default in FIELDS})

    @router.post("/experiments/new")
    async def validate_plan(request: Request) -> Response:
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Expected an HTML form")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Plan form exceeds 64 KiB")
        try:
            pairs = parse_qsl(
                body.decode("utf-8", errors="strict"),
                keep_blank_values=True,
                max_num_fields=32,
                encoding="utf-8",
                errors="strict",
            )
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, "Invalid form encoding") from exc
        values = dict(pairs)
        allowed = {name for name, _, _, _ in FIELDS} | {
            "csrf",
            "action",
            "complete",
            "synthetic",
            "connection",
        }
        if (
            len(values) != len(pairs)
            or values.keys() - allowed
            or any(len(v) > 16384 for v in values.values())
        ):
            raise HTTPException(400, "Invalid form fields")
        if not secrets.compare_digest(values.pop("csrf", "").encode(), token.encode()):
            raise HTTPException(403, "Reload the form before submitting")
        if values.get("action") not in {"validate", "download"} or any(
            values.get(key, "") not in {"", "yes"} for key in ("complete", "synthetic")
        ):
            raise HTTPException(400, "Invalid form choice")
        try:
            connection = next((c for c in connections if c.id == values.get("connection")), None)
            if connection is None:
                raise ValueError("Select a connection approved for this deployment.")
            plan = encoded(build_plan(values, connection))
        except (ValueError, TypeError, OverflowError) as exc:
            return render(request, values, str(exc))
        if values["action"] == "download":
            return Response(
                plan,
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="datavouch-plan.json"',
                },
            )
        return render(request, values, plan=plan)

    return router
