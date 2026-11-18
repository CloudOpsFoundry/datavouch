"""Verify that every required CI job must succeed before the final gate passes."""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped", "unknown", None])
@pytest.mark.parametrize("job", ["quality", "tests", "audit", "package"])
def test_gate_rejects_any_unsuccessful_required_job(job, outcome):
    gate = load_script("check_ci_results")
    results = {name: {"result": "success"} for name in gate.REQUIRED}
    results[job]["result"] = outcome
    assert not gate.passed(results)


@pytest.mark.parametrize("results", [{}, [], {"build": "success"}])
def test_gate_rejects_incomplete_results(results):
    assert not load_script("check_ci_results").passed(results)


def test_gate_cli_exit_and_summary(tmp_path):
    gate = load_script("check_ci_results")
    results = {name: {"result": "success"} for name in gate.REQUIRED}
    summary = tmp_path / "summary.md"
    for outcome, code in (("success", 0), ("skipped", 1)):
        results["package"]["result"] = outcome
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/check_ci_results.py")],
            env={
                **os.environ,
                "CI_RESULTS": json.dumps(results),
                "GITHUB_STEP_SUMMARY": str(summary),
            },
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == code
        assert f"| package | {outcome} |" in result.stdout
    assert "CI failed" in summary.read_text()
