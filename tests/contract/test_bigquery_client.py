"""Exercise real SDK configuration with a mocked transport and no credentials."""

import builtins
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from google.api_core.exceptions import BadRequest, Forbidden, Unauthorized
from google.auth.exceptions import DefaultCredentialsError, RefreshError
from google.cloud import bigquery

from datavouch.adapters.bigquery import client
from datavouch.adapters.bigquery.files import load_config
from datavouch.adapters.bigquery.models import CollectionError

ROOT = Path(__file__).resolve().parents[2] / "examples/bigquery"


@pytest.fixture
def transport(monkeypatch):
    class Clock:
        @staticmethod
        def now(zone):
            return datetime(2026, 11, 17, 12, tzinfo=UTC)

    monkeypatch.setattr(client, "datetime", Clock)
    factory = MagicMock()
    connection = factory.return_value.__enter__.return_value
    connection.query.return_value.result.return_value = []
    monkeypatch.setattr(bigquery, "Client", factory)
    return factory, connection


def test_sdk_parameters_and_budgets(transport):
    factory, connection = transport
    config = load_config(ROOT / "collection_config.json")
    result = client.collect_live(config)
    assert not result.eligible
    assert result.source == "bigquery"
    factory.assert_called_once_with(project=config.project, location="us")
    kwargs = connection.query.call_args.kwargs
    assert kwargs["retry"] is None and kwargs["job_retry"] is None
    assert kwargs["timeout"] == 60 and kwargs["location"] == "us"
    api = kwargs["job_config"].to_api_repr()
    assert api["query"]["useLegacySql"] is False
    assert api["query"]["useQueryCache"] is False
    assert int(api["query"]["maximumBytesBilled"]) == 100_000_000
    assert int(api["jobTimeoutMs"]) == 60_000
    params = {p["name"]: p for p in api["query"]["queryParameters"]}
    assert params["job_ids"]["parameterValue"]["arrayValues"] == [
        {"value": j} for j in config.job_ids
    ]
    assert params["row_limit"]["parameterValue"]["value"] == "4"
    result_kwargs = connection.query.return_value.result.call_args.kwargs
    assert result_kwargs["page_size"] == 101 and result_kwargs["max_results"] == 4
    assert 0 < result_kwargs["timeout"] <= 60
    assert result_kwargs["retry"] is None and result_kwargs["job_retry"] is None
    factory.return_value.__exit__.assert_called_once()


def test_live_rows_use_shared_conversion(transport):
    import json

    _, connection = transport
    connection.query.return_value.result.return_value = json.loads((ROOT / "jobs.json").read_text())
    result = client.collect_live(load_config(ROOT / "collection_config.json"))
    assert result.eligible
    assert len(result.jobs) == 3


@pytest.mark.parametrize(
    "error,expected",
    [
        (Forbidden("sensitive response"), "access denied"),
        (Unauthorized("sensitive response"), "access denied"),
        (DefaultCredentialsError("sensitive response"), "Credentials"),
        (RefreshError("sensitive response"), "Credentials"),
        (TimeoutError("sensitive response"), "timed out"),
        (BadRequest("sensitive response"), "request failed"),
    ],
)
def test_safe_transport_failures(transport, error, expected):
    _, connection = transport
    connection.query.side_effect = error
    with pytest.raises(CollectionError, match=expected) as caught:
        client.collect_live(load_config(ROOT / "collection_config.json"))
    assert "sensitive" not in str(caught.value)


def test_result_permission_failure(transport):
    _, connection = transport
    connection.query.return_value.result.side_effect = Forbidden("secret")
    with pytest.raises(CollectionError, match="access denied"):
        client.collect_live(load_config(ROOT / "collection_config.json"))


def test_deadline_expired_before_result(transport, monkeypatch):
    times = iter([0.0, 61.0])
    monkeypatch.setattr(client.time, "monotonic", lambda: next(times))
    with pytest.raises(CollectionError, match="timed out"):
        client.collect_live(load_config(ROOT / "collection_config.json"))
    transport[1].query.return_value.result.assert_not_called()


def test_optional_dependency_missing(transport, monkeypatch):
    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "google.api_core.exceptions":
            raise ImportError
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(CollectionError, match=r"datavouch\[bigquery\]"):
        client.collect_live(load_config(ROOT / "collection_config.json"))
