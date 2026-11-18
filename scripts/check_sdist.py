"""Rebuild the wheel from its source archive and compare all packaged contents."""

import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    sources = list((ROOT / "dist").glob("*.tar.gz"))
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(sources) != 1 or len(wheels) != 1:
        raise ValueError("Expected one source archive and wheel")
    with tempfile.TemporaryDirectory(prefix="datavouch-sdist-") as folder:
        directory = Path(folder)
        with tarfile.open(sources[0]) as archive:
            archive.extractall(directory, filter="data")
        roots = list(directory.iterdir())
        if len(roots) != 1 or not (roots[0] / "pyproject.toml").is_file():
            raise ValueError("Invalid source archive layout")
        output = directory / "rebuilt"
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(output)],
            cwd=roots[0],
            check=True,
        )
        rebuilt = list(output.glob("*.whl"))
        if len(rebuilt) != 1:
            raise ValueError("Expected one rebuilt wheel")
        direct_output = directory / "direct"
        subprocess.run(
            [
                sys.executable,
                "-m",
                "build",
                "--wheel",
                "--no-isolation",
                "--outdir",
                str(direct_output),
            ],
            cwd=ROOT,
            check=True,
        )
        direct = list(direct_output.glob("*.whl"))
        if len(direct) != 1:
            raise ValueError("Expected one direct checkout wheel")
        with zipfile.ZipFile(direct[0]) as first, zipfile.ZipFile(rebuilt[0]) as second:
            if sorted(first.namelist()) != sorted(second.namelist()):
                raise ValueError("Source rebuild has different packaged files")
            if any(first.read(name) != second.read(name) for name in first.namelist()):
                raise ValueError("Source rebuild has different package contents")
    print("Source distribution rebuild matches every direct-checkout wheel member")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
