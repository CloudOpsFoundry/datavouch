"""Authenticated local workspace with explicit, optional backend execution."""

import asyncio
import hashlib
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Annotated
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware

from datavouch.web.access import LOCAL_ADMIN, account, gateway_principal, policy, principal
from datavouch.web.catalog import ExperimentView, WorkloadView, load_catalog
from datavouch.web.connections import load_connections
from datavouch.web.planner import planning_router
from datavouch.web.runs import RunStore, run_router

ASSETS = Path(__file__).parent


def create_app(
    catalog: Path,
    password: str,
    *,
    allow_raw_reports: bool = False,
    connections: Path | None = None,
    run_directory: Path | None = None,
    enable_live_execution: bool = False,
    gateway_config: Path | None = None,
    gateway_secret: str = "",
) -> FastAPI:
    """Create a local workspace guarded by HTTP Basic authentication."""
    if gateway_config is not None and (
        not 32 <= len(gateway_secret) <= 256
        or not gateway_secret.strip()
        or not gateway_secret.isascii()
        or not gateway_secret.isprintable()
    ):
        raise ValueError("Gateway mode requires a strong backend secret")
    gateway_policy = policy(gateway_config) if gateway_config else None
    if gateway_config is None and (
        not isinstance(password, str)
        or not password.isascii()
        or not password.isprintable()
        or not password.strip()
        or not 16 <= len(password) <= 256
    ):
        raise ValueError("Viewer password must contain 16 to 256 ASCII characters")
    password_digest = hashlib.sha256(password.encode()).digest()
    workloads = () if gateway_config else load_catalog(catalog)
    security = HTTPBasic(auto_error=False)

    def authenticate(
        request: Request,
        credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    ) -> None:
        if gateway_config is not None:
            request.state.principal = gateway_principal(request, gateway_config, gateway_secret)
            return
        request.state.principal = LOCAL_ADMIN
        if credentials is None:
            raise HTTPException(
                401,
                "Authentication required",
                headers={"WWW-Authenticate": 'Basic realm="DataVouch"'},
            )
        correct_user = secrets.compare_digest(credentials.username.encode(), b"datavouch")
        correct_password = secrets.compare_digest(
            hashlib.sha256(credentials.password.encode()).digest(), password_digest
        )
        if not (correct_user and correct_password):
            raise HTTPException(
                401,
                "Authentication required",
                headers={"WWW-Authenticate": 'Basic realm="DataVouch"'},
            )

    if enable_live_execution and (connections is None or run_directory is None):
        raise ValueError("Execution requires connections and a private run directory")
    configured_connections = load_connections(connections)

    def authorize_actor(subject: str, connection: str) -> None:
        user = account(gateway_config, subject) if gateway_config else LOCAL_ADMIN
        if user.role not in {"operator", "admin"} or not user.permits(connection):
            raise ValueError("Execution authorization revoked")

    store = (
        RunStore(run_directory, connections, authorize_actor)
        if enable_live_execution and run_directory is not None and connections is not None
        else None
    )

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            if store is not None:
                await asyncio.to_thread(store.close)

    app = FastAPI(
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
        dependencies=[Depends(authenticate)],
        lifespan=lifespan,
    )
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=gateway_policy["allowed_hosts"]
        if gateway_policy
        else ["127.0.0.1", "localhost", "[::1]"],
    )
    templates = Jinja2Templates(directory=ASSETS / "templates")
    templates.env.globals["execution_enabled"] = store is not None
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        origin = request.headers.get("origin")
        unsafe_origin = False
        if origin is not None and request.method not in {"GET", "HEAD", "OPTIONS"}:
            try:
                parsed_origin = urlsplit(origin)
                unsafe_origin = parsed_origin.scheme not in {
                    "http",
                    "https",
                } or parsed_origin.netloc != request.headers.get("host")
            except ValueError:
                unsafe_origin = True
        if request.headers.get("sec-fetch-site") == "cross-site" or unsafe_origin:
            response = Response("Cross-site requests are not supported", status_code=403)
        else:
            response = await call_next(request)
        response.headers.update(
            {
                "Cache-Control": "no-store",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "no-referrer",
                "X-Frame-Options": "DENY",
                "Content-Security-Policy": (
                    "default-src 'none'; style-src 'self'; img-src 'self'; "
                    "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
                ),
            }
        )
        return response

    def workload_by_id(key: str) -> WorkloadView:
        workload = next((w for w in workloads if w.id == key), None)
        if workload is None:
            raise HTTPException(404, "Not found")
        return workload

    def experiment_by_id(workload: WorkloadView, key: str) -> ExperimentView:
        experiment = next((e for e in workload.experiments if e.id == key), None)
        if experiment is None:
            raise HTTPException(404, "Not found")
        return experiment

    @app.exception_handler(StarletteHTTPException)
    async def error(request: Request, exc: StarletteHTTPException) -> Response:
        labels = {
            401: "Sign in to DataVouch",
            403: "This action is not enabled",
            404: "Page not found",
            405: "Read-only viewer",
            409: "Report unavailable",
        }
        return templates.TemplateResponse(
            request=request,
            name="error.html",
            context={
                "title": labels.get(exc.status_code, "Request could not be completed"),
                "status_code": exc.status_code,
            },
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request, q: str = "", status: str = "") -> Response:
        if len(q) > 200 or status not in ("", "PASS", "FAIL", "UNKNOWN"):
            raise HTTPException(400, "Invalid filter")
        experiments = [(w, e) for w in workloads for e in w.experiments]
        authorized_runs = (
            [r for r in store.list_runs() if principal(request).permits(r["connection"])]
            if store
            else []
        )
        counts = {
            state: sum(e.status == state for _, e in experiments)
            + sum(r["status"] == state for r in authorized_runs)
            for state in ("PASS", "FAIL", "UNKNOWN")
        }
        visible = [
            (w, e)
            for w, e in experiments
            if (not status or e.status == status)
            and q.casefold() in f"{w.name} {e.title}".casefold()
        ]
        visible.sort(key=lambda item: (item[1].recorded_at, item[0].id, item[1].id), reverse=True)
        return templates.TemplateResponse(
            request=request,
            name="overview.html",
            context={
                "title": "Verification overview",
                "workloads": workloads,
                "counts": counts,
                "experiments": visible,
                "total": len(experiments) + len(authorized_runs),
                "recent_runs": [
                    r for r in store.list_runs() if principal(request).permits(r["connection"])
                ][:5]
                if store
                else [],
                "q": q,
                "status": status,
            },
        )

    @app.get("/workloads", response_class=HTMLResponse)
    def workload_list(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="workloads.html",
            context={
                "title": "Workloads",
                "workloads": workloads,
                "registered_workloads": sorted(
                    {
                        r.get("workload", r["title"])
                        for r in store.list_runs()
                        if principal(request).permits(r["connection"])
                    }
                )
                if store
                else [],
            },
        )

    @app.get("/workloads/{workload_id}", response_class=HTMLResponse)
    def workload_detail(request: Request, workload_id: str) -> Response:
        workload = workload_by_id(workload_id)
        return templates.TemplateResponse(
            request=request,
            name="workload.html",
            context={"title": workload.name, "workload": workload},
        )

    @app.get("/workloads/{workload_id}/experiments/{experiment_id}", response_class=HTMLResponse)
    def experiment_detail(request: Request, workload_id: str, experiment_id: str) -> Response:
        workload = workload_by_id(workload_id)
        experiment = experiment_by_id(workload, experiment_id)
        return templates.TemplateResponse(
            request=request,
            name="experiment.html",
            context={
                "title": experiment.title,
                "workload": workload,
                "experiment": experiment,
                "allow_raw_reports": allow_raw_reports,
            },
        )

    @app.get("/workloads/{workload_id}/experiments/{experiment_id}/summary.json")
    def summary(workload_id: str, experiment_id: str) -> Response:
        experiment = experiment_by_id(workload_by_id(workload_id), experiment_id)
        data = {
            "title": experiment.title,
            "status": experiment.status,
            "kind": experiment.kind,
            "synthetic": experiment.synthetic,
            "available": experiment.available,
            "sections": [asdict(s) for s in experiment.sections],
        }
        return JSONResponse(
            data, headers={"Content-Disposition": 'attachment; filename="datavouch-summary.json"'}
        )

    @app.get("/workloads/{workload_id}/experiments/{experiment_id}/report.json")
    def raw_report(workload_id: str, experiment_id: str) -> Response:
        if not allow_raw_reports:
            raise HTTPException(403, "Full report access is not enabled")
        experiment = experiment_by_id(workload_by_id(workload_id), experiment_id)
        if not experiment.available:
            raise HTTPException(409, "Report unavailable")
        return Response(
            experiment.raw,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="datavouch-report.json"'},
        )

    app.include_router(planning_router(templates, configured_connections, store))
    app.include_router(run_router(templates, store, allow_raw_reports))
    return app
