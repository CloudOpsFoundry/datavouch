"""Execution lifecycle with real CLI fixture replay and no cloud access."""

import json
import sqlite3
import subprocess
import threading
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from datavouch.adapters.bigquery.experiments import run_command
from datavouch.web.app import create_app
from datavouch.web.runs import RunBusy, RunStore

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples/bigquery/experiment"


@pytest.fixture
def setup(tmp_path, monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, tzinfo=UTC)

    monkeypatch.setattr("datavouch.web.runs.datetime", Clock)
    config = tmp_path / "connections.json"
    config.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "id": "test",
                        "label": "Test",
                        "project": "synthetic-project",
                        "location": "eu",
                        "maximum_bytes_billed": 100000000,
                        "timeout_seconds": 60,
                    }
                ]
            }
        )
    )
    plan = json.loads((EXAMPLES / "plan.json").read_text())
    return tmp_path / "runs", config, plan


def fixture_worker(monkeypatch, candidate="candidate-jobs.json"):
    def execute(command, **kwargs):
        assert command[1:4] == ["-m", "datavouch", "run-bigquery"]
        assert command[5:7] == ["--live", "--output-dir"]
        assert kwargs["timeout"] == 150
        assert kwargs["shell"] is False
        code = run_command(
            Path(command[4]),
            Path(command[7]),
            [EXAMPLES / "baseline-jobs.json", EXAMPLES / candidate],
            False,
        )
        return SimpleNamespace(returncode=code)

    monkeypatch.setattr("datavouch.web.runs.subprocess.run", execute)


def finish(store):
    store.thread.join(timeout=5)
    assert not store.thread.is_alive()


def test_persistent_result_and_duplicate_suppression(setup, monkeypatch):
    root, config, plan = setup
    fixture_worker(monkeypatch)
    store = RunStore(root, config)
    try:
        key = store.submit(plan, "test")
        finish(store)
        assert store.get(key)["state"] == "COMPLETED"
        assert store.get(key)["status"] == "PASS"
        assert store.submit(plan, "test") == key
        assert len(store.list_runs()) == 1
        assert store.view(key).raw == (root / key / "result/report.json").read_bytes()
    finally:
        store.close()
    restored = RunStore(root, config)
    try:
        assert restored.view(key).status == "PASS"
        assert restored.submit(plan, "test") == key
    finally:
        restored.close()


def test_busy_and_reauthorization(setup, monkeypatch):
    root, config, plan = setup
    started, release = threading.Event(), threading.Event()

    def execute(*args, **kwargs):
        started.set()
        assert release.wait(5)
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr("datavouch.web.runs.subprocess.run", execute)
    store = RunStore(root, config)
    try:
        key = store.submit(plan, "test")
        assert started.wait(5)
        assert store.submit(plan, "test") == key
        with pytest.raises(RunBusy):
            store.submit({**plan, "id": "another"}, "test")
        config.write_text('{"connections": []}')
        with pytest.raises(ValueError):
            store.submit(plan, "test")
    finally:
        release.set()
        store.close()
    assert store.get(key)["state"] == "ERROR"


@pytest.mark.parametrize("mode", ["failure", "timeout", "exception", "bad-output"])
def test_worker_failures_are_not_pass(setup, monkeypatch, mode):
    root, config, plan = setup

    def execute(*args, **kwargs):
        if mode == "timeout":
            raise subprocess.TimeoutExpired("private-command", 150)
        if mode == "exception":
            raise RuntimeError("SECRET SHOULD NEVER APPEAR")
        return SimpleNamespace(returncode=0 if mode == "bad-output" else 2)

    monkeypatch.setattr("datavouch.web.runs.subprocess.run", execute)
    store = RunStore(root, config)
    try:
        key = store.submit(plan, "test")
        finish(store)
        assert store.get(key)["state"] == "ERROR"
        assert store.get(key)["status"] == ""
        assert "SECRET" not in json.dumps(store.list_runs())
        assert store.submit(plan, "test") == key
    finally:
        store.close()


def test_scope_budget_and_closed_windows(setup):
    root, config, original = setup
    store = RunStore(root, config)
    try:
        for field, value in [
            ("project", "different-project"),
            ("location", "us"),
            ("maximum_bytes_billed", 100000001),
            ("timeout_seconds", 61),
            ("end", "2026-11-21T00:00:00Z"),
        ]:
            plan = json.loads(json.dumps(original))
            for side in ("baseline", "candidate"):
                if field != "end" or side == "candidate":
                    plan[side][field] = value
            with pytest.raises(ValueError):
                store.submit(plan, "test")
        assert not store.list_runs()
    finally:
        store.close()


def test_private_directory_owner_and_restart_recovery(setup):
    root, config, plan = setup
    root.mkdir(mode=0o755)
    with pytest.raises(ValueError, match="private"):
        RunStore(root, config)
    root.chmod(0o700)
    first = RunStore(root, config)
    with pytest.raises(sqlite3.OperationalError):
        RunStore(root, config)
    first.close()
    key = "a" * 64
    directory = root / key
    directory.mkdir()
    (directory / "state.json").write_text(
        json.dumps(
            {
                "id": key,
                "title": "Interrupted",
                "connection": "test",
                "finished_at": "",
                "message": "Interrupted",
                "state": "RUNNING",
                "submitted_at": "2026-11-18",
                "status": "",
            }
        )
    )
    restored = RunStore(root, config)
    try:
        assert restored.get(key)["state"] == "ERROR"
        assert "No automatic retry" in restored.get(key)["message"]
    finally:
        restored.close()


def test_execution_routes_default_disabled():
    with TestClient(
        create_app(ROOT / "examples/viewer.json", "fixture-only-password"),
        base_url="http://127.0.0.1",
    ) as client:
        client.auth = ("datavouch", "fixture-only-password")
        assert client.get("/runs").status_code == 404
        assert "Run experiment</button>" not in client.get("/experiments/new").text


def test_saved_result_routes(setup, monkeypatch):
    root, config, plan = setup
    fixture_worker(monkeypatch)
    store = RunStore(root, config)
    key = store.submit(plan, "test")
    finish(store)
    store.close()
    app = create_app(
        ROOT / "examples/viewer.json",
        "fixture-only-password",
        connections=config,
        run_directory=root,
        enable_live_execution=True,
    )
    with TestClient(app, base_url="http://127.0.0.1") as client:
        client.auth = ("datavouch", "fixture-only-password")
        assert client.get("/runs", auth=None).status_code == 401
        assert client.get("/runs").status_code == 200
        detail = client.get("/runs/" + key)
        assert detail.status_code == 200
        assert "PASS" in detail.text
        assert "refresh" not in detail.headers
        assert client.get("/runs/" + key + "/status.json").json()["state"] == "COMPLETED"
        assert client.get("/runs/" + key + "/summary.json").json()["status"] == "PASS"
        assert client.get("/runs/" + key + "/report.json").status_code == 403
        assert client.get("/runs/nonexistent").status_code == 404


def browser_form(client, plan):
    import re

    from datavouch.web.planner import FIELDS

    page = client.get("/experiments/new")
    values = {name: default for name, _, _, default in FIELDS}
    values.update(
        csrf=re.search(r'name="csrf" value="([^"]+)"', page.text).group(1),
        action="run",
        confirm_run="yes",
        connection="test",
        id=plan["id"],
        workload=plan["baseline"]["workload"]["id"],
        environment=plan["baseline"]["workload"]["environment"],
        snapshot=plan["baseline"]["workload"]["input_snapshot"],
        description=plan["change"]["description"],
        change_at=plan["change"]["at"].removesuffix("Z"),
        reference=plan["comparability"]["reference"],
        statement=plan["comparability"]["statement"],
        complete="yes",
        synthetic="yes",
    )
    for side in ("baseline", "candidate"):
        values[side + "_start"] = plan[side]["start"].removesuffix("Z")
        values[side + "_end"] = plan[side]["end"].removesuffix("Z")
        values[side + "_jobs"] = "\n".join(plan[side]["job_ids"])
    return values


@pytest.mark.parametrize(
    "candidate,expected",
    [("candidate-jobs.json", "UNKNOWN"), ("candidate-failed-jobs.json", "FAIL")],
)
def test_browser_submit_through_result(setup, monkeypatch, candidate, expected):
    root, config, plan = setup
    fixture_worker(monkeypatch, candidate)
    finished = threading.Event()
    original = RunStore._execute

    def execute(self, *args):
        try:
            original(self, *args)
        finally:
            finished.set()

    monkeypatch.setattr(RunStore, "_execute", execute)
    app = create_app(
        ROOT / "examples/viewer.json",
        "fixture-only-password",
        connections=config,
        run_directory=root,
        enable_live_execution=True,
        allow_raw_reports=True,
    )
    with TestClient(app, base_url="http://127.0.0.1", follow_redirects=False) as client:
        client.auth = ("datavouch", "fixture-only-password")
        form = browser_form(client, plan)
        assert client.post("/experiments/new", data=form, auth=None).status_code == 401
        assert client.post("/experiments/new", data={**form, "confirm_run": ""}).status_code == 403
        assert client.post("/experiments/new", data={**form, "csrf": "wrong"}).status_code == 403
        assert (
            client.post(
                "/experiments/new", data=form, headers={"Sec-Fetch-Site": "cross-site"}
            ).status_code
            == 403
        )
        assert not list(root.glob("*/plan.json"))
        response = client.post("/experiments/new", data=form)
        assert response.status_code == 303
        assert finished.wait(5)
        url = response.headers["location"]
        assert client.get(url).status_code == 200
        summary = client.get(url + "/summary.json")
        assert summary.json()["status"] == expected
        assert "execution_ids" not in summary.text
        raw = client.get(url + "/report.json")
        assert raw.content == (root / url.split("/")[-1] / "result/report.json").read_bytes()
        repeated = client.post("/experiments/new", data=form)
        assert repeated.headers["location"] == url
        assert len(list(root.glob("*/plan.json"))) == 1


def test_recheck_inside_worker_and_capacity(setup, monkeypatch):
    root, config, plan = setup
    store = RunStore(root, config)
    original = store._authorize
    calls = 0

    def authorize(*args):
        nonlocal calls
        calls += 1
        if calls > 1:
            raise ValueError("Revoked")
        return original(*args)

    monkeypatch.setattr(store, "_authorize", authorize)

    def unexpected(*args, **kwargs):
        pytest.fail("Revoked scope must not start a worker process")

    monkeypatch.setattr("datavouch.web.runs.subprocess.run", unexpected)
    try:
        key = store.submit(plan, "test")
        finish(store)
        assert store.get(key)["state"] == "ERROR"
        monkeypatch.setattr(store, "_authorize", original)
        monkeypatch.setattr("datavouch.web.runs.MAX_RUNS", 1)
        with pytest.raises(RunBusy, match="history is full"):
            store.submit({**plan, "id": "new"}, "test")
    finally:
        store.close()
    with pytest.raises(RunBusy, match="shutting down"):
        store.submit(plan, "test")


def test_running_page_and_busy_submission(setup, monkeypatch):
    root, config, plan = setup
    release = threading.Event()

    def execute(*args, **kwargs):
        assert release.wait(5)
        return SimpleNamespace(returncode=2)

    monkeypatch.setattr("datavouch.web.runs.subprocess.run", execute)
    app = create_app(
        ROOT / "examples/viewer.json",
        "fixture-only-password",
        connections=config,
        run_directory=root,
        enable_live_execution=True,
    )
    with TestClient(app, base_url="http://127.0.0.1", follow_redirects=False) as client:
        client.auth = ("datavouch", "fixture-only-password")
        try:
            form = browser_form(client, plan)
            response = client.post("/experiments/new", data=form)
            url = response.headers["location"]
            page = client.get(url)
            assert page.headers["refresh"] == "3"
            assert "RUNNING" in page.text
            assert client.get(url + "/summary.json").status_code == 409
            busy = client.post("/experiments/new", data={**form, "id": "another"})
            assert busy.status_code == 409
            assert "nothing was queued" in busy.text
            config.write_text('{"connections": []}')
            denied = client.post("/experiments/new", data={**form, "id": "revoked"})
            assert denied.status_code == 422
            assert "Select a connection approved" in denied.text
        finally:
            release.set()


def test_execution_requires_explicit_configuration():
    with pytest.raises(ValueError, match="requires connections"):
        create_app(
            ROOT / "examples/viewer.json", "fixture-only-password", enable_live_execution=True
        )
