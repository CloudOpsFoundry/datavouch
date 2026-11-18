import json
from pathlib import Path

import pytest

from datavouch.cli import main

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/financial/reviewed.json"


@pytest.mark.parametrize("minimum,code", [("0", 0), ("5", 1), (None, 3)])
def test_financial_cli(tmp_path, capsys, minimum, code):
    document = json.loads(EXAMPLE.read_text())
    if minimum is None:
        document.pop("billing")
    else:
        document["minimum_reduction"] = minimum
    path = tmp_path / "input.json"
    path.write_text(json.dumps(document))
    assert main(["finance", str(path)]) == code
    report = json.loads(capsys.readouterr().out)
    assert report["schema_version"] == "financial-0.1"
    assert report["status"] == {0: "PASS", 1: "FAIL", 3: "UNKNOWN"}[code]


def test_financial_invalid_input(tmp_path, capsys):
    assert main(["finance", str(tmp_path / "missing")]) == 2
    assert "Invalid or unreadable" in capsys.readouterr().err
