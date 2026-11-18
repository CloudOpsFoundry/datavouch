import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from datavouch.core.configuration import decode
from datavouch.core.models import Status, Workload
from datavouch.verification.correctness import CheckResult, decode_check, evaluate, instant
from datavouch.verification.evaluation import aggregate, verify
from datavouch.verification.reliability import ReliabilityPolicy
from datavouch.verification.reliability import evaluate as reliability
from datavouch.verification.windows import Windows, select

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/verification/passing.json"


@pytest.fixture
def document():
    return json.loads(EXAMPLE.read_text())


def test_all_configured_checks_pass(document):
    result = verify(document)
    assert result["overall_status"] == Status.PASS
    assert result["evidence_quality"] == {"PASS": 7, "FAIL": 0, "UNKNOWN": 0}
    assert result["performance"]["results"][0]["regression_percent"] == pytest.approx(-20)
    assert result["reliability_metrics"]["candidate_failure_percent"] == 0
    assert result == verify(copy.deepcopy(document))
    assert len(result["input_sha256"]) == 64


def test_fast_but_incorrect_is_failure(document):
    document["assurance"]["evidence"][0]["observed"] = False
    result = verify(document)
    assert result["performance"]["results"][0]["status"] == Status.PASS
    assert result["overall_status"] == Status.FAIL


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a.update(evidence=[]),
        lambda a: a.pop("windows"),
        lambda a: a.pop("completed_at"),
        lambda a: a["completed_at"].pop("a0"),
        lambda a: a.pop("reliability"),
        lambda a: a["reliability"].update(complete=False),
        lambda a: a["evidence"][0].update(reference=None),
        lambda a: a["evidence"][0].update(observed=None),
        lambda a: a["evidence"][0].update(experiment_id="unrelated"),
        lambda a: a["evidence"][0].update(execution_ids=["other"]),
        lambda a: a["evidence"][2].pop("method"),
        lambda a: a["evidence"][3].pop("as_of"),
        lambda a: a["evidence"][3].update(observed="2026-11-14T00:00:00Z"),
    ],
)
def test_missing_or_unrelated_evidence_is_unknown(document, change):
    change(document["assurance"])
    assert verify(document)["overall_status"] == Status.UNKNOWN


@pytest.mark.parametrize(
    "index,observed", [(1, ["total:STRING:NULLABLE"]), (2, "b" * 64), (3, "2026-11-12T00:00:00Z")]
)
def test_schema_checksum_and_freshness_failures(document, index, observed):
    document["assurance"]["evidence"][index]["observed"] = observed
    assert verify(document)["overall_status"] == Status.FAIL


def test_equal_row_counts_are_not_correctness(document):
    document["assurance"]["evidence"][0].update(kind="row_count", expected=10, observed=10)
    assert verify(document)["overall_status"] == Status.UNKNOWN


def test_failure_dominates_unknown(document):
    document["assurance"].pop("windows")
    document["assurance"]["evidence"][0]["observed"] = False
    assert verify(document)["overall_status"] == Status.FAIL
    assert aggregate(()) == Status.UNKNOWN


def test_failure_rates_are_independently_correct(document):
    document["comparison"]["experiment"]["candidate"][0]["execution"]["successful"] = False
    result = verify(document)
    assert result["overall_status"] == Status.FAIL
    assert result["reliability_metrics"]["candidate_failures"] == 1
    assert result["reliability_metrics"]["candidate_total"] == 3
    assert result["reliability_metrics"]["candidate_failure_percent"] == pytest.approx(100 / 3)
    assert result["reliability_metrics"]["increase_percentage_points"] == pytest.approx(100 / 3)


def test_rate_boundaries_and_normalized_volumes(document):
    exp, _ = decode(document["comparison"])
    before = tuple(
        replace(o, execution=replace(o.execution, successful=(i % 2 == 0)))
        for i, o in enumerate(exp.baseline.observations[:2])
    )
    after = tuple(
        replace(before[i % 2], execution=replace(before[i % 2].execution, id=f"new{i}"))
        for i in range(4)
    )
    exp = replace(exp, baseline=replace(exp.baseline, observations=before), candidate=after)
    result, rates = reliability(exp, ReliabilityPolicy(True, 50, 0), 2)
    assert result.status == Status.PASS
    assert rates["baseline_failure_percent"] == rates["candidate_failure_percent"] == 50
    assert reliability(exp, ReliabilityPolicy(True, 49.9, 0), 2)[0].status == Status.FAIL


def test_reliability_rejects_different_workloads(document):
    exp, policy = decode(document["comparison"])
    exp = replace(
        exp,
        candidate=tuple(
            replace(o, workload=Workload("other", "env", "snap")) for o in exp.candidate
        ),
    )
    assert (
        reliability(exp, ReliabilityPolicy(True), policy.minimum_samples)[0].status
        == Status.UNKNOWN
    )


def test_half_open_windows_and_baseline_selection(document):
    exp, _ = decode(document["comparison"])
    windows = Windows(**document["assurance"]["windows"])
    times = document["assurance"]["completed_at"]
    times["b0"] = windows.baseline_start
    document["assurance"]["started_at"]["b0"] = windows.baseline_start
    times["b1"] = windows.baseline_end
    chosen, excluded = select(exp, windows, times, document["assurance"]["started_at"])
    assert [o.execution.id for o in chosen.baseline.observations] == ["b0", "b2"]
    assert excluded == ("b1",)
    assert verify(document)["overall_status"] == Status.UNKNOWN


@pytest.mark.parametrize(
    "changes",
    [
        {"candidate_start": "2026-11-10T00:00:00Z"},
        {"change_at": "2026-11-09T00:00:00Z"},
        {"baseline_start": "2026-11-10"},
    ],
)
def test_invalid_windows(document, changes):
    document["assurance"]["windows"].update(changes)
    with pytest.raises(ValueError):
        verify(document)


@pytest.mark.parametrize(
    "change",
    [
        lambda a: a.update(required_checks=[]),
        lambda a: a.update(required_checks=["performance"]),
        lambda a: a.update(required_checks=["x", "x"]),
        lambda a: a.update(required_checks=[""]),
        lambda a: a.update(evidence={}),
        lambda a: a["evidence"].append(a["evidence"][0]),
        lambda a: a["evidence"][0].update(name="unrequested"),
        lambda a: a.update(extra=True),
        lambda a: a.update(completed_at=[]),
        lambda a: a["evidence"][0].update(kind="python"),
        lambda a: a["evidence"][0].update(observed=1),
        lambda a: a["evidence"][0].update(execution_ids="a0"),
        lambda a: a["evidence"][0].update(execution_ids=["a0", "a0"]),
        lambda a: a["evidence"][0].update(extra=True),
        lambda a: a["evidence"][1].update(observed=[]),
        lambda a: a["evidence"][1].update(observed=["x", "x"]),
        lambda a: a["evidence"][2].update(observed="bad hash"),
        lambda a: a["evidence"][3].update(expected=-1),
        lambda a: a["evidence"][3].update(observed=False),
        lambda a: a["reliability"].update(complete=1),
        lambda a: a["reliability"].update(max_failure_percent=101),
        lambda a: a["reliability"].update(max_increase_points=-1),
    ],
)
def test_bad_evidence_is_rejected(document, change):
    change(document["assurance"])
    with pytest.raises(ValueError):
        verify(document)


def test_window_inputs_and_empty_correctness_scope(document):
    exp, _ = decode(document["comparison"])
    windows = Windows(**document["assurance"]["windows"])
    with pytest.raises(ValueError):
        select(exp, windows, {}, {})
    with pytest.raises(ValueError):
        select(replace(exp, candidate=exp.baseline.observations), windows, {}, {})
    check = replace(decode_check(document["assurance"]["evidence"][0]), execution_ids=())
    assert evaluate(check, replace(exp, candidate=())).status == Status.UNKNOWN
    with pytest.raises(ValueError):
        replace(check, execution_ids=[])
    with pytest.raises(ValueError):
        replace(check, kind="row_count", expected=True, observed=True)
    with pytest.raises(ValueError):
        instant(None)
    assert aggregate((CheckResult("x", Status.PASS, "passed"),)) == Status.PASS


def test_execution_crossing_window_is_excluded(document):
    document["assurance"]["completed_at"]["a0"] = "2026-11-14T00:00:00Z"
    result = verify(document)
    assert result["excluded_execution_ids"] == ("a0",)
    assert result["overall_status"] == Status.UNKNOWN


def test_execution_started_before_change_is_excluded(document):
    document["assurance"]["started_at"]["a0"] = "2026-11-10T00:00:00Z"
    assert verify(document)["excluded_execution_ids"] == ("a0",)


def test_execution_start_after_end_is_invalid(document):
    document["assurance"]["started_at"]["a0"] = "2026-11-14T00:00:00Z"
    with pytest.raises(ValueError):
        verify(document)


def test_freshness_evaluation_before_output_is_unknown(document):
    document["assurance"]["evidence"][3].update(
        as_of="2026-11-12T11:00:00Z", observed="2026-11-12T11:00:00Z"
    )
    assert verify(document)["overall_status"] == Status.UNKNOWN


def test_missing_start_times_is_unknown(document):
    document["assurance"].pop("started_at")
    assert verify(document)["overall_status"] == Status.UNKNOWN
