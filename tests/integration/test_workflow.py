"""Repeatable gate, policy precedence and report safety contracts."""

import copy
import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from datavouch.cli import main
from datavouch.workflow.commands import gate_command
from datavouch.workflow.gate import encoded, evaluate, html_report, markdown

ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT / "examples/verification/passing.json"
POLICY = ROOT / "examples/workflow/policy.json"


@pytest.fixture
def document():
    return json.loads(INPUT.read_text())


@pytest.fixture
def policy():
    return json.loads(POLICY.read_text())


@pytest.mark.parametrize("state", ["PASS", "FAIL", "UNKNOWN"])
@pytest.mark.parametrize("unknown", ["block", "allow"])
def test_gate_decisions(document, policy, state, unknown):
    if state == "FAIL":
        document["assurance"]["evidence"][0]["observed"] = False
        document["assurance"]["evidence"].pop()
    if state == "UNKNOWN":
        document["assurance"]["evidence"] = []
    policy["unknown"] = unknown
    result = evaluate(document, policy)
    expected = 1 if state == "FAIL" else 3 if state == "UNKNOWN" and unknown == "block" else 0
    assert result["evidence_status"] == state
    assert result["exit_code"] == expected
    if state == "UNKNOWN":
        assert result["gate_status"] == (
            "ALLOWED_UNKNOWN" if unknown == "allow" else "BLOCKED_UNKNOWN"
        )
    assert result["schema_version"] == "workflow-0.1"


def test_policy_overrides_thresholds_without_mutation(document, policy):
    original = copy.deepcopy(document)
    policy["comparison"]["max_regression_percent"] = 0
    for observation in document["comparison"]["experiment"]["candidate"]:
        observation["measurements"][0]["value"] = 101
    document["comparison"]["policy"]["max_regression_percent"] = 100
    snapshot = copy.deepcopy(document)
    assert evaluate(document, policy)["evidence_status"] == "FAIL"
    assert document == snapshot
    assert original != document


def test_policy_cannot_attest_complete(document, policy):
    document["assurance"]["reliability"]["complete"] = False
    assert evaluate(document, policy)["evidence_status"] == "UNKNOWN"
    policy["reliability"]["complete"] = True
    with pytest.raises(ValueError):
        evaluate(document, policy)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", "future"),
        ("unknown", "ignore"),
        ("unknown", True),
        ("required_checks", []),
        ("required_checks", ["a"] * 101),
        ("required_checks", ["x" * 301]),
        ("required_checks", [12]),
        ("required_checks", ["performance"]),
        ("required_checks", ["a", "a"]),
        ("comparison", {}),
        ("reliability", {"max_failure_percent": -1, "max_increase_points": 0}),
    ],
)
def test_invalid_policy(document, policy, field, value):
    policy[field] = value
    with pytest.raises((ValueError, TypeError)):
        evaluate(document, policy)


def test_determinism_and_fingerprints(document, policy):
    result = evaluate(document, policy)
    assert encoded(result) == (ROOT / "examples/workflow/expected_report.json").read_text()
    assert encoded(result) == encoded(evaluate(document, policy))
    policy["unknown"] = "allow"
    changed = evaluate(document, policy)
    assert changed["policy_sha256"] != result["policy_sha256"]
    assert changed["input_sha256"] == result["input_sha256"]
    assert changed["effective_input_sha256"] == result["effective_input_sha256"]
    assert "source" not in result
    assert "execution_ids" not in encoded(result)
    assert "synthetic-independent-check-fixture" not in encoded(result)


def test_report_injection(document, policy):
    malicious = "<script>alert(1)</script>\n| [link](https://example.com) @everyone"
    document["assurance"]["evidence"][0]["name"] = malicious
    policy["required_checks"][0] = malicious
    result = evaluate(document, policy)
    page = html_report(result)
    summary = markdown(result)
    assert "<script>" not in page
    assert "&lt;script&gt;" in page
    assert "https://example.com" not in summary
    assert "@everyone" not in summary
    assert "default-src" in page


@pytest.mark.parametrize(
    "path,expected",
    [
        ("verification/passing.json", 0),
        ("verification/incorrect.json", 1),
        ("workflow/unknown.json", 3),
    ],
)
def test_installed_cli_artifacts(tmp_path, path, expected):
    output = tmp_path / "reports"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "datavouch",
            "gate",
            str(ROOT / "examples" / path),
            "--policy",
            str(POLICY),
            "--output-dir",
            str(output),
        ],
        capture_output=True,
        check=False,
    )
    assert result.returncode == expected, result.stderr
    assert result.stdout == (output / "report.json").read_bytes()
    assert set(p.name for p in output.iterdir()) == {"report.json", "summary.md", "report.html"}
    assert json.loads(result.stdout)["exit_code"] == expected
    assert "DataVouch verification" in (output / "summary.md").read_text()


def test_default_read_only_and_cli_dispatch(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    assert main(["gate", str(INPUT), "--policy", str(POLICY)]) == 0
    assert not list(tmp_path.iterdir())
    assert json.loads(capsys.readouterr().out)["evidence_status"] == "PASS"


def test_existing_output_preserved(tmp_path, capsys):
    sentinel = tmp_path / "report.json"
    sentinel.write_text("keep this")
    assert gate_command(INPUT, POLICY, tmp_path) == 2
    assert sentinel.read_text() == "keep this"
    assert capsys.readouterr().out == ""


def test_symlink_output_rejected(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    assert gate_command(INPUT, POLICY, link) == 2
    assert not list(target.iterdir())


def test_invalid_input_generic(tmp_path, capsys):
    source = tmp_path / "private-input.json"
    source.write_text('{"secret": "do-not-display"}')
    assert gate_command(source, POLICY, None) == 2
    captured = capsys.readouterr()
    assert not captured.out
    assert "private-input" not in captured.err
    assert "do-not-display" not in captured.err


def test_write_error_blocks(tmp_path, capsys):
    with patch("pathlib.Path.write_text", side_effect=OSError("private detail")):
        assert gate_command(INPUT, POLICY, tmp_path / "reports") == 2
    assert "private detail" not in capsys.readouterr().err
