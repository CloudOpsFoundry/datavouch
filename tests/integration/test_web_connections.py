"""Deployment configuration validation is independent of cloud credentials."""

import json

import pytest

from datavouch.web.connections import load_connections

ROW = {
    "id": "analytics",
    "label": "Analytics",
    "project": "client-analytics",
    "location": "eu",
    "maximum_bytes_billed": 100000000,
    "timeout_seconds": 60,
}


def test_valid_connections(tmp_path):
    assert load_connections(None) == ()
    path = tmp_path / "connections.json"
    path.write_text(json.dumps({"connections": [ROW]}))
    assert load_connections(path)[0].project == "client-analytics"


@pytest.mark.parametrize(
    "document",
    [
        {},
        {"connections": [ROW, ROW]},
        {"connections": [{**ROW, "project": "INVALID PROJECT"}]},
        {"connections": [{**ROW, "location": "EU"}]},
        {"connections": [{**ROW, "id": ""}]},
        {"connections": [{**ROW, "label": 123}]},
        {"connections": [{**ROW, "credential": "not-allowed"}]},
        {"connections": [{**ROW, "maximum_bytes_billed": 0}]},
        {"connections": [{**ROW, "timeout_seconds": 301}]},
        {"connections": [ROW] * 101},
    ],
)
def test_invalid_connections(tmp_path, document):
    path = tmp_path / "connections.json"
    path.write_text(json.dumps(document))
    with pytest.raises(ValueError):
        load_connections(path)


def test_bounded_and_unique_json(tmp_path):
    path = tmp_path / "connections.json"
    for content in ("x" * 65537, '{"connections":[],"connections":[]}'):
        path.write_text(content)
        with pytest.raises(ValueError):
            load_connections(path)


def test_empty_connections_disable_planning(tmp_path):
    from pathlib import Path

    from fastapi.testclient import TestClient

    from datavouch.web.app import create_app

    path = tmp_path / "connections.json"
    path.write_text('{"connections": []}')
    assert load_connections(path) == ()
    catalog = Path(__file__).resolve().parents[2] / "examples/viewer.json"
    with TestClient(
        create_app(catalog, "fixture-only-password", connections=path), base_url="http://127.0.0.1"
    ) as client:
        client.auth = ("datavouch", "fixture-only-password")
        page = client.get("/experiments/new")
        assert page.status_code == 200
        assert "No connections configured" in page.text
