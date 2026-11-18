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
