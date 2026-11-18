"""Failure rates for explicitly complete execution cohorts."""

from dataclasses import dataclass
from fractions import Fraction

from datavouch.core.models import Experiment, Status, nonnegative
from datavouch.verification.correctness import CheckResult


@dataclass(frozen=True, slots=True)
class ReliabilityPolicy:
    complete: bool
    max_failure_percent: float = 0.0
    max_increase_points: float = 0.0

    def __post_init__(self) -> None:
        if type(self.complete) is not bool:
            raise ValueError("Cohort completeness must be explicit")
        for value in (self.max_failure_percent, self.max_increase_points):
            nonnegative(value, "failure threshold")
            if value > 100:
                raise ValueError("Failure thresholds must not exceed 100")


def evaluate(
    experiment: Experiment, policy: ReliabilityPolicy, minimum_samples: int
) -> tuple[CheckResult, dict[str, int | float]]:
    before, after = experiment.baseline.observations, experiment.candidate
    counts = {
        "baseline_total": len(before),
        "candidate_total": len(after),
        "baseline_failures": sum(not o.execution.successful for o in before),
        "candidate_failures": sum(not o.execution.successful for o in after),
    }
    metrics: dict[str, int | float] = dict(counts)
    observations = before + after
    comparable = (
        experiment.comparability is not None
        and len({o.workload for o in observations}) == 1
        and len({o.execution.id for o in observations}) == len(observations)
    )
    if not comparable or not policy.complete or min(len(before), len(after)) < minimum_samples:
        return CheckResult(
            "reliability",
            Status.UNKNOWN,
            "Missing complete execution cohorts or insufficient samples",
        ), metrics
    baseline = Fraction(counts["baseline_failures"] * 100, len(before))
    candidate = Fraction(counts["candidate_failures"] * 100, len(after))
    metrics.update(
        baseline_failure_percent=float(baseline),
        candidate_failure_percent=float(candidate),
        increase_percentage_points=float(candidate - baseline),
    )
    failed = candidate > Fraction(
        str(policy.max_failure_percent)
    ) or candidate - baseline > Fraction(str(policy.max_increase_points))
    return CheckResult(
        "reliability",
        Status.FAIL if failed else Status.PASS,
        "Failure rate exceeds policy" if failed else "Failure rate is within policy",
    ), metrics
