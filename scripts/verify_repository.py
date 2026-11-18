"""Verify repository boundaries and distribution contents."""

import re
import subprocess
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    subprocess.run(["git", "check-ignore", ".local_context/probe"], cwd=ROOT, check=True)
    tracked = subprocess.check_output(
        ["git", "ls-files", ".local_context"], cwd=ROOT, text=True
    ).strip()
    if tracked:
        raise ValueError("Private context is tracked")
    candidates = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"], cwd=ROOT, text=True
    ).splitlines()
    patterns = [r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----", r"AKIA[0-9A-Z]{16}"]
    for name in candidates:
        path = ROOT / name
        if path.is_file() and path.stat().st_size <= 2_000_000:
            content = path.read_text(errors="replace")
            if any(re.search(pattern, content) for pattern in patterns):
                raise ValueError(f"Potential exposed credential in {name}")
    for required in ("README.md", "LICENSE", "SECURITY.md", "uv.lock"):
        if not (ROOT / required).is_file():
            raise ValueError(f"Missing {required}")
    artifacts = list((ROOT / "dist").glob("*.whl")) + list((ROOT / "dist").glob("*.tar.gz"))
    if len(artifacts) < 2:
        raise ValueError("Build both wheel and source distribution first")
    for artifact in artifacts:
        if artifact.suffix == ".whl":
            with zipfile.ZipFile(artifact) as archive:
                names = archive.namelist()
        else:
            with tarfile.open(artifact) as source:
                names = source.getnames()
        if any(".local_context" in n or "/.env" in n or "/.git/" in n for n in names):
            raise ValueError(f"Private files in {artifact.name}")
    print("Repository and release exclusions passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
