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
        demo_result = subprocess.check_output(
            [str(command), "demo", "--output-dir", str(directory / "demo"), "--groups", "100"],
            cwd=directory,
        )
        demo = json.loads(demo_result)
        assert demo["results"][1]["status"] == "FAIL"
        assert demo["results"][2]["checks"]["weighted_total"] == "UNKNOWN"
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
        for status, expected_exit in (("FAIL", 1), ("UNKNOWN", 3)):
            gate_input = json.loads((ROOT / "examples/verification/passing.json").read_text())
            if status == "FAIL":
                gate_input["assurance"]["evidence"][0]["observed"] = False
            else:
                gate_input["assurance"]["evidence"] = []
            input_path = directory / f"gate-{status}.json"
            input_path.write_text(json.dumps(gate_input))
            output_path = directory / f"gate-{status}"
            gate_result = subprocess.run(
                [
                    str(command),
                    "gate",
                    str(input_path),
                    "--policy",
                    str(ROOT / "examples/workflow/policy.json"),
                    "--output-dir",
                    str(output_path),
                ],
                cwd=directory,
                capture_output=True,
                check=False,
            )
            if gate_result.returncode != expected_exit:
                raise ValueError(f"Installed gate did not block {status}")
            gate_report = json.loads(gate_result.stdout)
            expected_gate = "BLOCKED_UNKNOWN" if status == "UNKNOWN" else status
            if (
                gate_report["evidence_status"] != status
                or gate_report["gate_status"] != expected_gate
            ):
                raise ValueError(f"Installed gate lost {status} outcome")
            if gate_result.stdout != (output_path / "report.json").read_bytes():
                raise ValueError("Installed gate output differs from saved evidence")
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
        experiment_example = ROOT / "examples/bigquery/experiment"
        experiment_output = directory / "experiment"
        experiment_report = subprocess.check_output(
            [
                str(command),
                "run-bigquery",
                str(experiment_example / "plan.json"),
                "--fixtures",
                str(experiment_example / "baseline-jobs.json"),
                str(experiment_example / "candidate-jobs.json"),
                "--output-dir",
                str(experiment_output),
            ],
            cwd=directory,
        )
        replay = subprocess.check_output(
            [str(command), "verify", str(experiment_output / "input.json")],
            cwd=directory,
        )
        if experiment_report != replay or json.loads(replay)["overall_status"] != "PASS":
            raise ValueError("Installed BigQuery experiment failed deterministic replay")
        failure_output = directory / "failed-experiment"
        failed = subprocess.run(
            [
                str(command),
                "run-bigquery",
                str(experiment_example / "plan.json"),
                "--fixtures",
                str(experiment_example / "baseline-jobs.json"),
                str(experiment_example / "candidate-failed-jobs.json"),
                "--output-dir",
                str(failure_output),
            ],
            cwd=directory,
            capture_output=True,
            check=False,
        )
        replay_failed = subprocess.run(
            [str(command), "verify", str(failure_output / "input.json")],
            cwd=directory,
            capture_output=True,
            check=False,
        )
        if failed.returncode != 1 or replay_failed.returncode != 1:
            raise ValueError("Installed failed-job experiment must fail verification")
        if failed.stdout != replay_failed.stdout:
            raise ValueError("Installed failed-job experiment differs from replay")
        failure_report = json.loads(failed.stdout)
        outcomes = {check["name"]: check["status"] for check in failure_report["checks"]}
        if outcomes["reliability"] != "FAIL" or outcomes["performance"] != "UNKNOWN":
            raise ValueError("Installed failed-job experiment lost check separation")
    print("Clean wheel installation and report comparison passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
