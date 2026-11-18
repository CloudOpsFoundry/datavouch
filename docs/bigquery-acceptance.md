# Manual BigQuery acceptance through the UI

Select an explicitly approved test project and BigQuery location before starting. No project or location is selected by this guide. This walkthrough creates no tables and changes no customer data. It runs small synthetic queries and bounded metadata collection, which can incur query charges. Keep the product's project configuration generic; keep private deployment values outside the repository.

## Prepare

1. Start the local UI using [UI execution](ui-execution.md). Configure a connection for your approved project and location. Choose a metadata byte budget (for example `200000000`) and timeout (for example `60` seconds) within your deployment policy. Use matching ADC quota project.
2. In BigQuery Studio, select that project. Set processing location to your approved location and turn off cached results for the test queries. Set a query byte limit appropriate for these table-free queries.
3. Record UTC times and the job ID from each completed query's job details. Use a baseline window starting before the first baseline job starts and ending after the last baseline job finishes. The candidate window starts after the declared change time and ends after its last job finishes.

## Run baseline and candidate manually

Run the baseline three times and record all three IDs and results:

```sql
SELECT SUM(number) AS business_total
FROM UNNEST(GENERATE_ARRAY(1, 1000)) AS number;
```

Each baseline result must be `500500`. Record the UTC change time after these jobs finish. Run the equivalent candidate three times:

```sql
SELECT DIV(1000 * 1001, 2) AS business_total;
```

Independently verify all three candidate results equal `500500`. Save a private evidence note containing the six job IDs, expected and observed totals, the input contract, UTC windows and reviewer identity. Do not publish that note or paste credentials into DataVouch.

## Fill the experiment form

| Field | Value |
| --- | --- |
| Connection | Your approved project/location connection |
| Experiment ID | A unique name such as `manual-equivalent-001` |
| Workload | `synthetic-business-total` |
| Environment | Your test-environment identifier |
| Input snapshot | `integer-sequence-1-through-1000` |
| Description | Equivalent aggregate rewritten as arithmetic |
| Change time | Recorded UTC time between the two cohorts |
| Baseline/candidate dates | Recorded UTC completion windows using the calendar controls |
| Baseline/candidate job IDs | Three IDs per cohort, one per line |
| Comparison reference | Private evidence-note identifier |
| Comparison statement | Same integer sequence and expected total; uncached runs in the same project/location |
| Required correctness check | `business_total` |
| Correctness outcome | Passed, only after verifying every selected candidate result |
| Evidence reference | Private evidence-note identifier covering all candidate IDs |
| Metric | Runtime |
| Minimum samples | `3` |
| Maximum regression | Your chosen tolerance, for example `5` percent |
| Completeness | Confirm only if every selected attempted execution is represented |
| Synthetic | Select: this is synthetic test data |

Confirm the evidence and run. Correctness should PASS and reliability should PASS. Runtime is measured, not guaranteed to improve: very short queries fluctuate, so overall PASS is not guaranteed. A runtime FAIL can be a valid result. Inspect the collected measurements and reasons rather than changing thresholds to force a pass.

## Demonstrate failures and missing evidence

Run an intentionally incorrect candidate three times after a new recorded change time:

```sql
SELECT DIV(1000 * 1001, 2) - 1 AS business_total;
```

Create a new experiment using those three candidate IDs and a new candidate window. Independently verify the observed `500499` differs from `500500`; select **Failed** for `business_total` and attach the evidence reference. The correctness check and overall result must FAIL even if runtime improves.

Create another uniquely named experiment using the equivalent candidate but leave correctness evidence unavailable. Correctness must be UNKNOWN. Overall is UNKNOWN only when no other required check fails; a performance or reliability failure still produces FAIL. Repeating a completed plan reuses its saved result; changing the evidence or experiment ID creates a different plan.

## Financial and replay checks

Open a saved run's financial section. Supply a clearly labeled synthetic price and validity interval covering both cohorts, or an approved actual contract rate. Inspect the estimate and its source measurements. Table-free jobs may have zero billed bytes; do not infer realized savings. Missing capacity billed slot-hours must remain unavailable, not be inferred from consumed slots.

Download the summary. An administrator can opt into raw reports for private replay. On the server, replay the saved `result/input.json` using `datavouch verify`; its report must match the saved verification report. Inspect the audit export and delete a disposable experiment to check retention behavior. Deletion does not remove BigQuery jobs.

Record the exact source revision, Python version, experiment IDs, configured policy, check outcomes, elapsed collection time and any unexpected behavior. These tests validate this bounded synthetic scenario; production workloads and each client deployment need their own acceptance.
