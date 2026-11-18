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


def test_public_ci_is_isolated_and_runs_all_validation_stages():
    import re

    import yaml

    content = (ROOT / ".github/workflows/public.yml").read_text()
    workflow = yaml.load(content, Loader=yaml.BaseLoader)
    assert "pull_request" in workflow["on"]
    assert "pull_request_target" not in workflow["on"]
    assert workflow["permissions"] == {"contents": "read"}
    assert "secrets." not in content
    assert "self-hosted" not in content
    job = workflow["jobs"]["validate"]
    assert job["runs-on"] == "ubuntu-24.04"
    assert job["if"] == "${{ !github.event.repository.private }}"
    assert "permissions" not in job
    stages = []
    for step in job["steps"]:
        assert "continue-on-error" not in step
        assert "if" not in step
        if "uses" in step and not step["uses"].startswith("./"):
            assert re.fullmatch(r"[^@]+@[0-9a-f]{40}", step["uses"])
        if step.get("uses", "").startswith("actions/checkout@"):
            assert step["with"]["persist-credentials"] == "false"
        if "--stage " in step.get("run", ""):
            stages.append(step["run"].split("--stage ", 1)[1])
    assert stages == list(load_validator().STAGES)
