"""Run required validation stages locally or as named CI steps. Fail on any error."""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STAGES = {
    "format": [["-m", "ruff", "format", "--check", "."]],
    "lint": [["-m", "ruff", "check", "."]],
    "workflows": [["scripts/check_workflows.py"]],
    "deployment": [["scripts/check_deployment.py"]],
    "types": [
        ["-m", "mypy"],
        [
            "-m",
            "mypy",
            "scripts/validate.py",
            "scripts/check_workflows.py",
        ],
        ["-m", "mypy", "examples/adapters/local_metrics.py", "examples/adapters/run_example.py"],
    ],
    "unit": [
        ["-m", "coverage", "run", "-m", "pytest", "tests/unit", "--junitxml=.ci-artifacts/unit.xml"]
    ],
    "contract": [
        [
            "-m",
            "coverage",
            "run",
            "--append",
            "-m",
            "pytest",
            "tests/contract",
            "examples/adapters",
            "--junitxml=.ci-artifacts/contract.xml",
        ]
    ],
    "integration": [
        [
            "-m",
            "coverage",
            "run",
            "--append",
            "-m",
            "pytest",
            "tests/integration",
            "--junitxml=.ci-artifacts/integration.xml",
        ]
    ],
    "coverage": [
        ["-m", "coverage", "report"],
        ["-m", "coverage", "xml", "-o", ".ci-artifacts/coverage.xml"],
    ],
    "security": [["-m", "bandit", "-q", "-r", "src"]],
    "dependencies": [["-m", "pip_audit", "--skip-editable"]],
    "build": [["-m", "build", "--sdist", "--wheel", "--no-isolation"]],
    "integrity": [["scripts/verify_repository.py"]],
    "installation": [["scripts/check_installation.py"]],
    "sdist": [["scripts/check_sdist.py"]],
    "release": [["scripts/check_release.py"]],
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", choices=["all", *STAGES], default="all")
    args = parser.parse_args(argv)
    (ROOT / ".ci-artifacts").mkdir(exist_ok=True)
    for stage, commands in STAGES.items():
        if args.stage not in ("all", stage):
            continue
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print(f"::group::Stage: {stage}", flush=True)
        print(f"Stage: {stage}", flush=True)
        for command in commands:
            print(f"Running: {sys.executable} {' '.join(command)}", flush=True)
            result = subprocess.run([sys.executable, *command], cwd=ROOT, check=False)
            if result.returncode:
                return result.returncode
        if os.environ.get("GITHUB_ACTIONS") == "true":
            print("::endgroup::", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
