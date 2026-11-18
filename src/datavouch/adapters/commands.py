"""Generic collection CLI; explicit adapters and explicit collection sources."""

import sys
from dataclasses import asdict
from pathlib import Path

from datavouch.adapters.contracts import API_VERSION
from datavouch.adapters.registry import builtin_registry, render
from datavouch.core.configuration import read_json


def adapters_command() -> int:
    print(
        render(
            {"api_version": API_VERSION, "adapters": [asdict(i) for i in builtin_registry().list()]}
        ),
        end="",
    )
    return 0


def collect_command(config: Path, fixture: Path | None, live: bool) -> int:
    try:
        report = builtin_registry().collect(read_json(config), fixture=fixture, live=live)
        output = render(report)
    except ValueError, TypeError, OSError, OverflowError, RecursionError:
        print(
            "Adapter collection failed. Check connector version, scope, source and dependencies.",
            file=sys.stderr,
        )
        return 2
    print(output, end="")
    return 0 if report["eligible"] else 3
