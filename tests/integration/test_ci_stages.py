"""CI stages must retain required checks and fail on errors."""

import importlib.util
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load_validator():
    spec = importlib.util.spec_from_file_location("ci_validator", ROOT / "scripts/validate.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_default_keeps_all_required_stages(monkeypatch, tmp_path):
    validator = load_validator()
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append(command[1:])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(validator.subprocess, "run", run)
    assert validator.main([]) == 0
    assert commands == [command for stage in validator.STAGES.values() for command in stage]
    assert any("pip_audit" in c for c in commands)
    assert any("scripts/check_installation.py" in c for c in commands)
    assert any("scripts/check_sdist.py" in c for c in commands)
    assert sum("pytest" in c for c in commands) == 3


def test_failed_stage_stops_pipeline(monkeypatch, tmp_path):
    validator = load_validator()
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append(command)
        return subprocess.CompletedProcess(command, 5)

    monkeypatch.setattr(validator.subprocess, "run", run)
    assert validator.main([]) == 5
    assert len(commands) == 1


def test_selected_stage_only(monkeypatch, tmp_path):
    validator = load_validator()
    monkeypatch.setattr(validator, "ROOT", tmp_path)
    commands = []

    def run(command, **kwargs):
        commands.append(command[1:])
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(validator.subprocess, "run", run)
    assert validator.main(["--stage", "integration"]) == 0
    assert commands == validator.STAGES["integration"]
    assert "--append" in commands[0]
    with pytest.raises(SystemExit):
        validator.main(["--stage", "unknown"])


def test_public_ci_calls_pinned_template_and_keeps_fail_closed_gate():
    import re

    import yaml

    content = (ROOT / ".github/workflows/public.yml").read_text()
    workflow = yaml.load(content, Loader=yaml.BaseLoader)
    assert "pull_request" in workflow["on"]
    assert "pull_request_target" not in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets" not in content
    job = workflow["jobs"]["validate"]
    assert re.fullmatch(
        r"CloudOpsFoundry/ci-templates/\.github/workflows/python-uv\.yml@[0-9a-f]{40}",
        job["uses"],
    )
    assert job["with"]["validation-command"] == "uv run --no-sync python scripts/validate.py"
    assert "steps" not in job and "permissions" not in job
    gate = workflow["jobs"]["gate"]
    assert gate["name"] == "Public CI passed"
    assert gate["needs"] == ["validate"]
    assert gate["if"] == "always()"
    step = gate["steps"][0]
    assert step["env"]["RESULT"] == "${{ needs.validate.result }}"
    for result in ("success", "failure", "cancelled", "skipped", "unknown"):
        process = subprocess.run(
            ["bash", "-c", step["run"]], env={"RESULT": result}, capture_output=True
        )
        assert (process.returncode == 0) == (result == "success")
