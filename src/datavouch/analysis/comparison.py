"""Descriptive comparisons with conservative evidence requirements."""

import math
from statistics import mean

from datavouch.core.models import (
    Direction,
    Experiment,
    Observation,
    Policy,
    Report,
    Status,
    VerificationResult,
)


def _eligibility(experiment: Experiment, policy: Policy) -> str | None:
    before, after = experiment.baseline.observations, experiment.candidate
    if len(before) < policy.minimum_samples or len(after) < policy.minimum_samples:
        return "Insufficient observations for the configured minimum sample count"
    if experiment.comparability is None:
        return "Missing explicit comparability evidence"
    observations = before + after
    if len({o.execution.id for o in observations}) != len(observations):
        return "Baseline and candidate execution IDs overlap"
    if len({o.workload for o in observations}) != 1:
        return "Workload, environment or input snapshot differs"
    if any(not o.execution.successful or o.execution.cached for o in observations):
        return "Failed or cached executions cannot support this comparison"
    if policy.normalize:
        if any(o.input_units is None or o.input_units == 0 for o in observations):
            return "Normalisation requires positive input volume for every execution"
        if len({o.input_unit for o in observations}) != 1:
            return "Normalisation input units differ"
    return None


def _values(observations: tuple[Observation, ...], policy: Policy) -> list[float] | None:
    values = []
    for observation in sorted(observations, key=lambda o: o.execution.id):
        measurement = next((m for m in observation.measurements if m.metric == policy.metric), None)
        if measurement is None:
            return None
        divisor = observation.input_units if policy.normalize else 1.0
        if divisor is None or divisor == 0:
            return None
        value = measurement.value / divisor
        if not math.isfinite(value) or (value == 0 and measurement.value != 0):
            return None
        values.append(value)
    return values


def compare(experiment: Experiment, policy: Policy) -> Report:
    """Evaluate one metric without implying correctness or causation."""
    reason = _eligibility(experiment, policy)
    unit = policy.metric.unit
    if policy.normalize and experiment.baseline.observations:
        unit += f"/{experiment.baseline.observations[0].input_unit or 'unknown'}"
    before = _values(experiment.baseline.observations, policy)
    after = _values(experiment.candidate, policy)
    if reason is None and (before is None or after is None):
        reason = "Missing metric, incompatible unit/direction or unrepresentable normalised value"
    baseline_mean = candidate_mean = regression = None
    status = Status.UNKNOWN
    if reason is None and before and after:
        # Exact intermediate summation avoids overflow and subnormal underflow.
        baseline_mean = mean(before)
        candidate_mean = mean(after)
        if baseline_mean == 0 and candidate_mean != 0:
            reason = "Zero baseline cannot support a relative change"
        else:
            regression = 0.0 if baseline_mean == 0 else (candidate_mean / baseline_mean - 1) * 100
            if policy.metric.direction == Direction.HIGHER:
                regression = -regression
            if not math.isfinite(regression):
                regression = None
                reason = "Relative change exceeds the supported numeric range"
            else:
                exceeds = regression > policy.max_regression_percent and not math.isclose(
                    regression, policy.max_regression_percent, rel_tol=1e-12, abs_tol=1e-12
                )
                status = Status.FAIL if exceeds else Status.PASS
                reason = (
                    "Regression exceeds threshold" if exceeds else "Within regression threshold"
                )
    result = VerificationResult(
        policy.metric.name,
        status,
        reason or "Insufficient evidence",
        unit,
        baseline_mean,
        candidate_mean,
        regression,
    )
    correctness = VerificationResult(
        "correctness", Status.UNKNOWN, "No supported correctness verification", "not applicable"
    )
    return Report(experiment, policy, (result, correctness))
