"""Validate local release artifacts and inventory this environment; not release approval."""

import hashlib
import importlib.metadata
import json
import tarfile
import tomllib
import zipfile
from email.parser import BytesParser
from pathlib import Path

from datavouch import __version__

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    if project["version"] != __version__:
        raise ValueError("Package and project versions disagree")
    if f"## {__version__}" not in (ROOT / "CHANGELOG.md").read_text():
        raise ValueError("Version is absent from changelog")
    wheels = list((ROOT / "dist").glob("*.whl"))
    sources = list((ROOT / "dist").glob("*.tar.gz"))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError("Expected one current wheel and source distribution")
    artifacts = []
    for path in wheels + sources:
        if path.suffix == ".whl":
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
                metadata_names = [n for n in names if n.endswith(".dist-info/METADATA")]
                if len(metadata_names) != 1:
                    raise ValueError("Ambiguous wheel metadata")
                metadata = BytesParser().parsebytes(archive.read(metadata_names[0]))
                if "datavouch/py.typed" not in names:
                    raise ValueError("Missing public typing marker")
        else:
            with tarfile.open(path) as archive:
                names = archive.getnames()
                metadata_names = [n for n in names if n.endswith("/PKG-INFO")]
                if len(metadata_names) != 1:
                    raise ValueError("Ambiguous source metadata")
                source = archive.extractfile(metadata_names[0])
                if source is None:
                    raise ValueError("Missing source metadata")
                metadata = BytesParser().parsebytes(source.read())
        if metadata["Name"] != project["name"] or metadata["Version"] != __version__:
            raise ValueError("Artifact identity differs from project")
        requirement = metadata["Requires-Python"]
        expected = {part.strip() for part in project["requires-python"].split(",")}
        if requirement is None or {part.strip() for part in requirement.split(",")} != expected:
            raise ValueError("Artifact Python requirement differs from project")
        if not any(n.endswith("/LICENSE") for n in names):
            raise ValueError("Missing license in distribution")
        artifacts.append(
            {
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "bytes": path.stat().st_size,
                "members": len(names),
            }
        )
    dependencies = []
    for dist in importlib.metadata.distributions():
        name = dist.metadata.get("Name")
        if name and name.lower() != "datavouch":
            # Metadata is an inventory, not a license compatibility determination.
            license_value = dist.metadata.get("License-Expression") or dist.metadata.get("License")
            dependencies.append(
                {
                    "name": name,
                    "version": dist.version,
                    "license_metadata": license_value[:200] if license_value else None,
                }
            )
    print(
        json.dumps(
            {
                "version": __version__,
                "local_artifact_checks_passed": True,
                "release_approval": "not_assessed",
                "dependency_scope": "installed validation environment, including development tools",
                "artifacts": artifacts,
                "dependencies": sorted(dependencies, key=lambda d: d["name"].lower()),
            },
            sort_keys=True,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
