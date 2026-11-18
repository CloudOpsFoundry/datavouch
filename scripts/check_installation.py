"""Verify the wheel in a clean environment outside the checkout."""

import json
import os
import subprocess
import tempfile
import venv
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    wheels = list((ROOT / "dist").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one built wheel")
    with zipfile.ZipFile(wheels[0]) as archive:
        if "datavouch/py.typed" not in archive.namelist():
            raise ValueError("Missing external typing marker")
        for asset in (
            "templates/base.html",
            "templates/experiment.html",
            "static/styles.css",
            "static/favicon.svg",
        ):
            if f"datavouch/web/{asset}" not in archive.namelist():
                raise ValueError(f"Missing viewer asset: {asset}")
    with tempfile.TemporaryDirectory(prefix="datavouch-install-") as folder:
        directory = Path(folder)
        venv.EnvBuilder(with_pip=True).create(directory / "env")
        binary = directory / "env" / ("Scripts" if os.name == "nt" else "bin")
        python = binary / ("python.exe" if os.name == "nt" else "python")
        subprocess.run(
            [str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheels[0])],
            cwd=directory,
            check=True,
        )
        subprocess.run([str(python), "-m", "datavouch", "--version"], cwd=directory, check=True)
        command = binary / ("datavouch.exe" if os.name == "nt" else "datavouch")
        result = subprocess.check_output(
            [str(command), "compare", str(ROOT / "examples/bigquery/comparison.json")],
            cwd=directory,
        )
        expected = (ROOT / "examples/bigquery/expected_report.json").read_bytes()
        if result != expected:
            raise ValueError("Installed wheel report differs from the fixture")
        collected = subprocess.check_output(
            [
                str(command),
                "collect-bigquery",
                str(ROOT / "examples/bigquery/collection_config.json"),
                "--fixture",
                str(ROOT / "examples/bigquery/jobs.json"),
            ],
            cwd=directory,
        )
        if collected != (ROOT / "examples/bigquery/expected_collection.json").read_bytes():
            raise ValueError("Installed wheel collection differs from the fixture")
        verified = subprocess.check_output(
            [str(command), "verify", str(ROOT / "examples/verification/passing.json")],
            cwd=directory,
        )
        if verified != (ROOT / "examples/verification/expected_report.json").read_bytes():
            raise ValueError("Installed verification report differs from the fixture")
        financial = subprocess.check_output(
            [str(command), "finance", str(ROOT / "examples/financial/reviewed.json")],
            cwd=directory,
        )
        if financial != (ROOT / "examples/financial/expected_report.json").read_bytes():
            raise ValueError("Installed financial report differs from the fixture")
        gated = subprocess.check_output(
            [
                str(command),
                "gate",
                str(ROOT / "examples/verification/passing.json"),
                "--policy",
                str(ROOT / "examples/workflow/policy.json"),
                "--output-dir",
                str(directory / "reports"),
            ],
            cwd=directory,
        )
        if gated != (ROOT / "examples/workflow/expected_report.json").read_bytes():
            raise ValueError("Installed workflow report differs from the fixture")
        if gated != (directory / "reports/report.json").read_bytes():
            raise ValueError("Installed workflow artifact differs from stdout")
        adapter_output = subprocess.check_output(
            [
                str(command),
                "collect",
                str(ROOT / "examples/adapters/bigquery_connector.json"),
                "--fixture",
                str(ROOT / "examples/bigquery/jobs.json"),
            ],
            cwd=directory,
        )
        if adapter_output != (ROOT / "examples/adapters/expected_bigquery.json").read_bytes():
            raise ValueError("Installed adapter collection differs from the fixture")
        subprocess.run(
            [str(command), "adapters"], cwd=directory, check=True, stdout=subprocess.DEVNULL
        )
        extension_output = subprocess.check_output(
            [str(python), str(ROOT / "examples/adapters/run_example.py")],
            cwd=directory,
        )
        extension = json.loads(extension_output)
        if not extension["eligible"] or len(extension["observations"]) != 3:
            raise ValueError("Independent adapter failed against the installed wheel")
    print("Clean wheel installation and report comparison passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
