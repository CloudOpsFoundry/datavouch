"""Release a successful main revision with Commitizen; never change repository visibility."""

import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from commitizen import defaults
from commitizen.git import get_commits
from commitizen.version_increment import VersionIncrement
from packaging.version import Version

FILES = (
    "pyproject.toml",
    "uv.lock",
    "src/datavouch/__init__.py",
    "deployment/helm/datavouch/Chart.yaml",
    "CHANGELOG.md",
)
BUMP = [
    sys.executable,
    "-m",
    "commitizen",
    "bump",
    "--increment-mode",
    "exact",
    "--prerelease",
    "alpha",
]


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], text=True).strip()


def network_git(token: str, *args: str) -> None:
    """Authenticate only the network command, never persist a token or expose it in argv."""
    authorization = base64.b64encode(f"x-access-token:{token}".encode()).decode()
    environment = {
        **os.environ,
        "GIT_CONFIG_COUNT": "1",
        "GIT_CONFIG_KEY_0": "http.https://github.com/.extraheader",
        "GIT_CONFIG_VALUE_0": f"AUTHORIZATION: basic {authorization}",
    }
    subprocess.run(["git", *args], env=environment, check=True)


def project_version() -> str:
    return tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]


def prepare() -> str | None:
    """Only edit release metadata. Commitizen owns version selection and changelog generation."""
    # Commitizen increments prerelease counters even for docs-only commits. Require a
    # release-worthy change using its own conventional-commit classifier first.
    increment = VersionIncrement.get_highest_by_messages(
        (commit.message for commit in get_commits("v" + project_version())),
        defaults.BUMP_PATTERN,
        defaults.BUMP_MAP,
    )
    if increment == VersionIncrement.NONE:
        return None
    result = subprocess.run([*BUMP, "--get-next"], capture_output=True, text=True)
    if result.returncode in (3, 21):  # No commits / no increment, as defined by Commitizen.
        return None
    result.check_returncode()
    expected = str(Version(result.stdout.strip()))
    changelog = Path("CHANGELOG.md")
    previous_changelog = changelog.read_text()
    subprocess.run([*BUMP, "--yes", "--version-files-only", "--changelog"], check=True)
    # Commitizen may rewrite handwritten historical sections when their heading
    # format differs from generated entries. Only accept its new release section.
    generated = changelog.read_text()
    heading = re.search(rf"(?m)^## v?{re.escape(expected)}(?:\s|$)", generated)
    if heading is None:
        raise ValueError("Missing generated release entry")
    following = re.search(r"(?m)^## ", generated[heading.end() :])
    end = heading.end() + following.start() if following else len(generated)
    entry = generated[heading.start() : end].strip()
    history = re.search(r"(?m)^## v?\d", previous_changelog)
    if history is None:
        raise ValueError("Missing historical release entries")
    pending = previous_changelog[: history.start()]
    unreleased = re.search(r"(?m)^## Unreleased\s*$", pending)
    if unreleased:
        notes = pending[unreleased.end() :].strip()
        if notes:
            entry += "\n\n" + notes
    changelog.write_text("# Changelog\n\n" + entry + "\n\n" + previous_changelog[history.start() :])
    if project_version() != expected:
        raise ValueError("Version calculation changed during release preparation")
    version = Version(expected)
    if version.pre is None or version.pre[0] != "a":
        raise ValueError("Automatic releases must remain alpha until release policy is reviewed")
    chart = Path("deployment/helm/datavouch/Chart.yaml")
    content, count = re.subn(
        r"(?m)^version: .+$",
        f"version: {version.base_version}-alpha.{version.pre[1]}",
        chart.read_text(),
    )
    content, app_count = re.subn(r"(?m)^appVersion: .+$", f"appVersion: {expected}", content)
    if (count, app_count) != (1, 1):
        raise ValueError("Ambiguous chart version metadata")
    chart.write_text(content)
    changed = set(git("diff", "--name-only").splitlines())
    if not changed <= set(FILES):
        raise ValueError("Release preparation changed unexpected files")
    return expected


def release_notes(version: str, changelog: str) -> str:
    match = re.search(rf"(?m)^## (?:v)?{re.escape(version)}(?:\s|$)", changelog)
    if match is None:
        raise ValueError("Release has no generated changelog entry")
    following = re.search(r"(?m)^## ", changelog[match.end() :])
    end = match.end() + following.start() if following else len(changelog)
    return (
        "Alpha prerelease for evaluation. Independent client, security and ownership reviews "
        "remain required. No production certification or package-registry publication.\n\n"
        + changelog[match.start() : end].strip()
    )


def ensure_github_release(repository: str, token: str, tag: str, version: str) -> None:
    """Retry safely: existing releases are never overwritten."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository identifier")
    url = f"https://api.github.com/repos/{repository}/releases"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    try:
        with urlopen(Request(url + "/tags/" + tag, headers=headers), timeout=30):
            print("GitHub release already exists; nothing changed")
            return
    except HTTPError as error:
        if error.code != 404:
            raise RuntimeError(f"GitHub release lookup failed: HTTP {error.code}") from None
    body = {
        "tag_name": tag,
        "name": f"DataVouch {version}",
        "body": release_notes(version, git("show", f"{tag}:CHANGELOG.md")),
        "prerelease": True,
        "make_latest": "false",
    }
    try:
        with urlopen(
            Request(url, data=json.dumps(body).encode(), headers=headers, method="POST"), timeout=30
        ):
            print(f"Created alpha release {tag}")
    except HTTPError as error:
        raise RuntimeError(
            f"GitHub release creation failed: HTTP {error.code}; rerun this job"
        ) from None


def completed_tag(trigger: str) -> str | None:
    """Recover a prior atomic push, even if main has subsequently advanced."""
    for tag in git("tag", "--list", "v*").splitlines():
        revision = git("rev-list", "-n", "1", tag)
        if git("show", "-s", "--format=%P", revision) != trigger:
            continue
        if git("show", "-s", "--format=%s", revision) != f"chore(release): {tag[1:]}":
            continue
        if (
            subprocess.run(
                ["git", "merge-base", "--is-ancestor", revision, "origin/main"], capture_output=True
            ).returncode
            == 0
        ):
            return tag
    return None


def main() -> int:
    if (
        os.environ.get("GITHUB_REF") != "refs/heads/main"
        or os.environ.get("GITHUB_ACTIONS") != "true"
    ):
        raise ValueError("Release writes require the main GitHub Actions job")
    trigger = os.environ["GITHUB_SHA"]
    if not re.fullmatch(r"[0-9a-f]{40}", trigger):
        raise ValueError("Invalid tested revision")
    token, repository = os.environ["GITHUB_TOKEN"], os.environ["GITHUB_REPOSITORY"]
    if git("status", "--porcelain") or git("rev-parse", "HEAD") != trigger:
        raise ValueError("Release checkout must be clean and match the tested revision")
    network_git(token, "fetch", "origin", "main", "--tags")
    if tag := completed_tag(trigger):
        ensure_github_release(repository, token, tag, tag[1:])
        return 0
    if git("rev-parse", "origin/main") != trigger:
        print("Main advanced; the newer successful pipeline will release the accumulated changes")
        return 0
    version = prepare()
    if version is None:
        print("No release-worthy commits; no version, tag or release changed")
        return 0
    # Main already tested the functional code. Revalidate stamped metadata and rebuilt artifacts.
    shutil.rmtree("dist", ignore_errors=True)
    for stage in ("build", "integrity", "installation", "sdist", "release"):
        subprocess.run([sys.executable, "scripts/validate.py", "--stage", stage], check=True)
    git("add", "--", *FILES)
    git(
        "-c",
        "user.name=github-actions[bot]",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit",
        "-m",
        f"chore(release): {version}",
    )
    tag = f"v{version}"
    git(
        "-c",
        "user.name=github-actions[bot]",
        "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "tag",
        "-a",
        tag,
        "-m",
        f"DataVouch {version} alpha prerelease",
    )
    network_git(token, "push", "--atomic", "origin", "HEAD:refs/heads/main", f"refs/tags/{tag}")
    ensure_github_release(repository, token, tag, version)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
