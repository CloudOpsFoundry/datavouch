"""Browser plan validation shares CLI semantics without collecting cloud evidence."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from datavouch.adapters.bigquery.experiments import prepare
from datavouch.verification.evaluation import verify
from datavouch.web.app import create_app

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def client(tmp_path):
    config = tmp_path / "connections.json"
    config.write_text(
        json.dumps(
            {
                "connections": [
                    {
                        "id": "test",
                        "label": "Test project",
                        "project": "client-analytics",
                        "location": "us",
                        "maximum_bytes_billed": 200000000,
                        "timeout_seconds": 120,
                    },
                    {
                        "id": "second",
                        "label": "Second project",
                        "project": "client-staging",
                        "location": "eu",
                        "maximum_bytes_billed": 100000000,
                        "timeout_seconds": 60,
                    },
                ]
            }
        )
    )
    with TestClient(
        create_app(ROOT / "examples/viewer.json", "fixture-only-password", connections=config),
        base_url="http://127.0.0.1",
    ) as c:
        c.auth = ("datavouch", "fixture-only-password")
        yield c


@pytest.fixture
def form(client):
    html = client.get("/experiments/new").text
    token = re.search(r'name="csrf" value="([^"]+)"', html).group(1)
    return {
        "csrf": token,
        "connection": "test",
        "action": "validate",
        "id": "rewrite-1",
        "workload": "sales",
        "environment": "sandbox-platform-services/eu/test",
        "snapshot": "snapshot-1",
        "description": "Rewrite sales aggregation",
        "reference": "review-123",
        "statement": "Same snapshot and query parameters",
        "baseline_start": "2026-11-16T00:00:00",
        "baseline_end": "2026-11-17T00:00:00",
        "baseline_jobs": "baseline_1\nbaseline_2\nbaseline_3",
        "change_at": "2026-11-17T12:00:00",
        "candidate_start": "2026-11-18T00:00:00",
        "candidate_end": "2026-11-19T00:00:00",
        "candidate_jobs": "candidate_1\ncandidate_2\ncandidate_3",
        "minimum_samples": "3",
        "max_regression_percent": "5",
        "required_checks": "business_total",
        "max_failure_percent": "0",
        "max_increase_points": "0",
        "maximum_bytes_billed": "100000000",
        "timeout_seconds": "60",
    }


def test_download_is_cli_compatible_and_not_a_pass(client, form):
    preview = client.post("/experiments/new", data=form)
    assert preview.status_code == 200
    assert "Plan structure validated" in preview.text
    assert "not a PASS result" in preview.text
    response = client.post("/experiments/new", data={**form, "action": "download"})
    assert response.status_code == 200
    assert "attachment;" in response.headers["content-disposition"]
    plan = response.json()
    before, after, template, synthetic = prepare(plan)
    assert before.project == after.project == "client-analytics"
    assert before.location == after.location == "us"
    assert before.maximum_bytes_billed == 100_000_000
    assert plan["assurance"]["evidence"] == []
    assert plan["assurance"]["reliability"]["complete"] is False
    assert synthetic is False
    assert "UNKNOWN" in json.dumps(verify(template))
    opted_in = client.post(
        "/experiments/new",
        data={**form, "action": "download", "complete": "yes", "synthetic": "yes"},
    ).json()
    assert opted_in["assurance"]["reliability"]["complete"] is True
    assert opted_in["synthetic"] is True


@pytest.mark.parametrize(
    "field,value,message",
    [
        ("id", "", "Experiment name is required"),
        ("minimum_samples", "three", "must be a whole number"),
        ("minimum_samples", "0", "minimum_samples"),
        ("max_regression_percent", "fast", "must be a number"),
        ("max_regression_percent", "nan", "finite"),
        ("max_failure_percent", "101", "100"),
        ("maximum_bytes_billed", "1000000001", "deployment connection limit"),
        ("timeout_seconds", "301", "Timeout"),
        ("candidate_jobs", "baseline_1", "overlap"),
        ("candidate_jobs", "same\nsame", "Duplicate"),
        ("candidate_jobs", "../job", "Invalid job"),
        ("candidate_start", "2026-11-16T00:00:00", "chronological"),
        ("baseline_start", "2026-11-16", "UTC date and time"),
        ("required_checks", "total\ntotal", "distinct"),
    ],
)
def test_invalid_plans_preserve_input_and_prevent_download(client, form, field, value, message):
    response = client.post("/experiments/new", data={**form, field: value, "action": "download"})
    assert response.status_code == 422
    assert message.lower() in response.text.lower()
    assert "Rewrite sales aggregation" in response.text
    assert "content-disposition" not in response.headers


def test_form_boundaries(client, form):
    assert client.get("/experiments/new", auth=None).status_code == 401
    assert client.post("/experiments/new", data=form, auth=None).status_code == 401
    assert client.post("/experiments/new", data={**form, "csrf": "wrong"}).status_code == 403
    assert (
        client.post(
            "/experiments/new", data=form, headers={"Sec-Fetch-Site": "cross-site"}
        ).status_code
        == 403
    )
    assert client.post("/experiments/new", json=form).status_code == 415
    assert (
        client.post("/experiments/new", data={**form, "project": "other-project"}).status_code
        == 400
    )
    assert client.post("/experiments/new", data={**form, "complete": "true"}).status_code == 400
    assert client.post("/experiments/new", data={**form, "action": "execute"}).status_code == 400
    assert (
        client.post(
            "/experiments/new",
            content=b"x=" + b"a" * 65536,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 413
    )
    assert (
        client.post(
            "/experiments/new",
            content=b"csrf=a&csrf=b",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/experiments/new",
            content=b"csrf=\xff",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        ).status_code
        == 400
    )


def test_input_is_escaped_in_preview(client, form):
    response = client.post(
        "/experiments/new", data={**form, "description": "<script>alert(1)</script>"}
    )
    assert response.status_code == 200
    assert "<script>" not in response.text
    assert "&lt;script&gt;" in response.text


def test_connection_selection_and_limits(client, form):
    response = client.post(
        "/experiments/new", data={**form, "connection": "second", "action": "download"}
    )
    assert response.status_code == 200
    assert response.json()["baseline"]["project"] == "client-staging"
    assert response.json()["candidate"]["location"] == "eu"
    for update in (
        {"connection": "unknown"},
        {"connection": ""},
        {"maximum_bytes_billed": "200000001"},
        {"timeout_seconds": "121"},
    ):
        assert client.post("/experiments/new", data={**form, **update}).status_code == 422


def test_no_connection_fails_closed(form):
    with TestClient(
        create_app(ROOT / "examples/viewer.json", "fixture-only-password"),
        base_url="http://127.0.0.1",
    ) as client:
        client.auth = ("datavouch", "fixture-only-password")
        page = client.get("/experiments/new")
        assert "No connections configured" in page.text
        token = re.search(r'name="csrf" value="([^"]+)"', page.text).group(1)
        assert client.post("/experiments/new", data={**form, "csrf": token}).status_code == 422


@pytest.mark.parametrize(
    "field", ["baseline_start", "baseline_end", "change_at", "candidate_start", "candidate_end"]
)
def test_calendar_fields(client, form, field):
    html = client.get("/experiments/new").text
    assert re.search(r'<input type="datetime-local"[^>]+id="' + field + '"', html)
    response = client.post("/experiments/new", data={**form, "action": "download"})
    plan = response.json()
    value = (
        plan["change"]["at"]
        if field == "change_at"
        else plan[field.split("_")[0]][field.split("_")[1]]
    )
    assert value.endswith("Z")
    preview = client.post("/experiments/new", data=form)
    assert 'value="' + form[field] + '"' in preview.text


@pytest.mark.parametrize(
    "value",
    [
        "2026-02-30T10:00",
        "2026-11-16T24:00",
        "2026-11-16T00:00Z",
        "2026-11-16T00:00+04:00",
        "2026-11-16T00:00:00.123456",
        "2026-11-16 00:00",
    ],
)
def test_calendar_rejects_invalid_or_ambiguous_values(client, form, value):
    response = client.post("/experiments/new", data={**form, "baseline_start": value})
    assert response.status_code == 422
    assert "UTC date and time" in response.text


def test_calendar_minutes_and_milliseconds_preserved(client, form):
    form.update(
        baseline_start="2026-11-16T00:00",
        candidate_end="2026-11-19T00:00:00.123",
        action="download",
    )
    result = client.post("/experiments/new", data=form)
    assert result.status_code == 200
    assert result.json()["baseline"]["start"] == "2026-11-16T00:00:00Z"
    assert result.json()["candidate"]["end"] == "2026-11-19T00:00:00.123000Z"
