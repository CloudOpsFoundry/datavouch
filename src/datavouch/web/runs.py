"""Single-worker local execution with durable state and no automatic cloud retries."""

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import subprocess  # nosec B404
import sys
import threading
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

from fastapi import APIRouter
from fastapi.templating import Jinja2Templates

from datavouch.adapters.bigquery.experiments import encoded, prepare
from datavouch.core.configuration import read_json
from datavouch.financial.evaluation import assess
from datavouch.web.access import administrator, form_token, operator, principal
from datavouch.web.catalog import ExperimentView, load_catalog, sections
from datavouch.web.connections import load_connections
from datavouch.web.financial import financial_document

MAX_RUNS = 50


def stamp() -> str:
    return datetime.now(UTC).isoformat()


class RunBusy(ValueError):
    """The deployment has no execution capacity available."""


class RunStore:
    """One server owns the store; one subprocess executes at a time, with no queue."""

    def __init__(
        self,
        root: Path,
        connections: Path,
        authorize_actor: Callable[[str, str], None] | None = None,
    ) -> None:
        self.authorize_actor = authorize_actor
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if root.is_symlink() or root.stat().st_mode & 0o077:
            raise ValueError("Run directory must be private (mode 700) and not a symlink")
        self.root = root.resolve()
        self.connections = connections
        self.lock = threading.RLock()
        self.thread: threading.Thread | None = None
        self.closed = False
        self.records: dict[str, dict[str, Any]] = {}
        self.views: dict[str, ExperimentView] = {}
        # An OS-backed SQLite lock is released even after an abrupt server exit.
        self.owner = sqlite3.connect(
            self.root / ".owner.sqlite", timeout=0, check_same_thread=False
        )
        try:
            self.owner.execute("CREATE TABLE IF NOT EXISTS owner (id INTEGER)")
            self.owner.commit()
            self.owner.execute("BEGIN EXCLUSIVE")
            paths = list(self.root.glob("*/state.json"))
            if len(paths) > MAX_RUNS:
                raise ValueError("Run history exceeds deployment limit")
            for path in paths:
                key = path.parent.name
                if (
                    path.is_symlink()
                    or path.parent.is_symlink()
                    or not re.fullmatch("[a-f0-9]{64}", key)
                ):
                    raise ValueError("Invalid run history path")
                with path.open("rb") as source:
                    data = source.read(65537)
                if len(data) > 65536:
                    raise ValueError("Run state exceeds 64 KiB")
                record = json.loads(data)
                required = {
                    "id",
                    "title",
                    "connection",
                    "state",
                    "submitted_at",
                    "finished_at",
                    "status",
                    "message",
                }
                if (
                    not isinstance(record, dict)
                    or not required <= record.keys()
                    or any(
                        not isinstance(record[field], str) or len(record[field]) > 2000
                        for field in required
                    )
                ):
                    raise ValueError("Invalid run state fields")
                if (record["state"] == "COMPLETED") != (
                    record["status"] in {"PASS", "FAIL", "UNKNOWN"}
                ):
                    raise ValueError("Run status does not match state")
                if record["id"] != key or record["state"] not in {"RUNNING", "COMPLETED", "ERROR"}:
                    raise ValueError("Invalid run state")
                if record["state"] == "RUNNING":
                    record.update(
                        state="ERROR",
                        finished_at=stamp(),
                        message=(
                            "Server interrupted. No automatic retry. "
                            "Check cloud job status before creating another experiment."
                        ),
                    )
                self.records[key] = record
                self._save(record)
        except BaseException:
            self.owner.close()
            raise

    def audit(self, action: str, key: str, actor: str, connection: str, outcome: str = "") -> None:
        with self.lock:
            path = self.root / "audit.jsonl"
            if path.is_symlink() or (path.exists() and path.stat().st_size > 10_000_000):
                raise RunBusy("Audit storage needs administrator maintenance")
            event = {
                "at": stamp(),
                "action": action,
                "run": key,
                "actor": actor,
                "connection": connection,
                "outcome": outcome,
            }
            with path.open("a", encoding="utf-8") as destination:
                destination.write(json.dumps(event, sort_keys=True) + "\n")
                destination.flush()
                os.fsync(destination.fileno())
            path.chmod(0o600)

    def audit_events(self) -> list[dict[str, Any]]:
        with self.lock:
            path = self.root / "audit.jsonl"
            if not path.exists():
                return []
            if path.is_symlink() or path.stat().st_size > 10_100_000:
                raise ValueError("Audit storage exceeds read limit")
            return [json.loads(line) for line in path.read_text().splitlines()]

    def _save(self, record: dict[str, Any]) -> None:
        directory = self.root / record["id"]
        temporary = directory / "state.tmp"
        temporary.write_text(encoded(record), encoding="utf-8")
        temporary.chmod(0o600)
        temporary.replace(directory / "state.json")

    def _authorize(self, plan: dict[str, Any], connection_id: str) -> int:
        connection = next(
            (c for c in load_connections(self.connections) if c.id == connection_id), None
        )
        if connection is None:
            raise ValueError("Connection is no longer approved by this deployment.")
        before, after, _, _ = prepare(plan)
        for scope in (before, after):
            if (scope.project, scope.location) != (connection.project, connection.location):
                raise ValueError("Plan scope differs from the approved connection.")
            if (
                scope.maximum_bytes_billed > connection.maximum_bytes_billed
                or scope.timeout_seconds > connection.timeout_seconds
            ):
                raise ValueError("Plan exceeds the current deployment collection limits.")
            scope.validate_live_window(datetime.now(UTC))
        return before.timeout_seconds + after.timeout_seconds + 30

    def submit(
        self, plan: dict[str, Any], connection_id: str, actor: str = "local:datavouch"
    ) -> str:
        payload = encoded(plan)
        plan = json.loads(payload)
        identity = "" if actor == "local:datavouch" else actor + "\n"
        key = hashlib.sha256((identity + connection_id + "\n" + payload).encode()).hexdigest()
        with self.lock:
            if self.closed:
                raise RunBusy("Execution is shutting down.")
            if self.authorize_actor:
                self.authorize_actor(actor, connection_id)
            self._authorize(plan, connection_id)
            if key in self.records:
                return key
            if self.thread is not None and self.thread.is_alive():
                raise RunBusy(
                    "Another experiment is running. Wait for it to finish; nothing was queued."
                )
            if len(self.records) >= MAX_RUNS:
                raise RunBusy(
                    "Run history is full. Ask the administrator to archive completed runs."
                )
            directory = self.root / key
            directory.mkdir(mode=0o700, exist_ok=False)
            plan_path = directory / "plan.json"
            plan_path.write_text(payload, encoding="utf-8")
            plan_path.chmod(0o600)
            record = {
                "id": key,
                "title": plan["id"],
                "connection": connection_id,
                "submitted_by": actor,
                "workload": plan["baseline"]["workload"]["id"],
                "project": plan["baseline"]["project"],
                "location": plan["baseline"]["location"],
                "state": "RUNNING",
                "submitted_at": stamp(),
                "finished_at": "",
                "status": "",
                "message": "Collecting metadata and evaluating evidence.",
            }
            self.audit("run_submitted", key, actor, connection_id)
            self._save(record)
            self.records[key] = record
            self.thread = threading.Thread(
                target=self._execute, args=(key, plan, connection_id, actor), daemon=True
            )
            self.thread.start()
            return key

    def _execute(
        self, key: str, plan: dict[str, Any], connection_id: str, actor: str = "local:datavouch"
    ) -> None:
        outcome: dict[str, Any] = {
            "state": "ERROR",
            "status": "",
            "message": (
                "Collection failed. Check backend credentials, project permissions, "
                "location and query limits. No automatic retry."
            ),
        }
        try:
            if self.authorize_actor:
                self.authorize_actor(actor, connection_id)
            timeout = self._authorize(plan, connection_id)
            directory = self.root / key
            # Paths are server-owned, keyed by a digest; the browser cannot supply argv.
            result = subprocess.run(  # nosec B603
                [
                    sys.executable,
                    "-m",
                    "datavouch",
                    "run-bigquery",
                    str(directory / "plan.json"),
                    "--live",
                    "--output-dir",
                    str(directory / "result"),
                ],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=timeout,
                check=False,
                shell=False,
            )
            expected = {0: "PASS", 1: "FAIL", 3: "UNKNOWN"}
            if result.returncode in expected:
                view = load_catalog(directory / "result/catalog.json")[0].experiments[0]
                if not view.available or view.status != expected[result.returncode]:
                    raise ValueError("Inconsistent saved report")
                with self.lock:
                    self.views[key] = view
                outcome.update(
                    state="COMPLETED",
                    status=view.status,
                    message="Evidence evaluation completed. Review the checks and limitations.",
                )
        except subprocess.TimeoutExpired:
            outcome["message"] = (
                "Execution deadline exceeded. Local worker stopped; "
                "remote jobs may still be running. "
                "Check cloud job status before another run."
            )
        except Exception:
            # Do not expose credentials, SDK responses, paths or supplied data in errors.
            outcome["state"] = "ERROR"
        finally:
            with self.lock:
                try:
                    self.audit(
                        "run_finished",
                        key,
                        actor,
                        connection_id,
                        outcome.get("status") or outcome["state"],
                    )
                except ValueError, OSError:
                    outcome.update(
                        state="ERROR",
                        status="",
                        message=(
                            "Evidence was collected but audit persistence failed. "
                            "Administrator review is required."
                        ),
                    )
                self.records[key].update(outcome, finished_at=stamp())
                self._save(self.records[key])

    def list_runs(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                dict(record)
                for record in sorted(
                    self.records.values(), key=lambda r: r["submitted_at"], reverse=True
                )
            ]

    def get(self, key: str) -> dict[str, Any]:
        with self.lock:
            return dict(self.records[key])

    def view(self, key: str) -> ExperimentView:
        with self.lock:
            if self.records[key]["state"] != "COMPLETED":
                raise ValueError("Report is not ready")
            if key not in self.views:
                view = load_catalog(self.root / key / "result/catalog.json")[0].experiments[0]
                if not view.available or view.status != self.records[key]["status"]:
                    raise ValueError("Saved result is unavailable")
                self.views[key] = view
            return self.views[key]

    def verification(self, key: str) -> dict[str, Any]:
        self.view(key)
        return dict(read_json(self.root / key / "result/input.json"))

    def financials(self, key: str) -> list[dict[str, Any]]:
        self.get(key)
        directory = self.root / key / "financial"
        if directory.is_symlink():
            raise ValueError("Invalid financial directory")
        paths = sorted(directory.glob("*.json"))
        if any(p.is_symlink() or not re.fullmatch("[a-f0-9]{64}", p.stem) for p in paths):
            raise ValueError("Invalid financial history")
        if len(paths) > 10:
            raise ValueError("Financial assessment limit exceeded")
        return [{"id": path.stem, "report": read_json(path)["report"]} for path in paths]

    def assess_financial(
        self, key: str, values: dict[str, str], actor: str = "local:datavouch"
    ) -> str:
        with self.lock:
            document = financial_document(values, self.verification(key))
            report = assess(document)
            identifier = hashlib.sha256(encoded(document).encode()).hexdigest()
            directory = self.root / key / "financial"
            self.financials(key)  # Reject unsafe paths before writing retained evidence.
            directory.mkdir(mode=0o700, exist_ok=True)
            target = directory / (identifier + ".json")
            if not target.exists():
                if len(list(directory.glob("*.json"))) >= 10:
                    raise ValueError("Limit of ten financial assessments reached")
                self.audit(
                    "financial_assessed",
                    key,
                    actor,
                    self.records[key]["connection"],
                    report["status"],
                )
                temporary = directory / (identifier + ".tmp")
                temporary.write_text(encoded({"input": document, "report": report}))
                temporary.chmod(0o600)
                temporary.replace(target)
            return identifier

    def delete(self, key: str, actor: str = "local:datavouch") -> None:
        with self.lock:
            if self.records[key]["state"] == "RUNNING":
                raise RunBusy("A running experiment cannot be deleted")
            directory = self.root / key
            if directory.is_symlink():
                raise ValueError("Invalid run directory")
            self.audit("run_deleted", key, actor, self.records[key]["connection"])
            shutil.rmtree(directory)
            del self.records[key]
            self.views.pop(key, None)

    def close(self) -> None:
        with self.lock:
            self.closed = True
            worker = self.thread
        if worker is not None:
            worker.join()
        self.owner.close()


def measurement_rows(document: dict[str, Any]) -> list[dict[str, Any]]:
    experiment = document["comparison"]["experiment"]
    rows = []
    for side, observations in (
        ("Baseline", experiment["baseline"]["observations"]),
        ("Candidate", experiment["candidate"]),
    ):
        for index, observation in enumerate(observations, 1):
            rows.append(
                {
                    "cohort": side,
                    "index": index,
                    "successful": observation["execution"]["successful"],
                    "metrics": {
                        m["metric"]["name"]: m["value"] for m in observation["measurements"]
                    },
                }
            )
    return rows


def run_router(templates: Jinja2Templates, store: RunStore | None, allow_raw: bool) -> APIRouter:
    """Authenticated run history, status and result downloads."""
    from dataclasses import asdict

    from fastapi import HTTPException, Request
    from fastapi.responses import JSONResponse, RedirectResponse, Response

    router = APIRouter()
    token = secrets.token_urlsafe(32)

    def required_store() -> RunStore:
        if store is None:
            raise HTTPException(404, "Execution is disabled")
        return store

    @router.get("/runs")
    def history(request: Request, q: str = "", status: str = "") -> Response:
        if len(q) > 300 or status not in {"", "RUNNING", "ERROR", "PASS", "FAIL", "UNKNOWN"}:
            raise HTTPException(400, "Invalid run filter")
        runs = [
            r
            for r in required_store().list_runs()
            if principal(request).permits(r["connection"])
            if q.casefold() in (r["title"] + " " + r.get("workload", "")).casefold()
            and (not status or status == (r["status"] or r["state"]))
        ]
        return templates.TemplateResponse(
            request=request,
            name="runs.html",
            context={"title": "Experiment runs", "runs": runs, "q": q, "status": status},
        )

    def record(request: Request, key: str) -> dict[str, Any]:
        try:
            result = required_store().get(key)
            if not principal(request).permits(result["connection"]):
                raise KeyError(key)
            return result
        except KeyError as exc:
            raise HTTPException(404, "Run not found") from exc

    def report(request: Request, key: str) -> ExperimentView:
        record(request, key)
        try:
            return required_store().view(key)
        except (ValueError, OSError, KeyError) as exc:
            raise HTTPException(409, "Saved report is unavailable") from exc

    def render_detail(
        request: Request,
        key: str,
        financial_values: dict[str, str] | None = None,
        financial_error: str = "",
    ) -> Response:
        run = record(request, key)
        view = report(request, key) if run["state"] == "COMPLETED" else None
        return templates.TemplateResponse(
            request=request,
            name="run.html",
            context={
                "title": run["title"],
                "run": run,
                "experiment": view,
                "allow_raw_reports": allow_raw and principal(request).role != "viewer",
                "csrf": form_token(token, request),
                "financial_values": financial_values or {},
                "financial_error": financial_error,
                "financials": [
                    {**item, "sections": sections("finance", item["report"])}
                    for item in required_store().financials(key)
                ],
                "measurements": measurement_rows(required_store().verification(key))
                if view
                else [],
            },
            headers={"Refresh": "3"} if run["state"] == "RUNNING" else {},
            status_code=422 if financial_error else 200,
        )

    @router.get("/audit.json")
    def audit_download(request: Request) -> Response:
        user = administrator(request)
        return JSONResponse(
            [
                event
                for event in required_store().audit_events()
                if user.permits(event["connection"])
            ],
            headers={"Content-Disposition": 'attachment; filename="datavouch-audit.json"'},
        )

    @router.get("/runs/{key}")
    def detail(request: Request, key: str) -> Response:
        return render_detail(request, key)

    async def submitted(request: Request) -> dict[str, str]:
        if (
            request.headers.get("content-type", "").split(";")[0]
            != "application/x-www-form-urlencoded"
        ):
            raise HTTPException(415, "Expected a form")
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 65536:
                raise HTTPException(413, "Form exceeds 64 KiB")
        try:
            pairs = parse_qsl(body.decode(), keep_blank_values=True, max_num_fields=20)
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, "Invalid form") from exc
        values = dict(pairs)
        if len(values) != len(pairs) or not secrets.compare_digest(
            values.pop("csrf", "").encode(), form_token(token, request).encode()
        ):
            raise HTTPException(403, "Reload before submitting")
        return values

    @router.post("/runs/{key}/financial")
    async def financial(request: Request, key: str) -> Response:
        operator(request)
        record(request, key)
        values = await submitted(request)
        allowed = {
            "scope",
            "pricing_model",
            "currency",
            "rate",
            "pricing_reference",
            "valid_from",
            "valid_to",
            "baseline_billed_slot_hours",
            "candidate_billed_slot_hours",
            "financial_json",
            "confirmed",
        }
        if values.keys() - allowed or values.get("confirmed") != "yes":
            raise HTTPException(400, "Confirm the supplied pricing/evidence")
        try:
            required_store().assess_financial(key, values, principal(request).subject)
        except ValueError, TypeError, OSError, KeyError:
            return render_detail(
                request,
                key,
                values,
                "Check the pricing fields and UTC dates. Advanced evidence must match "
                "this experiment's windows and execution IDs. No assessment was saved.",
            )
        return RedirectResponse(f"/runs/{key}#financial", status_code=303)

    @router.post("/runs/{key}/delete")
    async def delete(request: Request, key: str) -> Response:
        administrator(request)
        record(request, key)
        values = await submitted(request)
        if values != {"confirmed": "yes"}:
            raise HTTPException(400, "Confirm deletion")
        try:
            required_store().delete(key, principal(request).subject)
        except (ValueError, OSError) as exc:
            raise HTTPException(409, "Run cannot be deleted") from exc
        return RedirectResponse("/runs", status_code=303)

    @router.get("/runs/{key}/financial/{identifier}.json")
    def financial_report(request: Request, key: str, identifier: str) -> Response:
        record(request, key)
        item = next(
            (item for item in required_store().financials(key) if item["id"] == identifier), None
        )
        if item is None:
            raise HTTPException(404, "Assessment not found")
        result = item["report"]
        if not allow_raw or principal(request).role == "viewer":
            result = {
                "status": result["status"],
                "sections": [asdict(s) for s in sections("finance", result)],
            }
        return JSONResponse(
            result,
            headers={"Content-Disposition": 'attachment; filename="datavouch-financial.json"'},
        )

    @router.get("/runs/{key}/status.json")
    def status(request: Request, key: str) -> Response:
        return JSONResponse(record(request, key))

    @router.get("/runs/{key}/summary.json")
    def summary(request: Request, key: str) -> Response:
        view = report(request, key)
        return JSONResponse(
            {
                "title": view.title,
                "status": view.status,
                "kind": view.kind,
                "synthetic": view.synthetic,
                "available": view.available,
                "sections": [asdict(s) for s in view.sections],
            },
            headers={"Content-Disposition": 'attachment; filename="datavouch-summary.json"'},
        )

    @router.get("/runs/{key}/report.json")
    def raw(request: Request, key: str) -> Response:
        if not allow_raw or principal(request).role == "viewer":
            raise HTTPException(403, "Full report access is disabled")
        return Response(
            report(request, key).raw,
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="datavouch-report.json"'},
        )

    return router
