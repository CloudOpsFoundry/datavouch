import json
from pathlib import Path

import pytest

from datavouch.cli import main

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/verification/passing.json"


@pytest.mark.parametrize("outcome,code", [(True, 0), (False, 1), (None, 3)])
def test_verification_exit_codes(tmp_path, capsys, outcome, code):
    data = json.loads(EXAMPLE.read_text())
    data["assurance"]["evidence"][0]["observed"] = outcome
    path = tmp_path / "input.json"
    path.write_text(json.dumps(data))
    assert main(["verify", str(path)]) == code
    result = json.loads(capsys.readouterr().out)
    assert result["schema_version"] == "verification-0.1"
    assert result["overall_status"] == {0: "PASS", 1: "FAIL", 3: "UNKNOWN"}[code]


def test_invalid_input(tmp_path, capsys):
    assert main(["verify", str(tmp_path / "missing")]) == 2
    assert "Invalid or unreadable" in capsys.readouterr().err
