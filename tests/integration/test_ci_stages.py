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


def test_public_release_is_main_only_after_validation_without_checkout():
    import yaml

    workflow = yaml.load(
        (ROOT / ".github/workflows/public.yml").read_text(), Loader=yaml.BaseLoader
    )
    job = workflow["jobs"]["release"]
    assert job["needs"] == ["validate"]
    assert job["if"] == "github.event_name == 'push' && github.ref == 'refs/heads/main'"
    assert job["concurrency"]["cancel-in-progress"] == "false"
    assert not any("checkout" in step.get("uses", "") for step in job["steps"])
    assert not any("upload-artifact" in step.get("uses", "") for step in job["steps"])
    action = job["steps"][1]
    assert action["uses"].endswith("@45996ed1f6d02564a971a2fa1b5860e934307cf7")
    assert action["if"] == "steps.revision.outputs.current == 'true'"
    assert "gh workflow run public.yml" in job["steps"][2]["run"]


def test_release_manifest_and_annotations_match_only_project_version():
    import json
    import tomllib

    config = json.loads((ROOT / "release-please-config.json").read_text())
    manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())
    version = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
    assert manifest == {".": version}
    assert config["include-component-in-tag"] is False
    assert config["packages"]["."]["release-type"] == "python"
    annotated = [
        line
        for line in (ROOT / "uv.lock").read_text().splitlines()
        if "x-release-please-version" in line
    ]
    assert annotated == [f'version = "{version}" # x-release-please-version']
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    assert next(p["version"] for p in lock["package"] if p["name"] == "datavouch") == version
