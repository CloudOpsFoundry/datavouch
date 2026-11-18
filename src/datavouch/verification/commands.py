"""Command orchestration for full configured verification."""

import json
import sys
from pathlib import Path

from datavouch.core.configuration import read_json
from datavouch.core.models import Status
from datavouch.verification.evaluation import verify


def verify_command(path: Path) -> int:
    try:
        report = verify(read_json(path))
        output = json.dumps(report, sort_keys=True, indent=2, allow_nan=False) + "\n"
    except (ValueError, TypeError, OSError, OverflowError, RecursionError):
        print(
            "Invalid or unreadable verification input. Check the documented schema.",
            file=sys.stderr,
        )
        return 2
    print(output, end="")
    return {Status.PASS: 0, Status.FAIL: 1, Status.UNKNOWN: 3}[report["overall_status"]]
