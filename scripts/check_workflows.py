"""Validate repository workflows with actionlint."""

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    actionlint = shutil.which("actionlint")
    if actionlint is None:
        raise SystemExit("Install actionlint 1.7.12 before running workflow checks")
    # ShellCheck and Pyflakes are not bundled. Python is covered by Ruff and mypy.
    subprocess.run([actionlint, "-shellcheck=", "-pyflakes="], cwd=ROOT, check=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
