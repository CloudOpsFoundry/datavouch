"""Local viewer boundaries and parity with the public CLI."""

import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient as StarletteClient

from datavouch.web.app import create_app
from datavouch.web.catalog import load_catalog
from datavouch.web.commands import serve_command

ROOT = Path(__file__).resolve().parents[2]
AUTH = ("datavouch", "fixture-only-password")
BASE = "/workloads/daily-summary/experiments/"


def TestClient(app, *, base_url, auth):
    client = StarletteClient(app, base_url=base_url)
    client.auth = auth
    return client


@pytest.fixture
def catalog(tmp_path):
    shutil.copytree(ROOT / "examples", tmp_path / "examples")
    return tmp_path / "examples/viewer.json"


@pytest.fixture
def client(catalog):
    with TestClient(create_app(catalog, AUTH[1]), base_url="http://127.0.0.1", auth=AUTH) as client:
        yield client


def test_access_boundaries(client):
    assert client.get("/", auth=None).status_code == 401
    assert client.get("/", auth=("wrong", AUTH[1])).status_code == 401
    assert client.get("/", auth=(AUTH[0], "wrong")).status_code == 401
    assert client.get("/", headers={"Host": "attacker.example"}).status_code == 400
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    assert client.post("/").status_code == 405
    for route in ("/docs", "/openapi.json", "/workloads/missing", BASE + "missing"):
        assert client.get(route).status_code == 404
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-frame-options"] == "DENY"
    assert "default-src 'none'" in response.headers["content-security-policy"]
    assert client.get(BASE + "verified/report.json").status_code == 403


@pytest.mark.parametrize("route", ["/", "/workloads", "/workloads/daily-summary"])
def test_pages(client, route):
    assert client.get(route).status_code == 200


@pytest.mark.parametrize("key", ["verified", "incorrect", "estimates", "reviewed", "runtime"])
def test_details_and_summaries(client, key):
    assert client.get(BASE + key).status_code == 200
    response = client.get(BASE + key + "/summary.json")
    assert response.status_code == 200
    data = response.json()
    assert data["available"] is True
    assert data["synthetic"] is True
    assert data["status"] in {"PASS", "FAIL", "UNKNOWN"}
    assert set(data) == {"title", "status", "kind", "synthetic", "available", "sections"}
    assert "execution_ids" not in response.text
    assert "evidence_ref" not in response.text


@pytest.mark.parametrize(
    "key,command,source",
    [
        ("verified", "verify", "verification/passing.json"),
        ("incorrect", "verify", "verification/incorrect.json"),
        ("reviewed", "finance", "financial/reviewed.json"),
        ("estimates", "finance", "financial/estimate_only.json"),
        ("runtime", "compare", "bigquery/comparison.json"),
    ],
)
def test_download_matches_cli(catalog, key, command, source):
    cli = subprocess.run(
        [sys.executable, "-m", "datavouch", command, str(catalog.parent / source)],
        capture_output=True,
        check=False,
    )
    assert cli.returncode in (0, 1, 3)
    with TestClient(
        create_app(catalog, AUTH[1], allow_raw_reports=True),
        base_url="http://127.0.0.1",
        auth=AUTH,
    ) as client:
        response = client.get(BASE + key + "/report.json")
        assert response.status_code == 200
        assert response.content == cli.stdout


def test_filters(client):
    for state in ("PASS", "FAIL", "UNKNOWN"):
        assert client.get("/", params={"status": state}).status_code == 200
    assert client.get("/?status=BAD").status_code == 400
    assert client.get("/", params={"q": "x" * 201}).status_code == 400
    assert "verified" not in client.get("/?q=unmatched-example").text


def rewrite(catalog, change):
    document = json.loads(catalog.read_text())
    change(document)
    catalog.write_text(json.dumps(document))


def test_missing_input_and_snapshot(catalog):
    source = catalog.parent / "verification/passing.json"
    app = create_app(catalog, AUTH[1], allow_raw_reports=True)
    source.unlink()
    with TestClient(app, base_url="http://127.0.0.1", auth=AUTH) as client:
        assert client.get(BASE + "verified/summary.json").json()["status"] == "PASS"
    with TestClient(
        create_app(catalog, AUTH[1], allow_raw_reports=True),
        base_url="http://127.0.0.1",
        auth=AUTH,
    ) as client:
        assert client.get(BASE + "verified/summary.json").json()["status"] == "UNKNOWN"
        assert client.get(BASE + "verified/report.json").status_code == 409
        assert str(source) not in client.get(BASE + "verified").text


def test_html_escaping(catalog):
    rewrite(catalog, lambda d: d["workloads"][0].update(name='<script>alert("x")</script>'))
    with TestClient(create_app(catalog, AUTH[1]), base_url="http://127.0.0.1", auth=AUTH) as c:
        page = c.get("/").text
        assert '<script>alert("x")</script>' not in page
        assert "&lt;script&gt;" in page


@pytest.mark.parametrize("path", ["../secret.json", "/tmp/secret.json"])
def test_path_escape(catalog, path):
    rewrite(catalog, lambda d: d["workloads"][0]["experiments"][0].update(input=path))
    with pytest.raises(ValueError, match="within"):
        load_catalog(catalog)


def test_symlink_escape(catalog, tmp_path):
    (tmp_path / "secret.json").write_text("{}")
    (catalog.parent / "escape.json").symlink_to(tmp_path / "secret.json")
    rewrite(catalog, lambda d: d["workloads"][0]["experiments"][0].update(input="escape.json"))
    with pytest.raises(ValueError, match="symlink"):
        load_catalog(catalog)


@pytest.mark.parametrize(
    "field,value",
    [
        ("id", "Bad ID"),
        ("title", "x" * 301),
        ("kind", "other"),
        ("synthetic", "yes"),
        ("recorded_at", "not-a-date"),
    ],
)
def test_invalid_manifest(catalog, field, value):
    rewrite(catalog, lambda d: d["workloads"][0]["experiments"][0].update({field: value}))
    with pytest.raises(ValueError):
        load_catalog(catalog)


@pytest.mark.parametrize("password", ["short", " " * 20, "é" * 20, "x" * 257, "\n" * 20])
def test_invalid_password(catalog, password):
    with pytest.raises(ValueError, match="password"):
        create_app(catalog, password)


def test_command(catalog, monkeypatch, capsys):
    monkeypatch.delenv("DATAVOUCH_WEB_PASSWORD", raising=False)
    with patch("sys.stdin.isatty", return_value=False):
        assert serve_command(catalog, 8765, False) == 2
    assert serve_command(catalog, 80, False) == 2
    monkeypatch.setenv("DATAVOUCH_WEB_PASSWORD", "short")
    assert serve_command(catalog, 8765, False) == 2
    monkeypatch.setenv("DATAVOUCH_WEB_PASSWORD", AUTH[1])
    with patch("uvicorn.run") as run:
        assert serve_command(catalog, 8765, False) == 0
        assert run.call_args.kwargs == {
            "host": "127.0.0.1",
            "port": 8765,
            "access_log": False,
            "proxy_headers": False,
        }
    assert AUTH[1] not in capsys.readouterr().out


@pytest.mark.parametrize("scope", ["workload", "experiment"])
def test_duplicates(catalog, scope):
    def change(document):
        items = document["workloads"]
        if scope == "experiment":
            items = items[0]["experiments"]
        items.append(items[0])

    rewrite(catalog, change)
    with pytest.raises(ValueError, match="Duplicate"):
        load_catalog(catalog)


def test_catalog_limits(catalog):
    rewrite(catalog, lambda d: d.update(workloads=d["workloads"] * 51))
    with pytest.raises(ValueError, match="50 workloads"):
        load_catalog(catalog)


def test_report_limit(catalog):
    def change(document):
        example = document["workloads"][0]["experiments"][0]
        document["workloads"][0]["experiments"] = [
            {**example, "id": f"run-{i}"} for i in range(101)
        ]

    rewrite(catalog, change)
    with pytest.raises(ValueError, match="100 experiments"):
        load_catalog(catalog)


def test_input_budget(catalog):
    source = catalog.parent / "verification/passing.json"
    with source.open("wb") as stream:
        stream.truncate(20_000_001)
    with pytest.raises(OverflowError, match="input budget"):
        load_catalog(catalog)


def test_output_budget(catalog):
    with patch("datavouch.web.catalog.calculate", return_value=({}, b"x" * 50_000_001)):
        with pytest.raises(OverflowError, match="output budget"):
            load_catalog(catalog)


def test_interactive_password(catalog, monkeypatch):
    monkeypatch.delenv("DATAVOUCH_WEB_PASSWORD", raising=False)
    with (
        patch("sys.stdin.isatty", return_value=True),
        patch("getpass.getpass", return_value=AUTH[1]),
        patch("uvicorn.run"),
    ):
        assert serve_command(catalog, 8765, False) == 0
