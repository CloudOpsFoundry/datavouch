# Review a query rewrite with a synthetic aggregation example

An engineer wants to simplify an aggregation query. Both versions execute successfully, but one rewrite drops the weights from the calculation. DataVouch helps the engineer and reviewer assess whether the change satisfies the agreed correctness, performance and reliability checks.

## The calculation

This generated example contains 1,000 groups, each with three samples:

| Sample | Weight | Value | Weighted value |
| --- | ---: | ---: | ---: |
| A | 1 | 45 | 45 |
| B | 2 | 75 | 150 |
| C | 3 | 120 | 360 |
| Total per group | | | 555 |

The expected weighted sum is **555,000 units**. All values are synthetic integers; there is no currency, client data or industry-specific rule.

The baseline calculates each group's result separately. The equivalent rewrite aggregates all sample rows once:

```sql
SELECT SUM(weight * sample_value) FROM samples
```

The deliberately incorrect rewrite omits weights:

```sql
SELECT SUM(sample_value) FROM samples
```

It returns **240,000**, which is **315,000** below the expected result. Successful execution alone does not establish correctness.

## What to look for in the UI

Open **Example walkthrough** in the application. It explains the story and links any loaded weighted-aggregation reports or permitted saved weighted-aggregation runs. If none are loaded, it says so rather than displaying invented results.

Open each actual report and read **Review recommendation**:

- **Equivalent rewrite:** the independent weighted-total check should pass. Approve only if the measured performance, comparison windows and reliability also meet policy.
- **Incorrect rewrite:** the weighted-total check should fail. Successful execution or improved runtime cannot override the incorrect total.
- **Missing evidence:** the example deliberately omits the independent correctness check. Correctness remains UNKNOWN. If another check fails, the overall decision remains FAIL.

Reports show **Ready for reviewer approval**, **Do not approve this change**, or **Hold approval: evidence is incomplete** according to their computed result. These are recommendations for configured checks, not release actions or guarantees.

## Try it locally without Google Cloud

Follow [local setup](getting-started.md), then use a new output directory:

```sh
.venv/bin/python -m datavouch demo --output-dir .local_context/weighted-aggregation-demo
.venv/bin/python -m datavouch serve .local_context/weighted-aggregation-demo/catalog.json --port 8767
```

Choose a password when prompted, open `http://127.0.0.1:8767`, sign in as `datavouch`, and select **Example walkthrough**. This executes real SQLite queries on generated data and evaluates real measurements. It does not contact Google Cloud or benchmark BigQuery. See [local demo details](local-demo.md) for replay and Compose instructions.

## Run the same calculation in your approved BigQuery project

From a source checkout installed with the `bigquery` and `web` extras, configure [backend ADC and permissions](connections.md). On a VM, use its attached service account. Supply your own approved project and exact BigQuery location:

```sh
export DATAVOUCH_TEST_PROJECT='your-approved-project-id'
export DATAVOUCH_TEST_LOCATION='your-approved-bigquery-location'
.venv/bin/python examples/bigquery/aggregation.py \
  --project "$DATAVOUCH_TEST_PROJECT" \
  --location "$DATAVOUCH_TEST_LOCATION" \
  --run-id aggregation-review-1 \
  --output-dir .local_context/weighted-aggregation-bigquery-1 \
  --live
.venv/bin/python -m datavouch serve .local_context/weighted-aggregation-bigquery-1/catalog.json --port 8767
```

Replace both placeholder values before running. The explicit `--live` flag authorizes **nine synthetic workload queries and six metadata collection queries** in that project. Queries generate rows in SQL; no datasets or persistent tables are created. Each workload query is capped at 10,000,000 billed bytes and 60 seconds; each collection query at 200,000,000 bytes and 60 seconds. These are per-query limits, not spending estimates. BigQuery execution and any VM/disk usage can incur charges.

The example uses the production `run-bigquery` collection and verification code. An independent Python calculation checks returned weighted totals. It records SQL, job IDs, observed totals, generated plans, reports and the UI catalog. `summary.json` contains actual results. The three-sample, five-percent runtime policy is set before execution; timing may vary, so the equivalent candidate is not guaranteed to pass. This is not a statistically conclusive benchmark or a savings claim.

The output directory must be new. Repeating a completed command with the same directory stops before cloud calls. Workload job IDs are deterministic for the run ID; a matching existing job is reused, and mismatched SQL or cache configuration is rejected. If execution fails partway, inspect the saved output and cloud jobs first. A deliberate rerun in a new output directory can reuse matching workload jobs but performs new collection queries. Completed job history and incurred charges are not erased by deleting local output.

The catalog viewer is intended for a controlled walkthrough. Existing shared OIDC gateway deployments deliberately disable startup sample catalogs. In a shared workspace, create authorized runs under the `weighted-aggregation` workload through the normal experiment workflow; the Example walkthrough page lists only runs in the user's permitted connections.

## Apply it to your workload

The engineer gets an explicit acceptance policy instead of relying on query success. The reviewer can inspect the measurements, supplied correctness assertion and reasons for accepting, rejecting or postponing the change. Saved inputs make the decision reproducible.

Define the expected calculation and how to handle missing values, duplicates and input changes. Use comparable snapshots and independent checks, validate the client identity/network controls, and complete security and onboarding reviews. This synthetic example does not establish real client adoption or production readiness.
