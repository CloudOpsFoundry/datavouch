"""Immutable, provider independent measurement contracts."""

import math
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    # A verification outcome, not a credential.
    PASS = "PASS"  # nosec B105
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class Direction(StrEnum):
    LOWER = "lower"
    HIGHER = "higher"


def nonempty(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty string")


def nonnegative(value: float, name: str) -> None:
    if type(value) not in (int, float) or value < 0 or value > 1.7976931348623157e308:
        raise ValueError(f"{name} must be a finite nonnegative number")
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite nonnegative number")


@dataclass(frozen=True, slots=True)
class Workload:
    id: str
    environment: str
    input_snapshot: str

    def __post_init__(self) -> None:
        for name in ("id", "environment", "input_snapshot"):
            nonempty(getattr(self, name), name)


@dataclass(frozen=True, slots=True)
class Metric:
    name: str
    unit: str
    direction: Direction = Direction.LOWER

    def __post_init__(self) -> None:
        nonempty(self.name, "metric name")
        nonempty(self.unit, "metric unit")
        if not isinstance(self.direction, Direction):
            raise ValueError("Invalid metric direction")


@dataclass(frozen=True, slots=True)
class Measurement:
    metric: Metric
    value: float

    def __post_init__(self) -> None:
        if not isinstance(self.metric, Metric):
            raise ValueError("Expected a Metric")
        nonnegative(self.value, "measurement")


@dataclass(frozen=True, slots=True)
class Execution:
    id: str
    successful: bool = True
    cached: bool = False

    def __post_init__(self) -> None:
        nonempty(self.id, "execution id")
        if type(self.successful) is not bool or type(self.cached) is not bool:
            raise ValueError("Execution flags must be booleans")


@dataclass(frozen=True, slots=True)
class Observation:
    workload: Workload
    execution: Execution
    measurements: tuple[Measurement, ...]
    input_units: float | None = None
    input_unit: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.workload, Workload) or not isinstance(self.execution, Execution):
            raise ValueError("Expected workload and execution records")
        if not isinstance(self.measurements, tuple) or not all(
            isinstance(m, Measurement) for m in self.measurements
        ):
            raise ValueError("Measurements must be an immutable tuple")
        names = [m.metric.name for m in self.measurements]
        if len(set(names)) != len(names):
            raise ValueError("Duplicate metric names")
        if self.input_units is not None:
            nonnegative(self.input_units, "input units")
            if self.input_unit is None:
                raise ValueError("Input units require a unit label")
            nonempty(self.input_unit, "input unit label")
        elif self.input_unit is not None:
            raise ValueError("Input unit label requires a measurement")


@dataclass(frozen=True, slots=True)
class Baseline:
    observations: tuple[Observation, ...]

    def __post_init__(self) -> None:
        validate_observations(self.observations)


def validate_observations(observations: tuple[Observation, ...]) -> None:
    if not isinstance(observations, tuple) or not all(
        isinstance(o, Observation) for o in observations
    ):
        raise ValueError("Observations must be an immutable tuple")
    ids = [o.execution.id for o in observations]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate execution IDs")


@dataclass(frozen=True, slots=True)
class Change:
    id: str
    description: str

    def __post_init__(self) -> None:
        nonempty(self.id, "change id")
        nonempty(self.description, "change description")


@dataclass(frozen=True, slots=True)
class Evidence:
    reference: str
    statement: str

    def __post_init__(self) -> None:
        nonempty(self.reference, "evidence reference")
        nonempty(self.statement, "evidence statement")


@dataclass(frozen=True, slots=True)
class Experiment:
    id: str
    baseline: Baseline
    candidate: tuple[Observation, ...]
    change: Change
    comparability: Evidence | None = None

    def __post_init__(self) -> None:
        nonempty(self.id, "experiment id")
        if not isinstance(self.baseline, Baseline) or not isinstance(self.change, Change):
            raise ValueError("Expected baseline and change records")
        validate_observations(self.candidate)
        if self.comparability is not None and not isinstance(self.comparability, Evidence):
            raise ValueError("Expected comparability evidence")


@dataclass(frozen=True, slots=True)
class Policy:
    metric: Metric
    max_regression_percent: float = 0.0
    minimum_samples: int = 3
    normalize: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.metric, Metric):
            raise ValueError("Expected a metric")
        nonnegative(self.max_regression_percent, "regression threshold")
        if type(self.minimum_samples) is not int or self.minimum_samples < 1:
            raise ValueError("Minimum samples must be a positive integer")
        if type(self.normalize) is not bool:
            raise ValueError("Normalize must be a boolean")


@dataclass(frozen=True, slots=True)
class VerificationResult:
    check: str
    status: Status
    reason: str
    unit: str
    baseline_mean: float | None = None
    candidate_mean: float | None = None
    regression_percent: float | None = None


@dataclass(frozen=True, slots=True)
class Report:
    experiment: Experiment
    policy: Policy
    results: tuple[VerificationResult, ...]
    limitations: tuple[str, ...] = (
        "Descriptive comparison only. No statistical confidence or causal attribution.",
        "Comparability is caller supplied and is not independently verified.",
        "This metric-only report does not evaluate correctness, reliability or financial impact.",
    )
