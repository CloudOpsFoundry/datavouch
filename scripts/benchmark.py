"""Measure offline comparison only, excluding JSON IO and network latency."""

import json
import platform
import statistics
import timeit
from dataclasses import replace
from pathlib import Path

from datavouch.analysis.comparison import compare
from datavouch.core.configuration import load
from datavouch.core.models import Baseline


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    experiment, policy = load(root / "examples/bigquery/comparison.json")
    before = experiment.baseline.observations[0]
    after = experiment.candidate[0]
    count = 1000
    experiment = replace(
        experiment,
        baseline=Baseline(
            tuple(
                replace(before, execution=replace(before.execution, id=f"b{i}"))
                for i in range(count)
            )
        ),
        candidate=tuple(
            replace(after, execution=replace(after.execution, id=f"a{i}")) for i in range(count)
        ),
    )
    compare(experiment, policy)
    durations = timeit.repeat(lambda: compare(experiment, policy), repeat=7, number=100)
    print(
        json.dumps(
            {
                "python": platform.python_version(),
                "platform": platform.system(),
                "observations_per_group": count,
                "iterations_per_repeat": 100,
                "repeats": 7,
                "median_ms_per_comparison": statistics.median(durations) * 10,
                "minimum_ms_per_comparison": min(durations) * 10,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
