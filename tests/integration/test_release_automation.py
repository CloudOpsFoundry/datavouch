"""Exercise real Commitizen against isolated repositories; never publish test releases."""

import importlib.util
import json
import subprocess
from pathlib import Path
from urllib.error import HTTPError

import pytest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("release_automation", ROOT / "scripts/release.py")
release = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(release)


def git(*args):
    return subprocess.check_output(["git", *args], text=True).strip()


@pytest.fixture
def repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    git("init", "-b", "main")
    git("config", "user.name", "Release test")
    git("config", "user.email", "release@example.invalid")
    config = (ROOT / "pyproject.toml").read_text().split("[tool.commitizen]", 1)[1]
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname="datavouch"\nversion="0.1.0a2"\n[tool.commitizen]' + config
    )
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname="datavouch"\nversion="0.1.0a2"\n'
        '[[package]]\nname="unrelated"\nversion="0.1.0a2"\n'
    )
    (tmp_path / "src/datavouch").mkdir(parents=True)
    (tmp_path / "src/datavouch/__init__.py").write_text('__version__ = "0.1.0a2"\n')
    (tmp_path / "deployment/helm/datavouch").mkdir(parents=True)
    (tmp_path / "deployment/helm/datavouch/Chart.yaml").write_text(
        "version: 0.1.0-alpha.2\nappVersion: 0.1.0a2\n"
    )
    (tmp_path / "CHANGELOG.md").write_text("# Changelog\n\n## 0.1.0a2\n\nOriginal entry.\n")
    git("add", ".")
    git("commit", "-m", "chore: initial")
    git("tag", "v0.1.0a2")
    return tmp_path


@pytest.mark.parametrize(
    "message,expected",
    [
        ("fix: correct aggregation", "0.1.1a0"),
        ("feat: add adapter", "0.2.0a0"),
        ("feat!: change contract", "1.0.0a0"),
        ("fix: update behavior\n\nBREAKING CHANGE: old contract removed", "1.0.0a0"),
        ("docs: clarify setup", None),
    ],
)
def test_real_bumps_and_notes(repo, message, expected):
    git("commit", "--allow-empty", "-m", message)
    assert release.prepare() == expected
    if expected:
        import tomllib

        assert tomllib.loads((repo / "uv.lock").read_text())["package"][1]["version"] == "0.1.0a2"
        assert expected in (repo / "src/datavouch/__init__.py").read_text()
        assert "alpha.0" in (repo / "deployment/helm/datavouch/Chart.yaml").read_text()
        assert message.splitlines()[0].split(": ", 1)[1] in release.release_notes(
            expected, (repo / "CHANGELOG.md").read_text()
        )
        assert "Original entry." in (repo / "CHANGELOG.md").read_text()
    else:
        assert not git("status", "--porcelain")


def test_existing_tag_retry_and_notes_do_not_include_older_entries(repo):
    git("commit", "--allow-empty", "-m", "fix: first")
    trigger = git("rev-parse", "HEAD")
    version = release.prepare()
    git("add", ".")
    git("commit", "-m", f"chore(release): {version}")
    git("tag", f"v{version}")
    git("commit", "--allow-empty", "-m", "feat: later work")
    git("update-ref", "refs/remotes/origin/main", "HEAD")
    assert release.completed_tag(trigger) == f"v{version}"
    notes = release.release_notes(version, git("show", f"v{version}:CHANGELOG.md"))
    assert "first" in notes and "Original entry" not in notes


def test_atomic_push_race_leaves_remote_without_new_tag(repo, tmp_path):
    remote = tmp_path.parent / (tmp_path.name + "-remote.git")
    git("init", "--bare", str(remote))
    git("remote", "add", "origin", str(remote))
    git("push", "origin", "main")
    old = git("rev-parse", "HEAD")
    git("commit", "--allow-empty", "-m", "fix: newer main")
    git("push", "origin", "main")
    git("checkout", "--detach", old)
    git("commit", "--allow-empty", "-m", "chore(release): 0.1.1a0")
    git("tag", "v0.1.1a0")
    result = subprocess.run(
        ["git", "push", "--atomic", "origin", "HEAD:refs/heads/main", "refs/tags/v0.1.1a0"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert not git("ls-remote", "--tags", "origin", "refs/tags/v0.1.1a0")


def test_release_guard_before_any_git_write(monkeypatch):
    monkeypatch.setenv("GITHUB_REF", "refs/heads/feature/test")
    with pytest.raises(ValueError, match="main GitHub Actions"):
        release.main()


def test_github_release_retry_is_read_only(monkeypatch):
    calls = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def request(req, **kwargs):
        calls.append(req.get_method())
        return Response()

    monkeypatch.setattr(release, "urlopen", request)
    release.ensure_github_release("example/project", "fixture-only-token", "v0.1.1a0", "0.1.1a0")
    assert calls == ["GET"]


def test_github_release_is_explicitly_prerelease(monkeypatch):
    payloads = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

    def request(req, **kwargs):
        if req.get_method() == "GET":
            raise HTTPError(req.full_url, 404, "missing", {}, None)
        payloads.append(json.loads(req.data))
        return Response()

    monkeypatch.setattr(release, "urlopen", request)
    monkeypatch.setattr(release, "git", lambda *a: "## 0.1.1a0\n\nFix result\n\n## 0.1.0a2\nOld")
    release.ensure_github_release("example/project", "fixture-only-token", "v0.1.1a0", "0.1.1a0")
    assert payloads[0]["prerelease"] is True
    assert payloads[0]["make_latest"] == "false"
    assert "Old" not in payloads[0]["body"]


def test_no_new_commits_do_not_release(repo):
    assert release.prepare() is None
    assert not git("status", "--porcelain")


def test_private_main_gate_and_minimum_write_permissions():
    import yaml

    workflow = yaml.load((ROOT / ".github/workflows/main.yml").read_text(), Loader=yaml.BaseLoader)
    job = workflow["jobs"]["release"]
    assert job["needs"] == ["gate"]
    assert "refs/heads/main" in job["if"] and "github.event_name == 'push'" in job["if"]
    assert "github.event.repository.private" in job["if"]
    assert job["permissions"] == {"contents": "write"}
    assert job["concurrency"]["cancel-in-progress"] == "false"
    assert workflow["permissions"] == {"contents": "read"}
    assert "pull_request_target" not in workflow["on"]
    for name, other in workflow["jobs"].items():
        if name != "release":
            assert other.get("permissions", {}).get("contents", "read") == "read"


def test_superseded_main_does_not_prepare_or_publish(monkeypatch):
    trigger = "a" * 40
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_REF", "refs/heads/main")
    monkeypatch.setenv("GITHUB_SHA", trigger)
    monkeypatch.setenv("GITHUB_TOKEN", "fixture-only-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/project")
    monkeypatch.setattr(release, "network_git", lambda *args: None)
    monkeypatch.setattr(release, "completed_tag", lambda value: None)
    monkeypatch.setattr(release, "prepare", lambda: pytest.fail("Superseded revision prepared"))

    def query(*args):
        if args == ("rev-parse", "HEAD"):
            return trigger
        if args == ("rev-parse", "origin/main"):
            return "b" * 40
        return ""

    monkeypatch.setattr(release, "git", query)
    assert release.main() == 0


def test_validation_failure_prevents_commit_tag_and_push(monkeypatch):
    trigger = "a" * 40
    for name, value in {
        "GITHUB_ACTIONS": "true",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_SHA": trigger,
        "GITHUB_TOKEN": "fixture-only-token",
        "GITHUB_REPOSITORY": "example/project",
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(release, "network_git", lambda *args: None)
    monkeypatch.setattr(release, "completed_tag", lambda value: None)
    monkeypatch.setattr(release, "prepare", lambda: "0.1.1a0")
    monkeypatch.setattr(release.shutil, "rmtree", lambda *a, **kw: None)
    calls = []

    def query(*args):
        calls.append(args)
        return trigger if args[0] == "rev-parse" else ""

    def fail(*args, **kwargs):
        raise subprocess.CalledProcessError(1, args[0])

    monkeypatch.setattr(release, "git", query)
    monkeypatch.setattr(release.subprocess, "run", fail)
    with pytest.raises(subprocess.CalledProcessError):
        release.main()
    assert not any("commit" in c or "tag" in c or "push" in c for c in calls)


def test_network_auth_is_scoped_to_subprocess_environment(monkeypatch):
    calls = []
    monkeypatch.setattr(release.subprocess, "run", lambda args, **kw: calls.append((args, kw)))
    release.network_git("fixture-only-token", "fetch", "origin", "main", "--tags")
    args, options = calls[0]
    assert "fixture-only-token" not in " ".join(args)
    assert options["env"]["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraheader"
    assert options["env"]["GIT_CONFIG_VALUE_0"].startswith("AUTHORIZATION: basic ")
    assert options["check"] is True
