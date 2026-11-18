"""Select reproducible cohorts using explicit execution-time windows."""

from dataclasses import dataclass, replace

from datavouch.core.models import Baseline, Experiment
from datavouch.verification.correctness import instant


@dataclass(frozen=True, slots=True)
class Windows:
    baseline_start: str
    baseline_end: str
    change_at: str
    candidate_start: str
    candidate_end: str

    def __post_init__(self) -> None:
        a, b, change, c, d = (
            instant(v)
            for v in (
                self.baseline_start,
                self.baseline_end,
                self.change_at,
                self.candidate_start,
                self.candidate_end,
            )
        )
        if not a < b <= change <= c < d:
            raise ValueError("Require disjoint chronological windows around the change")


def select(
    experiment: Experiment,
    windows: Windows,
    completed_at: dict[str, str],
    started_at: dict[str, str],
) -> tuple[Experiment, tuple[str, ...]]:
    """Select executions fully contained in each half-open window."""
    all_observations = experiment.baseline.observations + experiment.candidate
    ids = {o.execution.id for o in all_observations}
    if len(ids) != len(all_observations):
        raise ValueError("Execution cohorts overlap")
    if set(completed_at) != ids or set(started_at) != ids:
        raise ValueError("Completion times must cover exactly the supplied executions")
    times = {key: instant(value) for key, value in completed_at.items()}
    starts = {key: instant(value) for key, value in started_at.items()}
    if any(starts[key] > times[key] for key in ids):
        raise ValueError("Execution start must not follow completion")
    before = tuple(
        o
        for o in experiment.baseline.observations
        if instant(windows.baseline_start) <= starts[o.execution.id]
        and times[o.execution.id] < instant(windows.baseline_end)
    )
    after = tuple(
        o
        for o in experiment.candidate
        if instant(windows.candidate_start) <= starts[o.execution.id]
        and times[o.execution.id] < instant(windows.candidate_end)
    )
    selected = {o.execution.id for o in before + after}
    return replace(experiment, baseline=Baseline(before), candidate=after), tuple(
        sorted(ids - selected)
    )
