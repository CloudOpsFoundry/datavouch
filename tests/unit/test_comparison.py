import json
from dataclasses import replace

import pytest

from datavouch.analysis.comparison import compare
from datavouch.core.models import (
    Baseline,
    Change,
    Direction,
    Evidence,
    Execution,
    Experiment,
    Measurement,
    Metric,
    Observation,
    Policy,
    Status,
    Workload,
)
from datavouch.reports.json_report import render

METRIC = Metric("runtime", "ms")
WORKLOAD = Workload("daily", "test", "snapshot-1")


def experiment(before=(100, 110, 90), after=(80, 85, 75), metric=METRIC):
    def group(values, prefix):
        return tuple(
            Observation(WORKLOAD, Execution(f"{prefix}{i}"), (Measurement(metric, v),), 10, "rows")
            for i, v in enumerate(values)
        )

    return Experiment(
        "exp-1",
        Baseline(group(before, "b")),
        group(after, "a"),
        Change("c1", "rewrite"),
        Evidence("fixture", "controlled synthetic data"),
    )


@pytest.mark.parametrize(
    "after,status,regression",
    [
        ((80, 85, 75), Status.PASS, -20),
        ((100, 100, 100), Status.PASS, 0),
        ((120, 120, 120), Status.FAIL, 20),
        ((105, 105, 105), Status.PASS, 5),
    ],
)
def test_independent_expected_values(after, status, regression):
    result = compare(experiment(after=after), Policy(METRIC, 5)).results[0]
    assert result.baseline_mean == 100
    assert result.candidate_mean == sum(after) / 3
    assert result.regression_percent == pytest.approx(regression)
    assert result.status == status


def test_higher_is_better():
    metric = Metric("throughput", "rows/s", Direction.HIGHER)
    result = compare(experiment(metric=metric), Policy(metric)).results[0]
    assert result.status == Status.FAIL
    assert result.regression_percent == pytest.approx(20)


@pytest.mark.parametrize(
    "before,after,status",
    [
        ((0, 0, 0), (0, 0, 0), Status.PASS),
        ((0, 0, 0), (1, 1, 1), Status.UNKNOWN),
        ((1, 1, 1), (0, 0, 0), Status.PASS),
        ((), (), Status.UNKNOWN),
        ((1,), (1,), Status.UNKNOWN),
    ],
)
def test_zero_and_missing(before, after, status):
    assert compare(experiment(before, after), Policy(METRIC)).results[0].status == status


def test_normalisation():
    exp = experiment(after=(160, 170, 150))
    exp = replace(exp, candidate=tuple(replace(o, input_units=20) for o in exp.candidate))
    result = compare(exp, Policy(METRIC, normalize=True)).results[0]
    assert result.baseline_mean == 10
    assert result.candidate_mean == 8
    assert result.regression_percent == pytest.approx(-20)
    assert result.unit == "ms/rows"


@pytest.mark.parametrize(
    "mutation",
    [
        lambda e: replace(e, comparability=None),
        lambda e: replace(e, candidate=e.baseline.observations),
        lambda e: replace(
            e,
            candidate=tuple(
                replace(o, workload=replace(o.workload, id="other")) for o in e.candidate
            ),
        ),
        lambda e: replace(
            e,
            candidate=tuple(
                replace(o, workload=replace(o.workload, environment="other")) for o in e.candidate
            ),
        ),
        lambda e: replace(
            e,
            candidate=tuple(
                replace(o, workload=replace(o.workload, input_snapshot="other"))
                for o in e.candidate
            ),
        ),
        lambda e: replace(e, candidate=tuple(replace(o, measurements=()) for o in e.candidate)),
        lambda e: replace(
            e,
            candidate=tuple(
                replace(o, execution=replace(o.execution, successful=False)) for o in e.candidate
            ),
        ),
        lambda e: replace(
            e,
            candidate=tuple(
                replace(o, execution=replace(o.execution, cached=True)) for o in e.candidate
            ),
        ),
        lambda e: replace(
            e,
            candidate=tuple(
                replace(o, measurements=(Measurement(Metric("runtime", "s"), 1),))
                for o in e.candidate
            ),
        ),
    ],
)
def test_ineligible_comparisons(mutation):
    report = compare(mutation(experiment()), Policy(METRIC))
    assert report.results[0].status == Status.UNKNOWN
    assert report.results[0].reason


@pytest.mark.parametrize("units,label", [(None, None), (0, "rows"), (10, "bytes")])
def test_invalid_normalisation_evidence(units, label):
    exp = experiment()
    exp = replace(
        exp, candidate=tuple(replace(o, input_units=units, input_unit=label) for o in exp.candidate)
    )
    assert compare(exp, Policy(METRIC, normalize=True)).results[0].status == Status.UNKNOWN


def test_report_reproducible_and_keeps_missing_correctness():
    exp = experiment()
    report = compare(exp, Policy(METRIC))
    assert report.results[1].status == Status.UNKNOWN
    shuffled = replace(
        exp,
        candidate=tuple(reversed(exp.candidate)),
        baseline=Baseline(tuple(reversed(exp.baseline.observations))),
    )
    assert render(report) == render(compare(shuffled, Policy(METRIC)))
    data = json.loads(render(report))
    assert len(data["input_sha256"]) == 64
    assert len(data["experiment"]["candidate"]) == 3
    assert data["schema_version"] == "0.1"


@pytest.mark.parametrize(
    "before,after", [((1e-300,) * 3, (1e300,) * 3), ((1e308,) * 3, (1e308,) * 3)]
)
def test_extreme_values_produce_finite_json(before, after):
    report = compare(experiment(before, after), Policy(METRIC))
    assert "Infinity" not in render(report)
    assert "NaN" not in render(report)


def test_normalisation_overflow_is_unknown():
    exp = experiment(after=(1e308,) * 3)
    exp = replace(exp, candidate=tuple(replace(o, input_units=1e-300) for o in exp.candidate))
    assert compare(exp, Policy(METRIC, normalize=True)).results[0].status == Status.UNKNOWN


def test_subnormal_measurements_are_not_rounded_to_zero():
    result = compare(experiment((5e-324,) * 3, (1e-323,) * 3), Policy(METRIC)).results[0]
    assert result.baseline_mean == 5e-324
    assert result.candidate_mean == 1e-323
    assert result.regression_percent == 100
    assert result.status == Status.FAIL


def test_normalisation_underflow_is_unknown():
    exp = experiment(after=(1e-300,) * 3)
    exp = replace(exp, candidate=tuple(replace(o, input_units=1e300) for o in exp.candidate))
    assert compare(exp, Policy(METRIC, normalize=True)).results[0].status == Status.UNKNOWN
