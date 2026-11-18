# Approve an event ticket-sales query change with evidence

An event team wants a faster sales dashboard. An engineer rewrites its query. Both versions execute successfully, but one rewrite forgets that a booking line can contain several tickets. The dashboard would understate sales if that change were accepted.

DataVouch helps the engineer and reviewer decide whether the proposed change meets the agreed checks. It provides a repeatable decision and its evidence; it does not approve a deployment on someone's behalf.

## The business rule

This generated example has 1,000 confirmed bookings. Each contains:

| Ticket tier | Quantity per booking | Price per ticket | Total per booking |
| --- | ---: | ---: | ---: |
| Standard | 1 | €45 | €45 |
| Premium | 2 | €75 | €150 |
| VIP | 3 | €120 | €360 |
| Total | 6 | | €555 |

The expected ticket-sales total is **€555,000**, stored as **55,500,000 integer cents**. This is synthetic face-value sales before cancellations, refunds, fees and taxes, not a settlement or accounting-revenue model. A real client must define those rules, currency and comparison conditions explicitly.

The baseline aggregates sales separately for each booking. The equivalent rewrite aggregates ticket lines once:

```sql
SELECT SUM(quantity * ticket_price_cents) FROM tickets
```

The deliberately incorrect rewrite drops quantity:

```sql
SELECT SUM(ticket_price_cents) FROM tickets
```

It returns **€240,000**, understating the generated ticket sales by **€315,000**. This is an example calculation, not a claim of money saved for a client.

## What to look for in the UI

Open **Example walkthrough** in the application. It explains the story and links any loaded ticket-sales reports or permitted saved ticket-sales runs. If none are loaded, it says so rather than displaying invented results.

Open each actual report and read **Review recommendation**:

- **Equivalent rewrite:** the independent ticket-sales check should pass. Approve only if the measured performance, comparison windows and reliability also meet policy.
- **Incorrect rewrite:** the ticket-sales check should fail. Successful execution or improved runtime cannot override the incorrect total.
- **Missing evidence:** the example deliberately omits the independent correctness check. Correctness remains UNKNOWN. If another check fails, the overall decision remains FAIL.

Reports show **Ready for reviewer approval**, **Do not approve this change**, or **Hold approval: evidence is incomplete** according to their computed result. These are recommendations for configured checks, not release actions or guarantees.

## Try it locally without Google Cloud

Follow [local setup](getting-started.md), then use a new output directory:

```sh
.venv/bin/python -m datavouch demo --output-dir .local_context/ticket-sales-demo
.venv/bin/python -m datavouch serve .local_context/ticket-sales-demo/catalog.json --port 8767
```

Choose a password when prompted, open `http://127.0.0.1:8767`, sign in as `datavouch`, and select **Example walkthrough**. This executes real SQLite queries on generated data and evaluates real measurements. It does not contact Google Cloud or benchmark BigQuery. See [local demo details](local-demo.md) for replay and Compose instructions.

## Run the same business case in your approved BigQuery project

From a source checkout installed with the `bigquery` and `web` extras, configure [backend ADC and permissions](connections.md). On a VM, use its attached service account. Supply your own approved project and exact BigQuery location:

```sh
export DATAVOUCH_TEST_PROJECT='your-approved-project-id'
export DATAVOUCH_TEST_LOCATION='your-approved-bigquery-location'
.venv/bin/python examples/bigquery/ticket_sales.py \
  --project "$DATAVOUCH_TEST_PROJECT" \
  --location "$DATAVOUCH_TEST_LOCATION" \
  --run-id ticket-review-1 \
  --output-dir .local_context/ticket-sales-bigquery-1 \
  --live
.venv/bin/python -m datavouch serve .local_context/ticket-sales-bigquery-1/catalog.json --port 8767
```

Replace both placeholder values before running. The explicit `--live` flag authorizes **nine synthetic workload queries and six metadata collection queries** in that project. Queries generate rows in SQL; no datasets or persistent tables are created. Each workload query is capped at 10,000,000 billed bytes and 60 seconds; each collection query at 200,000,000 bytes and 60 seconds. These are per-query limits, not spending estimates. BigQuery execution and any VM/disk usage can incur charges.

The example uses the production `run-bigquery` collection and verification code. An independent Python calculation checks returned ticket totals. It records SQL, job IDs, observed totals, generated plans, reports and the UI catalog. `summary.json` contains actual results. The three-sample, five-percent runtime policy is set before execution; timing may vary, so the equivalent candidate is not guaranteed to pass. This is not a statistically conclusive benchmark or a savings claim.

The output directory must be new. Repeating a completed command with the same directory stops before cloud calls. Workload job IDs are deterministic for the run ID; a matching existing job is reused, and mismatched SQL or cache configuration is rejected. If execution fails partway, inspect the saved output and cloud jobs first. A deliberate rerun in a new output directory can reuse matching workload jobs but performs new collection queries. Completed job history and incurred charges are not erased by deleting local output.

The catalog viewer is intended for a controlled walkthrough. Existing shared OIDC gateway deployments deliberately disable startup sample catalogs. In a shared workspace, create authorized runs under the `ticket-sales` workload through the normal experiment workflow; the Example walkthrough page lists only runs in the user's permitted connections.

## What the client gains

The event-data engineer has an acceptance policy instead of relying on query success. The reviewer can see why a change should be accepted, rejected or postponed. A finance stakeholder can inspect whether the agreed ticket-sales assertion was supplied and passed. The saved report makes that reasoning reproducible.

Before applying this to real ticketing data, agree cancellation/refund/fee/tax rules, use comparable snapshots and independent checks, validate the client's identity/network controls, and complete security and onboarding reviews. The example does not establish real client adoption, regulatory compliance or award eligibility.
