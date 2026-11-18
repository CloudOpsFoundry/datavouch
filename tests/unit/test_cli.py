import pytest

from datavouch.cli import main


def test_help(capsys):
    assert main([]) == 0
    assert "Measure. Validate. Trust." in capsys.readouterr().out


def test_version(capsys):
    with pytest.raises(SystemExit) as result:
        main(["--version"])
    assert result.value.code == 0
    assert "0.1.0a2" in capsys.readouterr().out


def test_cli_invalid_input(tmp_path, capsys):
    assert main(["compare", str(tmp_path / "missing")]) == 2
    assert "Invalid or unreadable" in capsys.readouterr().err


def test_cli_comparison(capsys):
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "examples/bigquery/comparison.json"
    assert main(["compare", str(path)]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["results"][0]["status"] == "PASS"
    assert data["results"][1]["status"] == "UNKNOWN"
