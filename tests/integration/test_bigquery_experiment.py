import copy
import json
from pathlib import Path

import pytest

from datavouch.adapters.bigquery import client
from datavouch.adapters.bigquery.collector import collect_rows
from datavouch.adapters.bigquery.experiments import prepare, run_command
from datavouch.adapters.bigquery.models import CollectionConfig, CollectionError
from datavouch.cli import main
from datavouch.core.configuration import read_json
from datavouch.verification.evaluation import verify
from datavouch.web.catalog import load_catalog

EXAMPLE = Path(__file__).resolve().parents[2] / "examples/bigquery/experiment"


@pytest.fixture
def inputs(tmp_path):
    for source in EXAMPLE.glob("*.json"):
        (tmp_path / source.name).write_bytes(source.read_bytes())
    return tmp_path


def change(path, edit):
    data = read_json(path)
    edit(data)
    path.write_text(json.dumps(data))


def run(inputs, name="result"):
    return main(
        [
            "run-bigquery",
            str(inputs / "plan.json"),
            "--fixtures",
            str(inputs / "baseline-jobs.json"),
            str(inputs / "candidate-jobs.json"),
            "--output-dir",
            str(inputs / name),
        ]
    )


def checks(inputs):
    return {c["name"]: c["status"] for c in read_json(inputs / "result/report.json")["checks"]}


def test_complete_workflow_replay_and_viewer(inputs, capsys):
    assert run(inputs) == 0
    report = read_json(inputs / "result/report.json")
    assert json.loads(capsys.readouterr().out) == report
    metric = report["performance"]["results"][0]
    assert metric["baseline_mean"] == 1000
    assert metric["candidate_mean"] == 800
    assert metric["regression_percent"] == pytest.approx(-20)
    document = read_json(inputs / "result/input.json")
    assert json.loads(json.dumps(verify(document))) == report
    view = load_catalog(inputs / "result/catalog.json")[0].experiments[0]
    assert view.available and view.status == "PASS"
    assert view.raw == (inputs / "result/report.json").read_bytes()
    assert len(document["assurance"]["started_at"]) == 6
    assert document["assurance"]["completed_at"]["synthetic-project/eu/candidate_1"].endswith(
        "10:00:01.800000+00:00"
    )
    collection = read_json(inputs / "result/candidate-collection.json")
    assert collection["schema_version"] == "bigquery-collection-0.2"
    assert collection["jobs"][0]["completed_at"]
    assert run(inputs, "repeat") == 0
    for artifact in (inputs / "result").iterdir():
        assert artifact.read_bytes() == (inputs / "repeat" / artifact.name).read_bytes()


@pytest.mark.parametrize("side", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "edit",
    [
        lambda rows: rows.pop(),
        lambda rows: rows[0].update(cache_hit=True),
        lambda rows: rows[0].update(fingerprint="ffff"),
        lambda rows: rows[0].update(end_time=None),
        lambda rows: rows[0].update(state="RUNNING"),
        lambda rows: rows.clear(),
    ],
)
def test_ineligible_cohort_cannot_pass(inputs, side, edit):
    change(inputs / f"{side}-jobs.json", edit)
    assert run(inputs) == 3
    assert checks(inputs)["performance"] == "UNKNOWN"
    assert checks(inputs)["reliability"] == "UNKNOWN"
    scopes = read_json(inputs / "result/collection-status.json")
    assert not scopes[side]["used"]
    assert not scopes[side]["eligible"]
    collection = read_json(inputs / f"result/{side}-collection.json")
    assert collection["jobs"] or collection["missing_job_ids"]


def test_completion_outside_window_withholds_whole_cohort(inputs):
    change(inputs / "candidate-jobs.json", lambda r: r[0].update(end_time="2026-11-19T00:00:00Z"))
    assert run(inputs) == 3
    scope = read_json(inputs / "result/collection-status.json")["candidate"]
    assert scope["eligible"] and not scope["fully_contained"] and not scope["used"]


def test_correctness_failure_dominates_faster_runtime(inputs):
    change(inputs / "plan.json", lambda p: p["assurance"]["evidence"][0].update(observed=False))
    assert run(inputs) == 1
    assert checks(inputs)["performance"] == "PASS"
    assert checks(inputs)["business_total"] == "FAIL"


def test_known_correctness_failure_dominates_missing_baseline(inputs):
    change(inputs / "baseline-jobs.json", lambda r: r.clear())
    change(inputs / "plan.json", lambda p: p["assurance"]["evidence"][0].update(observed=False))
    assert run(inputs) == 1


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p["assurance"].pop("evidence"),
        lambda p: p["assurance"].pop("reliability"),
        lambda p: p.pop("comparability"),
        lambda p: p["assurance"]["evidence"][0].update(experiment_id="another-experiment"),
        lambda p: p["assurance"]["evidence"][0].update(execution_ids=["unrelated-job"]),
    ],
)
def test_missing_or_misbound_assurances_are_unknown(inputs, edit):
    change(inputs / "plan.json", edit)
    assert run(inputs) == 3


def test_performance_regression(inputs):
    change(
        inputs / "candidate-jobs.json",
        lambda rows: [r.update(end_time="2026-11-18T10:00:03Z") for r in rows],
    )
    assert run(inputs) == 1
    assert checks(inputs)["performance"] == "FAIL"


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p.update(schema_version="future"),
        lambda p: p.update(synthetic="yes"),
        lambda p: p.update(extra=True),
        lambda p: p["candidate"].update(location="us"),
        lambda p: p["candidate"].update(project="another-project"),
        lambda p: p["candidate"]["workload"].update(input_snapshot="other-snapshot"),
        lambda p: p["candidate"].update(job_ids=["baseline_1"]),
        lambda p: p["change"].update(at="2026-11-16T12:00:00Z"),
        lambda p: p["policy"].update(minimum_samples=0),
        lambda p: p["assurance"].update(completed_at={}),
        lambda p: p["assurance"].update(required_checks=[]),
        lambda p: p.update(id="x" * 301),
    ],
)
def test_invalid_plan_rejected_before_cloud_or_output(inputs, monkeypatch, edit):
    change(inputs / "plan.json", edit)

    def forbidden(_):
        pytest.fail("Invalid input must not contact BigQuery")

    monkeypatch.setattr(client, "collect_live", forbidden)
    assert run_command(inputs / "plan.json", inputs / "result", None, True) == 2
    assert not (inputs / "result").exists()


def test_existing_directory_is_not_overwritten_or_queried(inputs, monkeypatch):
    (inputs / "result").mkdir()
    sentinel = inputs / "result/keep"
    sentinel.write_text("keep")
    monkeypatch.setattr(CollectionConfig, "validate_live_window", lambda *_: None)
    monkeypatch.setattr(client, "collect_live", lambda _: pytest.fail("Must not query"))
    assert run_command(inputs / "plan.json", inputs / "result", None, True) == 2
    assert sentinel.read_text() == "keep"


def test_live_orchestration_contract_and_sanitized_failure(inputs, monkeypatch, capsys):
    monkeypatch.setattr(CollectionConfig, "validate_live_window", lambda *_: None)
    calls = []

    def collect(config):
        calls.append(config)
        side = "baseline" if config.job_ids[0].startswith("baseline") else "candidate"
        return collect_rows(read_json(inputs / f"{side}-jobs.json"), config, source="bigquery")

    monkeypatch.setattr(client, "collect_live", collect)
    assert run_command(inputs / "plan.json", inputs / "live", None, True) == 0
    assert len(calls) == 2
    assert all(c.project == "synthetic-project" and c.location == "eu" for c in calls)
    capsys.readouterr()

    def denied(_):
        raise CollectionError("BigQuery access denied")

    monkeypatch.setattr(client, "collect_live", denied)
    assert run_command(inputs / "plan.json", inputs / "denied", None, True) == 2
    assert capsys.readouterr().err.strip() == "BigQuery access denied"
    assert not (inputs / "denied/catalog.json").exists()


def test_live_windows_both_checked_before_queries(inputs, monkeypatch):
    calls = []

    def window(config, now):
        calls.append(config)
        if len(calls) == 2:
            raise CollectionError("Window invalid")

    monkeypatch.setattr(CollectionConfig, "validate_live_window", window)
    monkeypatch.setattr(client, "collect_live", lambda _: pytest.fail("Must not query"))
    assert run_command(inputs / "plan.json", inputs / "result", None, True) == 2
    assert len(calls) == 2 and not (inputs / "result").exists()


def test_sources_required_and_exclusive(inputs):
    with pytest.raises(SystemExit):
        main(["run-bigquery", str(inputs / "plan.json"), "--output-dir", str(inputs / "result")])
    assert run_command(inputs / "plan.json", inputs / "result", None, False) == 2
    assert run_command(inputs / "plan.json", inputs / "result", [], True) == 2


def test_sensitive_provider_fields_not_persisted(inputs):
    change(
        inputs / "candidate-jobs.json",
        lambda r: r[0].update(
            query="PRIVATE_SQL",
            user_email="PRIVATE_EMAIL",
            error_result={"message": "PRIVATE_ERROR"},
        ),
    )
    assert run(inputs) == 0
    for artifact in (inputs / "result").iterdir():
        assert "PRIVATE_" not in artifact.read_text()


def test_prepare_does_not_mutate_config(inputs):
    document = read_json(inputs / "plan.json")
    original = copy.deepcopy(document)
    prepare(document)
    assert document == original


@pytest.mark.parametrize(
    ("baseline_failures", "candidate_failures", "maximum", "increase", "status"),
    [
        (0, 1, 0, 0, "FAIL"),
        (1, 0, 0, 0, "PASS"),
        (1, 1, 40, 0, "PASS"),
        (1, 2, 100, 0, "FAIL"),
        (0, 3, 100, 100, "PASS"),
    ],
)
def test_failed_jobs_count_for_reliability(
    inputs, baseline_failures, candidate_failures, maximum, increase, status
):
    for side, count in (("baseline", baseline_failures), ("candidate", candidate_failures)):
        change(
            inputs / f"{side}-jobs.json",
            lambda rows, count=count: [
                r.update(failure_reason="backendError") for r in rows[:count]
            ],
        )
    change(
        inputs / "plan.json",
        lambda p: p["assurance"]["reliability"].update(
            max_failure_percent=maximum, max_increase_points=increase
        ),
    )
    assert run(inputs) == (1 if status == "FAIL" else 3)
    assert checks(inputs)["reliability"] == status
    assert checks(inputs)["performance"] == "UNKNOWN"
    report = read_json(inputs / "result/report.json")
    rates = report["reliability_metrics"]
    assert rates["baseline_total"] == rates["candidate_total"] == 3
    assert rates["baseline_failures"] == baseline_failures
    assert rates["candidate_failures"] == candidate_failures
    assert rates["candidate_failure_percent"] == pytest.approx(candidate_failures / 3 * 100)
    document = read_json(inputs / "result/input.json")
    assert json.loads(json.dumps(verify(document))) == report
    view = load_catalog(inputs / "result/catalog.json")[0].experiments[0]
    assert view.raw == (inputs / "result/report.json").read_bytes()
    for side in ("baseline", "candidate"):
        scope = read_json(inputs / "result/collection-status.json")[side]
        assert scope["used"] and scope["reliability_eligible"]
    observations = (
        document["comparison"]["experiment"]["baseline"]["observations"]
        + document["comparison"]["experiment"]["candidate"]
    )
    failed = [o for o in observations if not o["execution"]["successful"]]
    assert len(failed) == baseline_failures + candidate_failures
    assert all(o["measurements"] == [] for o in failed)


@pytest.mark.parametrize("side", ["baseline", "candidate"])
@pytest.mark.parametrize(
    "edit",
    [
        lambda r: r.update(fingerprint=None),
        lambda r: r.update(cache_hit=True),
        lambda r: r.pop("cache_hit"),
        lambda r: r.update(state="RUNNING"),
        lambda r: r.update(statement_type="SCRIPT"),
        lambda r: r.update(parent_job_id="parent"),
        lambda r: r.update(end_time=None),
        lambda r: r.update(end_time="2026-11-20T00:00:00Z"),
    ],
)
def test_failed_job_with_other_exclusions_still_withholds_cohort(inputs, side, edit):
    def mutate(rows):
        rows[0].update(failure_reason="backendError")
        edit(rows[0])

    change(inputs / f"{side}-jobs.json", mutate)
    assert run(inputs) == 3
    assert checks(inputs)["reliability"] == "UNKNOWN"
    assert not read_json(inputs / "result/collection-status.json")[side]["used"]


@pytest.mark.parametrize(
    "edit",
    [
        lambda p: p["assurance"]["reliability"].update(complete=False),
        lambda p: p["assurance"].pop("reliability"),
        lambda p: p.pop("comparability"),
        lambda p: p["policy"].update(minimum_samples=4),
    ],
)
def test_failed_jobs_do_not_override_missing_assurances(inputs, edit):
    change(inputs / "candidate-jobs.json", lambda r: r[0].update(failure_reason="backendError"))
    change(inputs / "plan.json", edit)
    assert run(inputs) == 3
    assert checks(inputs)["reliability"] == "UNKNOWN"


def test_missing_job_prevents_partial_failure_rate(inputs):
    change(inputs / "candidate-jobs.json", lambda r: r[0].update(failure_reason="backendError"))
    change(inputs / "candidate-jobs.json", lambda r: r.pop())
    assert run(inputs) == 3
    assert checks(inputs)["reliability"] == "UNKNOWN"
    assert read_json(inputs / "result/report.json")["reliability_metrics"]["candidate_total"] == 0
