"""Run required local checks. Stop on the first failure."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    commands = [
        ["-m", "ruff", "format", "--check", "."],
        ["-m", "ruff", "check", "."],
        ["-m", "mypy"],
        ["-m", "mypy", "examples/adapters/local_metrics.py", "examples/adapters/run_example.py"],
        ["-m", "coverage", "run", "-m", "pytest"],
        ["-m", "coverage", "report"],
        ["-m", "bandit", "-q", "-r", "src"],
        ["-m", "pip_audit", "--skip-editable"],
        ["-m", "build", "--no-isolation"],
        ["scripts/verify_repository.py"],
        ["scripts/check_installation.py"],
        ["scripts/check_sdist.py"],
        ["scripts/check_release.py"],
    ]
    for args in commands:
        print(f"Running: {sys.executable} {' '.join(args)}", flush=True)
        result = subprocess.run([sys.executable, *args], cwd=ROOT, check=False)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
