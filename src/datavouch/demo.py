"""Execute a bounded, local SQL example and verify measured evidence with the product engine."""

import json
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter_ns
from typing import Any

from datavouch.verification.evaluation import verify

BASELINE = """SELECT SUM((SELECT SUM(quantity * ticket_price_cents)
FROM tickets WHERE tickets.booking_id = bookings.id)) FROM bookings"""
CANDIDATES = {
    "equivalent": "SELECT SUM(quantity * ticket_price_cents) FROM tickets",
    "incorrect": "SELECT SUM(ticket_price_cents) FROM tickets",
}


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n")
    path.chmod(0o600)


def observe(connection: sqlite3.Connection, sql: str, prefix: str) -> list[dict[str, Any]]:
    result = []
    for index in range(3):
        started = timestamp()
        before = perf_counter_ns()
        total = connection.execute(sql).fetchone()[0]
        elapsed_ms = (perf_counter_ns() - before) / 1_000_000
        result.append(
            {
                "id": f"{prefix}-{index}",
                "started": started,
                "completed": timestamp(),
                "runtime_ms": elapsed_ms,
                "total_cents": total,
            }
        )
    return result


def document(
    name: str,
    baseline: list[dict[str, Any]],
    candidate: list[dict[str, Any]],
    expected: int,
    change_at: str,
    snapshot: str,
    *,
    missing: bool = False,
) -> dict[str, Any]:
    metric = {"name": "runtime", "unit": "ms", "direction": "lower"}
    workload = {"id": "ticket-sales", "environment": "local-sqlite", "input_snapshot": snapshot}

    def observation(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "workload": workload,
            "execution": {"id": row["id"], "successful": True},
            "measurements": [{"metric": metric, "value": row["runtime_ms"]}],
        }

    experiment_id = "local-ticket-sales-" + name
    return {
        "comparison": {
            "experiment": {
                "id": experiment_id,
                "baseline": {"observations": [observation(row) for row in baseline]},
                "candidate": [observation(row) for row in candidate],
                "change": {
                    "id": name,
                    "description": "Replace per-booking ticket-sales aggregation",
                },
                "comparability": {
                    "reference": "observations.json",
                    "statement": (
                        "Same immutable SQLite rows, connection and local process; "
                        "three executions per version"
                    ),
                },
            },
            "policy": {"metric": metric, "minimum_samples": 3, "max_regression_percent": 5},
        },
        "assurance": {
            "required_checks": ["ticket_sales_total"],
            "windows": {
                "baseline_start": baseline[0]["started"],
                "baseline_end": change_at,
                "change_at": change_at,
                "candidate_start": candidate[0]["started"],
                "candidate_end": timestamp(),
            },
            "started_at": {row["id"]: row["started"] for row in baseline + candidate},
            "completed_at": {row["id"]: row["completed"] for row in baseline + candidate},
            "reliability": {"complete": True, "max_failure_percent": 0, "max_increase_points": 0},
            "evidence": []
            if missing
            else [
                {
                    "name": "ticket_sales_total",
                    "kind": "assertion",
                    "expected": True,
                    "observed": all(row["total_cents"] == expected for row in candidate),
                    "reference": "observations.json: independent Python sum of line items",
                    "experiment_id": experiment_id,
                    "execution_ids": [row["id"] for row in candidate],
                }
            ],
        },
    }


def run_demo(output: Path, orders: int = 1000) -> dict[str, Any]:
    if not 100 <= orders <= 2000:
        raise ValueError("Use 100 to 2000 bookings for the bounded demo")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    # Independent Python oracle; no conclusion is inferred from SQL job success.
    items = [
        (booking, tier + 1, (4500, 7500, 12000)[tier])
        for booking in range(1, orders + 1)
        for tier in range(3)
    ]
    expected = sum(quantity * price for _, quantity, price in items)
    connection = sqlite3.connect(":memory:")
    try:
        connection.execute("CREATE TABLE bookings(id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE tickets(booking_id INTEGER, quantity INTEGER, ticket_price_cents INTEGER)"
        )
        connection.executemany(
            "INSERT INTO bookings VALUES (?)", [(i,) for i in range(1, orders + 1)]
        )
        connection.executemany("INSERT INTO tickets VALUES (?, ?, ?)", items)
        baseline = observe(connection, BASELINE, "baseline")
        if any(row["total_cents"] != expected for row in baseline):
            raise ValueError("Demo baseline disagrees with the independent oracle")
        change_at = timestamp()
        candidates = {name: observe(connection, sql, name) for name, sql in CANDIDATES.items()}
    finally:
        connection.close()
    write(
        output / "observations.json",
        {
            "synthetic": True,
            "bookings": orders,
            "line_items": len(items),
            "expected_total_cents": expected,
            "baseline_sql": BASELINE,
            "candidate_sql": CANDIDATES,
            "baseline": baseline,
            "candidates": candidates,
            "limitations": (
                "Local measured runtime; not a cloud benchmark, statistical proof "
                "or spending evidence."
            ),
        },
    )
    experiments, results = [], []
    for name in ("equivalent", "incorrect", "missing-evidence"):
        rows = candidates["equivalent" if name == "missing-evidence" else name]
        supplied = document(
            name,
            baseline,
            rows,
            expected,
            change_at,
            f"generated-{orders}-ticket-bookings",
            missing=name == "missing-evidence",
        )
        report = verify(supplied)
        write(output / f"{name}-input.json", supplied)
        write(output / f"{name}-report.json", report)
        checks = {check["name"]: check["status"] for check in report["checks"]}
        metric = report["performance"]["results"][0]
        results.append(
            {
                "scenario": name,
                "status": report["overall_status"],
                "checks": checks,
                "expected_total_cents": expected,
                "observed_total_cents": rows[0]["total_cents"],
                "baseline_mean_ms": metric["baseline_mean"],
                "candidate_mean_ms": metric["candidate_mean"],
                "regression_percent": metric["regression_percent"],
            }
        )
        experiments.append(
            {
                "id": name,
                "title": {
                    "equivalent": "Equivalent rewrite: ticket quantities preserved",
                    "incorrect": "Incorrect rewrite: ticket quantities ignored",
                    "missing-evidence": "Do not approve without correctness evidence",
                }[name],
                "kind": "verify",
                "input": f"{name}-input.json",
                "recorded_at": timestamp(),
                "synthetic": True,
            }
        )
    write(
        output / "catalog.json",
        {
            "workloads": [
                {
                    "id": "ticket-sales",
                    "name": "Event ticket sales: a measured local example",
                    "description": (
                        f"Measured SQL over {orders:,} generated bookings "
                        f"and {len(items):,} ticket lines. "
                        f"Expected ticket sales: {expected:,} cents. "
                        "The incorrect rewrite returns "
                        f"{candidates['incorrect'][0]['total_cents']:,} "
                        "cents because it ignores quantities. No cloud savings claim."
                    ),
                    "experiments": experiments,
                }
            ]
        },
    )
    summary = {
        "synthetic": True,
        "results": results,
        "financial_conclusion": "UNKNOWN: no cloud pricing or billing evidence supplied",
    }
    write(output / "summary.json", summary)
    return summary


def demo_command(output: Path, orders: int) -> int:
    try:
        summary = run_demo(output, orders)
    except ValueError, OSError, sqlite3.Error:
        print(
            "Demo failed. Choose a new writable output directory and 100 to 2000 bookings.",
            file=sys.stderr,
        )
        return 2
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0
