"""Fail the final CI gate unless every required job completed successfully."""

import json
import os
from pathlib import Path

REQUIRED = frozenset({"quality", "tests", "audit", "package"})


def passed(results: object) -> bool:
    return (
        isinstance(results, dict)
        and set(results) == REQUIRED
        and all(
            isinstance(value, dict) and value.get("result") == "success"
            for value in results.values()
        )
    )


def main() -> int:
    results = json.loads(os.environ["CI_RESULTS"])
    success = passed(results)
    lines = ["| Stage | Result |", "| --- | --- |"]
    for name in sorted(REQUIRED):
        value = results.get(name, {}) if isinstance(results, dict) else {}
        result = value.get("result", "missing") if isinstance(value, dict) else "invalid"
        # Only known GitHub result labels are written into the summary.
        if result not in {"success", "failure", "cancelled", "skipped", "missing"}:
            result = "invalid"
        lines.append(f"| {name} | {result} |")
    lines.append("\nCI passed" if success else "\nCI failed: every required stage must succeed")
    summary = "\n".join(lines) + "\n"
    print(summary, end="")
    if destination := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(destination).open("a") as stream:
            stream.write(summary)
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
