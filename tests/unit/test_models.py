from dataclasses import FrozenInstanceError

import pytest

from datavouch.core.models import (
    Baseline,
    Change,
    Evidence,
    Execution,
    Experiment,
    Measurement,
    Metric,
    Observation,
    Policy,
    Workload,
)

M = Metric("runtime", "ms")
W = Workload("workload", "test", "snapshot")
OBSERVATION = Observation(W, Execution("1"), (Measurement(M, 10),))


@pytest.mark.parametrize("value", [-1, float("nan"), float("inf"), float("-inf"), True, "10", None])
def test_invalid_measurement(value):
    with pytest.raises(ValueError):
        Measurement(M, value)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: Workload("", "test", "s"),
        lambda: Workload("w", " ", "s"),
        lambda: Metric("x", ""),
        lambda: Metric("x", "ms", "lower"),
        lambda: Measurement("metric", 1),
        lambda: Execution(""),
        lambda: Execution("x", 1),
        lambda: Change("", "x"),
        lambda: Evidence("x", ""),
        lambda: Observation("w", Execution("x"), ()),
        lambda: Observation(W, Execution("x"), []),
        lambda: Observation(W, Execution("x"), (Measurement(M, 1), Measurement(M, 2))),
        lambda: Observation(W, Execution("x"), (), 1),
        lambda: Observation(W, Execution("x"), (), None, "rows"),
        lambda: Baseline([OBSERVATION]),
        lambda: Baseline((OBSERVATION, OBSERVATION)),
        lambda: Experiment("", Baseline(()), (), Change("c", "d")),
        lambda: Experiment("e", (), (), Change("c", "d")),
        lambda: Experiment("e", Baseline(()), (), Change("c", "d"), "evidence"),
        lambda: Policy("metric"),
        lambda: Policy(M, -1),
        lambda: Policy(M, minimum_samples=0),
        lambda: Policy(M, minimum_samples=True),
        lambda: Policy(M, normalize=1),
    ],
)
def test_invalid_records(factory):
    with pytest.raises(ValueError):
        factory()


def test_observations_are_immutable():
    with pytest.raises(FrozenInstanceError):
        OBSERVATION.input_units = 1


def test_unrepresentable_integer_is_invalid():
    with pytest.raises(ValueError):
        Measurement(M, 10**400)
