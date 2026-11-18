"""Generic CLI output and error boundaries."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from datavouch.cli import main

ROOT = Path(__file__).resolve().parents[2]
CONNECTOR = ROOT / "examples/adapters/bigquery_connector.json"
FIXTURE = ROOT / "examples/bigquery/jobs.json"


def test_list_and_collect_dispatch(capsys):
    assert main(["adapters"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["api_version"] == "adapter-1"
    assert data["adapters"][0]["modes"] == ["fixture", "live"]
    assert main(["collect", str(CONNECTOR), "--fixture", str(FIXTURE)]) == 0
    assert (
        capsys.readouterr().out == (ROOT / "examples/adapters/expected_bigquery.json").read_text()
    )


def test_missing_fixture_rows_unknown(tmp_path, capsys):
    path = tmp_path / "empty.json"
    path.write_text("[]")
    assert main(["collect", str(CONNECTOR), "--fixture", str(path)]) == 3
    report = json.loads(capsys.readouterr().out)
    assert not report["eligible"]
    assert len(report["missing_ids"]) == 3


@pytest.mark.parametrize("problem", ["missing", "invalid", "version", "config", "too_large"])
def test_safe_errors(tmp_path, capsys, problem):
    path = tmp_path / "private-config.json"
    document = json.loads(CONNECTOR.read_text())
    if problem == "invalid":
        path.write_text("not-json private-secret")
    elif problem == "version":
        document["api_version"] = "unknown"
        path.write_text(json.dumps(document))
    elif problem == "config":
        document["config"]["project"] = "private-secret-invalid"
        document["config"]["extra"] = "private-secret"
        path.write_text(json.dumps(document))
    elif problem == "too_large":
        with path.open("wb") as output:
            output.truncate(5_000_001)
    assert main(["collect", str(path), "--fixture", str(FIXTURE)]) == 2
    capture = capsys.readouterr()
    assert capture.out == ""
    assert "private" not in capture.err


def test_process_output_matches_fixture():
    result = subprocess.run(
        [sys.executable, "-m", "datavouch", "collect", str(CONNECTOR), "--fixture", str(FIXTURE)],
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0
    assert result.stdout == (ROOT / "examples/adapters/expected_bigquery.json").read_bytes()
