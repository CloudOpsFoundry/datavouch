"""Authenticated local HTML viewer. No cloud access or browser-side calculations."""

import hashlib
import secrets
from dataclasses import asdict
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware

from datavouch.web.catalog import ExperimentView, WorkloadView, load_catalog
from datavouch.web.connections import load_connections
from datavouch.web.planner import planning_router

ASSETS = Path(__file__).parent


def create_app(
    catalog: Path,
    password: str,
    *,
    allow_raw_reports: bool = False,
    connections: Path | None = None,
) -> FastAPI:
    """Create a read-only startup snapshot guarded by local HTTP Basic authentication."""
    if (
        not isinstance(password, str)
        or not password.isascii()
        or not password.isprintable()
        or not password.strip()
        or not 16 <= len(password) <= 256
    ):
        raise ValueError("Viewer password must contain 16 to 256 ASCII characters")
    password_digest = hashlib.sha256(password.encode()).digest()
    workloads = load_catalog(catalog)
    security = HTTPBasic(auto_error=False)

    def authenticate(
        credentials: Annotated[HTTPBasicCredentials | None, Depends(security)],
    ) -> None:
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

    app = FastAPI(
        docs_url=None, redoc_url=None, openapi_url=None, dependencies=[Depends(authenticate)]
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "[::1]"])
    templates = Jinja2Templates(directory=ASSETS / "templates")
    app.mount("/static", StaticFiles(directory=ASSETS / "static"), name="static")

    @app.middleware("http")
    async def security_headers(request: Request, call_next: RequestResponseEndpoint) -> Response:
        if request.headers.get("sec-fetch-site") == "cross-site":
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
        counts = {
            state: sum(e.status == state for _, e in experiments)
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
                "total": len(experiments),
                "q": q,
                "status": status,
            },
        )

    @app.get("/workloads", response_class=HTMLResponse)
    def workload_list(request: Request) -> Response:
        return templates.TemplateResponse(
            request=request,
            name="workloads.html",
            context={"title": "Workloads", "workloads": workloads},
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

    app.include_router(planning_router(templates, load_connections(connections)))
    return app
