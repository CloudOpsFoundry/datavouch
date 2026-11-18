"""Run a trusted contributor adapter without changing DataVouch core code."""

from pathlib import Path

from local_metrics import LocalMetricsAdapter

from datavouch.adapters.registry import Registry, render
from datavouch.core.configuration import read_json


def main() -> None:
    here = Path(__file__).parent
    registry = Registry()
    registry.register(LocalMetricsAdapter())
    report = registry.collect(
        read_json(here / "baseline_connector.json"), fixture=here / "baseline.json"
    )
    print(render(report), end="")


if __name__ == "__main__":
    main()
