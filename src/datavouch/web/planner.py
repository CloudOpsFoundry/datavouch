"""Bounded experiment planning with optional cloud discovery and explicit collection."""

import secrets
from typing import Any
from urllib.parse import parse_qsl, urlencode

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool

from datavouch.adapters.bigquery.experiments import encoded, prepare
from datavouch.web.access import form_token, operator, principal
from datavouch.web.connections import Connection
from datavouch.web.discovery import PROJECT, ConnectionCatalog, DiscoveryError, Listing
from datavouch.web.evidence import METRICS, check_key, supplied_evidence
from datavouch.web.runs import RunBusy, RunStore
from datavouch.web.temporal import picker_timestamp

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
        "Maximum metric regression (%)",
        "Allowed increase in the selected metric; lower is better.",
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
    metric = values.get("metric", "runtime")
    if metric not in METRICS:
        raise ValueError("Select a supported BigQuery metric")
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
            "metric": {"name": metric, "unit": METRICS[metric][1], "direction": "lower"},
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
    plan["assurance"]["evidence"] = supplied_evidence(values, plan)
    prepare(plan)
    return plan


def planning_router(
    templates: Jinja2Templates,
    connections: tuple[Connection, ...],
    store: RunStore | None = None,
    catalog: ConnectionCatalog | None = None,
) -> APIRouter:
    """Create authenticated form routes; app dependencies apply to both routes."""
    router = APIRouter()
    token = secrets.token_urlsafe(32)

    def render(
        request: Request,
        values: dict[str, str],
        error: str = "",
        plan: str = "",
        status_code: int | None = None,
    ) -> Response:
        visible = tuple(c for c in connections if principal(request).permits(c.id))
        projects = Listing((), "")
        locations = Listing((), "")
        discovery_enabled = False
        discovery_error = ""
        if catalog is not None:
            try:
                discovery_enabled = catalog.enabled()
                if discovery_enabled:
                    projects = catalog.projects(principal(request))
                    visible, locations = catalog.choices(
                        principal(request), values.get("discovery_project", "")
                    )
            except (ValueError, OSError) as exc:
                discovery_error = (
                    str(exc)
                    if isinstance(exc, DiscoveryError)
                    else "Check the deployment's connection configuration."
                )
        return templates.TemplateResponse(
            request=request,
            name="planner.html",
            context={
                "title": "Plan a BigQuery experiment",
                "fields": FIELDS,
                "connections": visible,
                "discovery_enabled": discovery_enabled,
                "discovery_projects": projects.entries,
                "discovery_checked": locations.checked_at or projects.checked_at,
                "discovery_incomplete": locations.incomplete or projects.incomplete,
                "discovery_error": discovery_error,
                "execution_enabled": store is not None,
                "known_workloads": sorted(
                    {
                        r.get("workload", "")
                        for r in store.list_runs()
                        if principal(request).permits(r["connection"])
                    }
                    - {""}
                )
                if store
                else [],
                "values": values,
                "multiline": MULTILINE,
                "time_fields": TIME_FIELDS,
                "metrics": METRICS,
                "checks": [
                    (name.strip(), check_key(name.strip()))
                    for name in dict.fromkeys(
                        values.get("required_checks", "business_total").splitlines()
                    )
                    if name.strip()
                ][:100],
                "csrf": form_token(token, request),
                "error": error,
                "plan": plan,
            },
            status_code=status_code or (422 if error else 200),
        )

    @router.get("/experiments/new")
    def new_plan(request: Request, project: str = "") -> Response:
        operator(request)
        if project and not PROJECT.fullmatch(project):
            raise HTTPException(400, "Invalid project selection")
        return render(
            request,
            {**{name: default for name, _, _, default in FIELDS}, "discovery_project": project},
        )

    @router.post("/connections/refresh")
    async def refresh_connections(request: Request) -> Response:
        operator(request)
        if catalog is None or not catalog.enabled():
            raise HTTPException(403, "Cloud discovery is disabled")
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Expected an HTML form")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, "Refresh form exceeds its limit")
        try:
            pairs = parse_qsl(body.decode("utf-8"), keep_blank_values=True, max_num_fields=2)
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, "Invalid refresh form") from exc
        values = dict(pairs)
        if len(values) != len(pairs) or values.keys() - {"csrf", "project"}:
            raise HTTPException(400, "Invalid refresh form")
        if not secrets.compare_digest(
            values.get("csrf", "").encode(), form_token(token, request).encode()
        ):
            raise HTTPException(403, "Reload before refreshing")
        project = values.get("project", "")
        if project and not PROJECT.fullmatch(project):
            raise HTTPException(400, "Invalid project selection")
        await run_in_threadpool(catalog.refresh)
        return RedirectResponse(
            "/experiments/new?" + urlencode({"project": project}), status_code=303
        )

    @router.post("/experiments/new")
    async def validate_plan(request: Request) -> Response:
        user = operator(request)
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
                max_num_fields=256,
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
            "confirm_run",
            "metric",
            "evidence_json",
            "evidence_confirmed",
            "discovery_project",
        }
        for name in values.get("required_checks", "business_total").splitlines()[:100]:
            key = check_key(name.strip())
            allowed.update({key + "_outcome", key + "_reference"})
        if (
            len(values) != len(pairs)
            or values.keys() - allowed
            or any(len(v) > 16384 for v in values.values())
        ):
            raise HTTPException(400, "Invalid form fields")
        if not secrets.compare_digest(
            values.pop("csrf", "").encode(), form_token(token, request).encode()
        ):
            raise HTTPException(403, "Reload the form before submitting")
        if values.get("action") not in {"validate", "download", "run"} or any(
            values.get(key, "") not in {"", "yes"}
            for key in ("complete", "synthetic", "confirm_run", "evidence_confirmed")
        ):
            raise HTTPException(400, "Invalid form choice")
        try:
            identity = values.get("connection", "")
            if not user.permits(identity):
                raise ValueError("Select a connection approved for this deployment.")
            connection = (
                await run_in_threadpool(catalog.resolve, identity)
                if catalog
                else next((c for c in connections if c.id == identity), None)
            )
            if connection is None:
                raise ValueError("Select a connection approved for this deployment.")
            plan = encoded(build_plan(values, connection))
        except (ValueError, TypeError, OverflowError) as exc:
            return await run_in_threadpool(render, request, values, str(exc))
        if values["action"] == "run":
            if store is None or values.get("confirm_run") != "yes":
                raise HTTPException(403, "Live execution is disabled or not confirmed")
            try:
                key = await run_in_threadpool(
                    store.submit, build_plan(values, connection), connection.id, user.subject
                )
            except RunBusy as exc:
                return await run_in_threadpool(render, request, values, str(exc), status_code=409)
            except ValueError, OSError:
                return await run_in_threadpool(
                    render,
                    request,
                    values,
                    (
                        "Run not started. Check current connection approval, limits "
                        "and closed execution windows."
                    ),
                )
            return RedirectResponse(f"/runs/{key}", status_code=303)
        if values["action"] == "download":
            return Response(
                plan,
                media_type="application/json",
                headers={
                    "Content-Disposition": 'attachment; filename="datavouch-plan.json"',
                },
            )
        return await run_in_threadpool(render, request, values, plan=plan)

    return router
