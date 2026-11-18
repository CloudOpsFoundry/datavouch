"""Release checks reject mismatched identity and missing legal/typing artifacts."""

import importlib.util
import io
import json
import tarfile
import zipfile
from pathlib import Path

import pytest

from datavouch import __version__

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def release(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location(
        "release_check", ROOT / "scripts/check_release.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module.importlib.metadata, "distributions", lambda: [])
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname="datavouch"\nversion="{__version__}"\nrequires-python=">=3.15,<3.16"\n'
    )
    (tmp_path / "CHANGELOG.md").write_text(f"## {__version__}\n")
    (tmp_path / "dist").mkdir()
    return module


def artifacts(root, *, version=__version__, license=True, typed=True, python=">=3.15,<3.16"):
    metadata = f"Name: datavouch\nVersion: {version}\nRequires-Python: {python}\n".encode()
    with zipfile.ZipFile(root / "dist/package.whl", "w") as archive:
        archive.writestr("datavouch.dist-info/METADATA", metadata)
        if typed:
            archive.writestr("datavouch/py.typed", "")
        if license:
            archive.writestr("datavouch.dist-info/licenses/LICENSE", "MIT")
    with tarfile.open(root / "dist/package.tar.gz", "w:gz") as archive:
        for name, value in {"package/PKG-INFO": metadata, "package/LICENSE": b"MIT"}.items():
            member = tarfile.TarInfo(name)
            member.size = len(value)
            archive.addfile(member, io.BytesIO(value))


def test_release_inventory_is_not_approval(release, capsys):
    artifacts(release.ROOT)
    assert release.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert report["local_artifact_checks_passed"] is True
    assert report["release_approval"] == "not_assessed"
    assert len(report["artifacts"]) == 2
    assert all(len(a["sha256"]) == 64 for a in report["artifacts"])


@pytest.mark.parametrize(
    "problem", ["identity", "license", "typing", "version", "changelog", "missing"]
)
def test_release_rejects_invalid_artifacts(release, problem):
    artifacts(
        release.ROOT,
        version="9.0.0" if problem == "identity" else __version__,
        license=problem != "license",
        typed=problem != "typing",
    )
    if problem == "version":
        release.__version__ = "9.0.0"
    elif problem == "changelog":
        (release.ROOT / "CHANGELOG.md").write_text("Nothing released")
    elif problem == "missing":
        (release.ROOT / "dist/package.whl").unlink()
    with pytest.raises(ValueError):
        release.main()


def test_release_accepts_reordered_python_constraints(release):
    artifacts(release.ROOT, python="<3.16, >=3.15")
    assert release.main() == 0


def test_release_rejects_different_python_constraints(release):
    artifacts(release.ROOT, python=">=3.15")
    with pytest.raises(ValueError, match="Python requirement"):
        release.main()


def test_release_accepts_generated_tag_heading(release):
    artifacts(release.ROOT)
    (release.ROOT / "CHANGELOG.md").write_text(f"## v{__version__} (2026-11-18)\n")
    assert release.main() == 0


def test_release_requires_exact_version_heading(release):
    artifacts(release.ROOT)
    (release.ROOT / "CHANGELOG.md").write_text(f"## {__version__}0\n")
    with pytest.raises(ValueError, match="absent from changelog"):
        release.main()
