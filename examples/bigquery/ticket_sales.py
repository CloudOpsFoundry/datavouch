"""Opt-in, table-free BigQuery ticket-sales walkthrough using the real verification pipeline."""

import argparse
import json
import re
from contextlib import redirect_stdout
from datetime import UTC, datetime, timedelta
from io import StringIO
from pathlib import Path

from datavouch.adapters.bigquery.experiments import prepare, run_command
from datavouch.web.connections import validate_scope

TITLES = {
    "equivalent": "Equivalent rewrite: ticket quantities preserved",
    "incorrect": "Incorrect rewrite: ticket quantities ignored",
    "missing-evidence": "Hold approval: ticket-sales evidence omitted",
}


def queries():
    source = """WITH bookings AS (
  SELECT booking_id FROM UNNEST(GENERATE_ARRAY(1, 1000)) AS booking_id
), tickets AS (
  SELECT booking_id, tier AS quantity,
    CASE tier WHEN 1 THEN 4500 WHEN 2 THEN 7500 ELSE 12000 END AS ticket_price_cents
  FROM bookings CROSS JOIN UNNEST([1, 2, 3]) AS tier
)
"""
    return {
        "baseline": source + "SELECT SUM((SELECT SUM(quantity * ticket_price_cents) FROM tickets "
        "WHERE tickets.booking_id = b.booking_id)) AS ticket_sales_cents FROM bookings AS b",
        "equivalent": source
        + "SELECT SUM(quantity * ticket_price_cents) AS ticket_sales_cents FROM tickets",
        "incorrect": source + "SELECT SUM(ticket_price_cents) AS ticket_sales_cents FROM tickets",
    }


def plan(project, location, run_id, scenario, cohorts, expected):
    baseline = cohorts["baseline"]
    candidate = cohorts["equivalent" if scenario == "missing-evidence" else scenario]
    baseline_end = max(datetime.fromisoformat(j["ended"]) for j in baseline) + timedelta(
        milliseconds=1
    )
    candidate_start = min(datetime.fromisoformat(j["created"]) for j in candidate)
    if baseline_end >= candidate_start:
        raise ValueError("Execution timestamps do not form disjoint comparison windows")
    identity = f"tickets-{run_id}-{scenario}"
    document = {
        "schema_version": "bigquery-experiment-0.1",
        "id": identity,
        "change": {
            "id": identity + "-change",
            "description": TITLES[scenario],
            "at": (baseline_end + (candidate_start - baseline_end) / 2).isoformat(),
        },
        "comparability": {
            "reference": "observations.json",
            "statement": (
                "Same 1000 generated confirmed bookings and ticket tiers; integer cents; "
                "no cancellations, refunds, fees or taxes; three uncached jobs per version."
            ),
        },
        "policy": {
            "metric": {"name": "runtime", "unit": "ms", "direction": "lower"},
            "minimum_samples": 3,
            "max_regression_percent": 5,
        },
        "assurance": {
            "required_checks": ["ticket_sales_total"],
            "evidence": [],
            "reliability": {"complete": True, "max_failure_percent": 0, "max_increase_points": 0},
        },
        "synthetic": True,
    }
    for side, jobs in (("baseline", baseline), ("candidate", candidate)):
        document[side] = {
            "project": project,
            "location": location,
            "start": min(datetime.fromisoformat(j["created"]) for j in jobs).isoformat(),
            "end": (
                max(datetime.fromisoformat(j["ended"]) for j in jobs) + timedelta(milliseconds=1)
            ).isoformat(),
            "job_ids": [j["id"] for j in jobs],
            "workload": {
                "id": "ticket-sales",
                "environment": "synthetic-bigquery-example",
                "input_snapshot": "1000-confirmed-bookings-three-ticket-tiers-v1",
            },
            "maximum_bytes_billed": 200000000,
            "timeout_seconds": 60,
        }
    if scenario != "missing-evidence":
        document["assurance"]["evidence"] = [
            {
                "name": "ticket_sales_total",
                "kind": "assertion",
                "expected": True,
                "observed": all(j["ticket_sales_cents"] == expected for j in candidate),
                "reference": (
                    "observations.json: independent Python sum of "
                    "ticket quantities multiplied by prices"
                ),
                "experiment_id": identity,
                "execution_ids": [f"{project}/{location}/{j['id']}" for j in candidate],
            }
        ]
    prepare(document)
    return document


def write(path, value):
    with path.open("x", encoding="utf-8") as target:
        json.dump(value, target, indent=2, sort_keys=True, allow_nan=False)
        target.write("\n")
    path.chmod(0o600)


def execute(project, location, run_id, output):
    # Validate before importing the SDK or making any cloud requests.
    validate_scope(project, location, 200000000, 60)
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,39}", run_id):
        raise ValueError("Use a run ID of 1 to 40 lowercase letters, digits or hyphens")
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    from google.api_core.exceptions import NotFound
    from google.cloud import bigquery

    expected = sum(
        quantity * price
        for _ in range(1000)
        for quantity, price in ((1, 4500), (2, 7500), (3, 12000))
    )
    with bigquery.Client(project=project, location=location) as client:
        cohorts = {}
        for scenario, sql in queries().items():
            jobs = []
            for index in range(3):
                identity = f"datavouch_tickets_v1_{run_id}_{scenario}_{index}"
                try:
                    job = client.get_job(
                        identity, project=project, location=location, retry=None, timeout=30
                    )
                    if job.query != sql or job.use_query_cache is not False:
                        raise ValueError("Existing job differs; use a new run ID")
                except NotFound:
                    job = client.query(
                        sql,
                        job_id=identity,
                        location=location,
                        job_config=bigquery.QueryJobConfig(
                            use_query_cache=False,
                            maximum_bytes_billed=10000000,
                            job_timeout_ms=60000,
                            labels={"application": "datavouch", "purpose": "ticket-sales-demo"},
                        ),
                        retry=None,
                        job_retry=None,
                        timeout=30,
                    )
                rows = list(job.result(timeout=90, retry=None, job_retry=None))
                if job.cache_hit:
                    raise ValueError("Cached jobs cannot establish the example's measurements")
                total = int(rows[0]["ticket_sales_cents"])
                if scenario == "baseline" and total != expected:
                    raise ValueError("Baseline disagrees with the independent sales calculation")
                jobs.append(
                    {
                        "id": identity,
                        "created": job.created.isoformat(),
                        "ended": job.ended.isoformat(),
                        "ticket_sales_cents": total,
                    }
                )
            cohorts[scenario] = jobs
    write(
        output / "observations.json",
        {
            "synthetic": True,
            "project": project,
            "location": location,
            "expected_ticket_sales_cents": expected,
            "sql": queries(),
            "cohorts": cohorts,
        },
    )
    experiments = []
    summary = []
    for scenario, title in TITLES.items():
        supplied = plan(project, location, run_id, scenario, cohorts, expected)
        target = output / (scenario + "-plan.json")
        write(target, supplied)
        result = output / scenario
        with redirect_stdout(StringIO()):
            code = run_command(target, result, None, True)
        if code not in (0, 1, 3):
            raise ValueError(
                "Collection failed; inspect the output and cloud job status before retrying"
            )
        report = json.loads((result / "report.json").read_text())
        summary.append(
            {
                "scenario": scenario,
                "status": report["overall_status"],
                "checks": {c["name"]: c["status"] for c in report["checks"]},
            }
        )
        experiments.append(
            {
                "id": scenario,
                "title": title,
                "kind": "verify",
                "input": scenario + "/input.json",
                "recorded_at": datetime.now(UTC).isoformat(),
                "synthetic": True,
            }
        )
    write(
        output / "catalog.json",
        {
            "workloads": [
                {
                    "id": "ticket-sales",
                    "name": "Event ticket sales: measured BigQuery example",
                    "description": (
                        "Real BigQuery executions over 1,000 generated confirmed bookings. "
                        "Independent expected ticket sales: 55,500,000 cents (€555,000). "
                        "Synthetic data, not a client benchmark or savings claim."
                    ),
                    "experiments": experiments,
                }
            ]
        },
    )
    write(output / "summary.json", {"results": summary, "expected_ticket_sales_cents": expected})
    print(json.dumps(summary, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", required=True)
    parser.add_argument("--location", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--live",
        action="store_true",
        required=True,
        help="Authorize nine synthetic queries and six bounded metadata collection queries",
    )
    args = parser.parse_args()
    execute(args.project, args.location, args.run_id, args.output_dir)


if __name__ == "__main__":
    main()
