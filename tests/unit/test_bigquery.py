import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from datavouch.adapters.bigquery.collector import collect_rows
from datavouch.adapters.bigquery.files import load_config, load_fixture, render_collection
from datavouch.adapters.bigquery.models import CollectionError, timestamp
from datavouch.adapters.bigquery.queries import metadata_query

ROOT = Path(__file__).resolve().parents[2] / "examples/bigquery"


@pytest.fixture
def config():
    return load_config(ROOT / "collection_config.json")


@pytest.fixture
def rows():
    return json.loads((ROOT / "jobs.json").read_text())


def test_fixture_produces_core_observations(config):
    result = load_fixture(ROOT / "jobs.json", config)
    assert result.eligible
    observation = result.jobs[0].observation
    assert observation.workload == config.workload
    assert {m.metric.name: m.value for m in observation.measurements} == {
        "runtime": 1000,
        "slot_time": 1000,
        "processed_bytes": 1048576,
        "billed_bytes": 10485760,
    }
    assert observation.execution.id == "synthetic-project/us/baseline_1"
    assert observation.input_units is None


def test_missing_optional_metrics_are_not_zero(config, rows):
    for row in rows:
        for name in ("total_slot_ms", "total_bytes_processed", "total_bytes_billed"):
            row.pop(name)
    result = collect_rows(rows, config)
    assert result.eligible
    assert [m.metric.name for m in result.jobs[0].observation.measurements] == ["runtime"]


@pytest.mark.parametrize(
    "updates,reason",
    [
        ({"failure_reason": "invalidQuery"}, "Job failed"),
        ({"job_type": "LOAD"}, "standalone SELECT"),
        ({"statement_type": "SCRIPT"}, "standalone SELECT"),
        ({"statement_type": "INSERT"}, "standalone SELECT"),
        ({"parent_job_id": "parent"}, "standalone SELECT"),
        ({"state": "RUNNING", "end_time": None}, "not complete"),
        ({"state": "PENDING", "start_time": None}, "not complete"),
        ({"cache_hit": True}, "Cached"),
        ({"cache_hit": None}, "Cache status"),
        ({"fingerprint": None}, "fingerprint"),
        ({"end_time": None}, "timestamps"),
    ],
)
def test_ineligible_rows_are_retained(config, rows, updates, reason):
    rows[0].update(updates)
    result = collect_rows(rows, config)
    assert not result.eligible
    assert len(result.jobs) == 3
    assert result.jobs[0].observation is None
    assert any(reason in issue for issue in result.jobs[0].issues)


@pytest.mark.parametrize("field", ["failure_reason", "parent_job_id"])
def test_missing_critical_metadata_is_ineligible(config, rows, field):
    rows[0].pop(field)
    assert not collect_rows(rows, config).eligible


@pytest.mark.parametrize(
    "updates",
    [
        {"project_id": "other-project"},
        {"location": "eu"},
        {"job_id": "unrequested"},
        {"creation_time": "2026-11-17T00:00:00Z"},
        {"creation_time": None},
        {"state": None},
        {"failure_reason": "personal details!"},
        {"fingerprint": "SQL text"},
        {"start_time": "2026-11-15T00:00:00Z"},
        {"end_time": "2026-11-16T10:00:00Z"},
        {"total_slot_ms": -1},
        {"total_slot_ms": True},
        {"total_bytes_billed": 1.5},
        {"total_bytes_processed": 2**63},
    ],
)
def test_bad_metadata_rejected(config, rows, updates):
    rows[0].update(updates)
    with pytest.raises(ValueError):
        collect_rows(rows, config)


def test_missing_duplicate_and_bounded_records(config, rows):
    result = collect_rows(rows[:1], config)
    assert not result.eligible
    assert result.missing_job_ids == ("baseline_2", "baseline_3")
    assert not collect_rows([], config).eligible
    with pytest.raises(CollectionError, match="Duplicate"):
        collect_rows([rows[0], rows[0]], config)
    with pytest.raises(CollectionError, match="exceeded"):
        collect_rows(rows + rows, config)


def test_multiple_fingerprints_are_explicit_groups(config, rows):
    rows[0]["fingerprint"] = "bbbb"
    result = collect_rows(rows, config)
    assert not result.eligible
    data = json.loads(render_collection(result))
    assert data["fingerprint_groups"] == {
        "bbbb": ["baseline_1"],
        "a1b2c3": ["baseline_2", "baseline_3"],
    }


def test_sensitive_fields_are_never_serialized(config, rows):
    rows[0].update(
        query="sensitive SQL", user_email="user@example.test", error_result={"message": "private"}
    )
    result = render_collection(collect_rows(rows, config))
    assert all(secret not in result for secret in ("sensitive SQL", "user@example.test", "private"))
    assert result == render_collection(collect_rows(reversed(rows), config))


@pytest.mark.parametrize(
    "changes",
    [
        {"project": "injected`"},
        {"project": ""},
        {"location": "US"},
        {"location": "us`"},
        {"job_ids": ()},
        {"job_ids": ["job"]},
        {"job_ids": ("job", "job")},
        {"job_ids": ("injected'",)},
        {"job_ids": tuple(str(i) for i in range(101))},
        {"workload": None},
        {"maximum_bytes_billed": True},
        {"maximum_bytes_billed": 0},
        {"maximum_bytes_billed": 10**9 + 1},
        {"timeout_seconds": 0},
        {"timeout_seconds": 301},
        {"start": datetime(2026, 1, 1)},
        {"end": datetime(2026, 1, 1, tzinfo=UTC)},
        {"end": datetime(2026, 12, 20, tzinfo=UTC)},
    ],
)
def test_invalid_config(config, changes):
    with pytest.raises(ValueError):
        replace(config, **changes)


def test_live_retention_bounds(config):
    config.validate_live_window(config.end)
    with pytest.raises(CollectionError):
        config.validate_live_window(config.end - timedelta(seconds=1))
    with pytest.raises(CollectionError):
        config.validate_live_window(config.start + timedelta(days=181))
    assert timestamp("2026-11-16T04:00:00+04:00") == config.start


def test_fixed_read_only_query_is_bounded(config):
    query = metadata_query(config)
    assert query.startswith("SELECT")
    assert "INFORMATION_SCHEMA.JOBS_BY_PROJECT" in query
    assert "creation_time >= @start_time AND creation_time < @end_time" in query
    assert "job_id IN UNNEST(@job_ids)" in query
    assert "LIMIT @row_limit" in query
    assert "user_email" not in query
    assert "error_result.message" not in query
    assert "baseline_1" not in query


@pytest.mark.parametrize("contents", ["{}", "[null]", '{"x":1,"x":2}', "x", " " * 5_000_001])
def test_invalid_fixture_file(config, tmp_path, contents):
    path = tmp_path / "bad.json"
    path.write_text(contents)
    with pytest.raises(ValueError):
        load_fixture(path, config)


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(extra=1),
        lambda d: d.update(job_ids="job"),
        lambda d: d.update(workload=[]),
        lambda d: d.pop("start"),
    ],
)
def test_invalid_config_file(tmp_path, change):
    data = json.loads((ROOT / "collection_config.json").read_text())
    change(data)
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_config(path)
