"""Offline CLI for financial evidence assessment."""

import json
import sys
from pathlib import Path

from datavouch.core.configuration import read_json
from datavouch.core.models import Status
from datavouch.financial.evaluation import assess


def finance_command(path: Path) -> int:
    try:
        report = assess(read_json(path))
        output = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    except ValueError, TypeError, OSError, OverflowError, RecursionError:
        print(
            "Invalid or unreadable financial input. Check the documented schema.", file=sys.stderr
        )
        return 2
    print(output, end="")
    return {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 3}[report["status"]]
