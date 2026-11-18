"""Machine-readable exit statuses and opt-in local report artifacts."""

import sys
from pathlib import Path

from datavouch.core.configuration import read_json
from datavouch.workflow.gate import encoded, evaluate, write_reports


def gate_command(path: Path, policy: Path, output_dir: Path | None) -> int:
    try:
        report = evaluate(read_json(path), read_json(policy))
        if output_dir is not None:
            write_reports(output_dir, report)
        output = encoded(report)
    except (ValueError, TypeError, OSError, OverflowError, RecursionError):
        print(
            "Workflow gate error: check input, policy and a new writable output directory.",
            file=sys.stderr,
        )
        return 2
    print(output, end="")
    return int(report["exit_code"])
