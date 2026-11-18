"""Ticket-sales onboarding uses real decisions and respects existing access boundaries."""

import importlib.util
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from google.api_core.exceptions import NotFound

from datavouch.adapters.bigquery.collector import collect_rows
from datavouch.demo import run_demo
from datavouch.web.app import create_app
from datavouch.web.catalog import load_catalog

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "ticket_example", ROOT / "examples/bigquery/ticket_sales.py"
)
example = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(example)


def test_guided_story_uses_measured_reports_and_honest_empty_state(tmp_path):
    output = tmp_path / "demo"
    run_demo(output, 100)
    with TestClient(
        create_app(output / "catalog.json", "fixture-only-password"), base_url="http://127.0.0.1"
    ) as client:
        assert client.get("/guide/ticket-sales").status_code == 401
        client.auth = ("datavouch", "fixture-only-password")
        page = client.get("/guide/ticket-sales")
        assert page.status_code == 200
        assert "€555,000" in page.text and "€240,000" in page.text
        assert "measured local example" in page.text
        assert "smaller local examples have different totals" in page.text
        for scenario in example.TITLES:
            assert f"/workloads/ticket-sales/experiments/{scenario}" in page.text
        wrong = client.get("/workloads/ticket-sales/experiments/incorrect")
        assert "Do not approve this change" in wrong.text
        assert "Ticket sales total:" in wrong.text
        missing = client.get("/workloads/ticket-sales/experiments/missing-evidence")
        assert "Ticket sales total:" in missing.text
        assert "UNKNOWN" in missing.text
    with TestClient(
        create_app(ROOT / "examples/web/empty-catalog.json", "fixture-only-password"),
        base_url="http://127.0.0.1",
    ) as client:
        client.auth = ("datavouch", "fixture-only-password")
        assert "No measured ticket-sales examples" in client.get("/guide/ticket-sales").text


def test_gateway_story_never_exposes_startup_catalog(tmp_path):
    output = tmp_path / "demo"
    run_demo(output, 100)
    config = tmp_path / "gateway.json"
    config.write_text(
        json.dumps(
            {
                "allowed_hosts": ["datavouch.example.test"],
                "trusted_proxy_networks": ["127.0.0.1/32"],
                "principals": {"reader": {"role": "viewer", "connections": []}},
            }
        )
    )
    secret = "fixture-only-gateway-secret-for-tests"
    with TestClient(
        create_app(output / "catalog.json", "", gateway_config=config, gateway_secret=secret),
        base_url="https://datavouch.example.test",
        client=("127.0.0.1", 12345),
    ) as client:
        page = client.get(
            "/guide/ticket-sales",
            headers={"X-DataVouch-Gateway-Token": secret, "X-Auth-Request-User": "reader"},
        )
        assert page.status_code == 200
        assert "No measured ticket-sales examples" in page.text
        assert "/workloads/ticket-sales/experiments/" not in page.text
        assert "Create your own experiment" not in page.text


def test_bigquery_example_with_sdk_boundary_mock_and_real_verifier(tmp_path, monkeypatch):
    jobs = {}
    collection_calls = []

    class Client:
        def __init__(self, *, project, location):
            assert project == "client-project" and location == "eu"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def get_job(self, identity, **kwargs):
            if identity not in jobs:
                raise NotFound("fixture missing")
            return jobs[identity]

        def query(self, sql, *, job_id, job_config, **kwargs):
            assert kwargs["retry"] is None and kwargs["job_retry"] is None
            assert job_config.use_query_cache is False
            assert job_config.maximum_bytes_billed == 10000000
            created = datetime(2026, 11, 16, tzinfo=UTC) + timedelta(seconds=3 * len(jobs))
            total = 24000000 if "_incorrect_" in job_id else 55500000
            job = SimpleNamespace(
                query=sql,
                use_query_cache=False,
                cache_hit=False,
                created=created,
                ended=created + timedelta(seconds=1),
                result=lambda **kw: [{"ticket_sales_cents": total}],
            )
            jobs[job_id] = job
            return job

    def collect(config):
        collection_calls.append(config)
        rows = []
        for identity in config.job_ids:
            job = jobs[identity]
            rows.append(
                {
                    "project_id": config.project,
                    "location": config.location,
                    "job_id": identity,
                    "creation_time": job.created.isoformat(),
                    "start_time": job.created.isoformat(),
                    "end_time": job.ended.isoformat(),
                    "job_type": "QUERY",
                    "statement_type": "SELECT",
                    "parent_job_id": None,
                    "state": "DONE",
                    "cache_hit": False,
                    "failure_reason": None,
                    "fingerprint": "a1b2c3",
                    "total_slot_ms": 1000,
                    "total_bytes_processed": 0,
                    "total_bytes_billed": 0,
                }
            )
        return collect_rows(rows, config, source="fixture")

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 20, tzinfo=UTC)

    monkeypatch.setattr("google.cloud.bigquery.Client", Client)
    monkeypatch.setattr("datavouch.adapters.bigquery.client.collect_live", collect)
    monkeypatch.setattr("datavouch.adapters.bigquery.experiments.datetime", Clock)
    output = tmp_path / "bigquery"
    example.execute("client-project", "eu", "sample", output)
    assert len(jobs) == 9 and len(collection_calls) == 6
    catalog = load_catalog(output / "catalog.json")
    assert {e.id: e.status for e in catalog[0].experiments} == {
        "equivalent": "PASS",
        "incorrect": "FAIL",
        "missing-evidence": "UNKNOWN",
    }
    assert catalog[0].id == "ticket-sales"
    assert all(c.project == "client-project" and c.location == "eu" for c in collection_calls)
    with pytest.raises(FileExistsError):
        example.execute("client-project", "eu", "sample", output)
    assert len(collection_calls) == 6
    jobs[next(iter(jobs))].query = "unexpected SQL"
    with pytest.raises(ValueError, match="Existing job differs"):
        example.execute("client-project", "eu", "sample", tmp_path / "conflict")


@pytest.mark.parametrize(
    "project,location,run_id",
    [
        ("bad project", "eu", "test"),
        ("client-project", "EU", "test"),
        ("client-project", "eu", "../unsafe"),
    ],
)
def test_example_rejects_invalid_scope_before_cloud_access(tmp_path, project, location, run_id):
    with pytest.raises(ValueError):
        example.execute(project, location, run_id, tmp_path / "invalid")
    assert not (tmp_path / "invalid").exists()


def test_example_requires_explicit_live_authorization(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples/bigquery/ticket_sales.py"),
            "--project",
            "client-project",
            "--location",
            "eu",
            "--run-id",
            "test",
            "--output-dir",
            str(tmp_path / "demo"),
        ],
        capture_output=True,
    )
    assert result.returncode == 2
    assert b"--live" in result.stderr
    assert not (tmp_path / "demo").exists()


def test_story_lists_only_permitted_ticket_runs(tmp_path, monkeypatch):
    config = tmp_path / "connections.json"
    config.write_text('{"connections": []}')
    gateway = tmp_path / "gateway.json"
    secret = "fixture-only-gateway-secret-for-tests"
    gateway.write_text(
        json.dumps(
            {
                "allowed_hosts": ["datavouch.example.test"],
                "trusted_proxy_networks": ["127.0.0.1/32"],
                "principals": {"reader": {"role": "viewer", "connections": ["one"]}},
            }
        )
    )
    records = [
        {
            "id": "a" * 64,
            "title": "Permitted ticket example",
            "workload": "ticket-sales",
            "connection": "one",
            "status": "PASS",
            "state": "COMPLETED",
        },
        {
            "id": "b" * 64,
            "title": "Hidden ticket example",
            "workload": "ticket-sales",
            "connection": "two",
            "status": "FAIL",
            "state": "COMPLETED",
        },
        {
            "id": "c" * 64,
            "title": "Unrelated example",
            "workload": "other",
            "connection": "one",
            "status": "PASS",
            "state": "COMPLETED",
        },
    ]
    monkeypatch.setattr("datavouch.web.runs.RunStore.list_runs", lambda self: records)
    app = create_app(
        ROOT / "examples/web/empty-catalog.json",
        "",
        connections=config,
        run_directory=tmp_path / "runs",
        enable_live_execution=True,
        gateway_config=gateway,
        gateway_secret=secret,
    )
    with TestClient(
        app, base_url="https://datavouch.example.test", client=("127.0.0.1", 12345)
    ) as client:
        page = client.get(
            "/guide/ticket-sales",
            headers={"X-DataVouch-Gateway-Token": secret, "X-Auth-Request-User": "reader"},
        )
        assert page.status_code == 200
        assert "Permitted ticket example" in page.text
        assert "Hidden ticket example" not in page.text
        assert "Unrelated example" not in page.text
