import json
from pathlib import Path

import pytest

from datavouch.adapters.bigquery.commands import collect_command
from datavouch.adapters.bigquery.files import load_fixture
from datavouch.cli import main

ROOT = Path(__file__).resolve().parents[2] / "examples/bigquery"
CONFIG = ROOT / "collection_config.json"
FIXTURE = ROOT / "jobs.json"


def test_offline_cli(capsys):
    assert main(["collect-bigquery", str(CONFIG), "--fixture", str(FIXTURE)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["eligible"]
    assert data["source"] == "fixture"
    assert len(data["observations"]) == 3


def test_incomplete_fixture_exit_code(tmp_path, capsys):
    path = tmp_path / "jobs.json"
    path.write_text("[]")
    assert main(["collect-bigquery", str(CONFIG), "--fixture", str(path)]) == 3
    assert not json.loads(capsys.readouterr().out)["eligible"]


def test_live_cli_with_injected_collector(monkeypatch, capsys):
    from datavouch.adapters.bigquery import client

    monkeypatch.setattr(client, "collect_live", lambda config: load_fixture(FIXTURE, config))
    assert main(["collect-bigquery", str(CONFIG), "--live"]) == 0
    assert json.loads(capsys.readouterr().out)["eligible"]


def test_explicit_source_required():
    with pytest.raises(SystemExit) as error:
        main(["collect-bigquery", str(CONFIG)])
    assert error.value.code == 2


def test_missing_source_safe_error(capsys):
    assert collect_command(CONFIG, None, False) == 2
    assert "Select a fixture" in capsys.readouterr().err


def test_unreadable_config_safe_error(tmp_path, capsys):
    assert collect_command(tmp_path / "missing", FIXTURE, False) == 2
    assert "Invalid or unreadable" in capsys.readouterr().err
