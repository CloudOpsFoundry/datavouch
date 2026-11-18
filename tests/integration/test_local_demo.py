"""Local use-case acceptance with real SQL, independent results and replayed verification."""

import json
import subprocess
import sys

import pytest

from datavouch.demo import run_demo
from datavouch.verification.evaluation import verify
from datavouch.web.catalog import load_catalog


def test_local_revenue_workflow(tmp_path):
    output = tmp_path / "demo"
    summary = run_demo(output)
    outcomes = {row["scenario"]: row for row in summary["results"]}
    correct = outcomes["equivalent"]
    incorrect = outcomes["incorrect"]
    assert correct["expected_total_cents"] == correct["observed_total_cents"] == 55500000
    assert incorrect["observed_total_cents"] == 24000000
    assert incorrect["status"] == "FAIL"
    assert correct["checks"]["ticket_sales_total"] == "PASS"
    assert outcomes["missing-evidence"]["checks"]["ticket_sales_total"] == "UNKNOWN"
    assert all(row["candidate_mean_ms"] > 0 for row in summary["results"])
    assert "UNKNOWN" in summary["financial_conclusion"]
    assert len(load_catalog(output / "catalog.json")[0].experiments) == 3
    observations = json.loads((output / "observations.json").read_text())
    assert observations["line_items"] == 3000
    for name in outcomes:
        saved = json.loads((output / f"{name}-report.json").read_text())
        supplied = json.loads((output / f"{name}-input.json").read_text())
        assert saved == json.loads(json.dumps(verify(supplied)))
        replay = subprocess.run(
            [sys.executable, "-m", "datavouch", "verify", str(output / f"{name}-input.json")],
            capture_output=True,
        )
        assert replay.returncode == {"PASS": 0, "FAIL": 1, "UNKNOWN": 3}[saved["overall_status"]]
        assert replay.stdout == (output / f"{name}-report.json").read_bytes()
    with pytest.raises(FileExistsError):
        run_demo(output)


@pytest.mark.parametrize("orders", [0, 99, 2001])
def test_demo_is_bounded(tmp_path, orders):
    with pytest.raises(ValueError):
        run_demo(tmp_path / "invalid", orders)
    assert not (tmp_path / "invalid").exists()


def test_cli_demo_and_no_overwrite(tmp_path):
    output = tmp_path / "demo"
    command = [
        sys.executable,
        "-m",
        "datavouch",
        "demo",
        "--bookings",
        "100",
        "--output-dir",
        str(output),
    ]
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 0
    assert json.loads(result.stdout)["synthetic"]
    original = (output / "summary.json").read_bytes()
    assert subprocess.run(command, capture_output=True).returncode == 2
    assert original == (output / "summary.json").read_bytes()
