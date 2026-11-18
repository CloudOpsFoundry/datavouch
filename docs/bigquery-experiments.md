# BigQuery experiments

`run-bigquery` connects bounded BigQuery collection to the existing verification engine and local viewer. You select both execution cohorts, identify the change and provide explicit comparability and correctness evidence. DataVouch collects measurements and execution timestamps without requiring manual observation JSON assembly.

## Run the complete offline example

```sh
datavouch run-bigquery examples/bigquery/experiment/plan.json \
  --fixtures examples/bigquery/experiment/baseline-jobs.json \
             examples/bigquery/experiment/candidate-jobs.json \
  --output-dir /tmp/datavouch-example-run
```

Use a new output directory for every experiment. Its parent must already exist. The example has three baseline runs at 1000 ms and three candidate runs at 800 ms, a descriptive 20 percent reduction. The independent assertion and cohort completeness in this example are synthetic fixtures.

Exit codes are 0 for PASS, 1 for FAIL, 2 for invalid input or collection/output errors, and 3 for UNKNOWN. FAIL and UNKNOWN are completed evaluations with saved evidence. On exit 2, discard any partial output directory and inspect the error before retrying. A timed-out metadata query may still be running.

## Inspect and reproduce the result

The command prints the verification report and saves:

| File | Purpose |
| --- | --- |
| `input.json` | Complete input for offline verification and workflow gates |
| `report.json` | Deterministic report, identical to CLI replay and the viewer's raw report |
| `baseline-collection.json`, `candidate-collection.json` | Sanitized collection evidence, missing IDs, exclusions and execution timestamps |
| `collection-status.json` | Whether each complete cohort was used and why it was withheld |
| `catalog.json` | Entry point for the authenticated local viewer |

```sh
datavouch verify /tmp/datavouch-example-run/input.json
datavouch serve /tmp/datavouch-example-run/catalog.json --port 8766
```

The viewer requires the web extra and a password entered at its prompt. See [viewer setup](web.md). Its recorded date is the configured candidate window end, not the time the command ran. Multiple runs can be combined into a curated history using the documented catalog format. Each run is stored separately and existing files are never overwritten.

Files contain workload identifiers and supplied evidence. Keep real experiment directories private. Provider SQL, user email and full provider error messages are not collected. Caller-supplied descriptions and evidence references can still contain sensitive text.

## Configure a real experiment

Start with [the example plan](../examples/bigquery/experiment/plan.json):

- `schema_version` is `bigquery-experiment-0.1`.
- `baseline` and `candidate` use the existing [collection configuration](bigquery.md), including project, location, explicit job IDs and bounded creation windows. Both must register the same workload, environment and input snapshot in the same project and location. IDs must be disjoint.
- `change` supplies an ID, description and timezone-aware `at` timestamp between the two windows.
- `comparability` records an independently reviewed statement and reference. It is not inferred from query fingerprints.
- `policy` selects a metric and thresholds using the [comparison schema](configuration.md).
- `assurance` supplies required check names, optional independent evidence and an optional reliability policy using the [verification schema](verification.md). Execution IDs in correctness evidence use `project/location/job_id`. Start/completion mappings and verification windows are generated from collected metadata and the plan, so these fields cannot be supplied in `assurance`.
- `synthetic` is an explicit description of the workload data. Keep it true for synthetic queries even when they execute in a real cloud project.

A complete plan is validated before any cloud request. Live mode runs two metadata SELECTs, one per cohort. Each has its own byte and time budget. The combined maximum is the sum of those budgets. Live access always requires `--live` and the BigQuery extra.

For the authorized sandbox, use `sandbox-platform-services` and `eu` in both scopes, with matching Application Default Credentials quota project. Replace example IDs and dates with actual job IDs and provider-derived windows. Keep the plan outside the repository:

```sh
GOOGLE_CLOUD_QUOTA_PROJECT=sandbox-platform-services \
  datavouch run-bigquery /private/path/experiment.json --live \
  --output-dir /private/path/new-experiment-run
```

The command reads metadata for existing jobs. It does not run or modify the workload, execute assertion queries, access billing exports, or infer financial savings. Reuse independently established correctness evidence only when it covers the exact selected experiment and candidate executions.

## Conservative cohort handling

A missing, cached, incomplete, unsupported or mixed-fingerprint job makes its whole collection unusable for this command. An execution crossing its configured window also withholds the whole cohort. Diagnostics remain in the collection files and `collection-status.json`. The assembled input has an empty cohort instead of silently dropping undesirable runs, which makes performance and reliability UNKNOWN. A known independent correctness failure in the remaining candidate cohort can still produce FAIL.

Different fingerprints between baseline and candidate are allowed for a query rewrite. Matching fingerprints alone do not establish comparability. Missing optional metrics or required assertions remain UNKNOWN. Input volume normalization also remains UNKNOWN because job metadata does not supply input row counts.

Reliability requires explicit `complete: true`, adequate samples and usable collections. This asserts completeness of the selected experiment, not all project jobs. A completed job whose only collection exclusion is a classified failure is retained as an unsuccessful execution with no performance measurements. The whole selected cohort remains present for failure-rate calculation. Performance remains UNKNOWN whenever either cohort includes a failure. Reliability can produce FAIL when the candidate failure rate or its increase exceeds the declared policy. That known failure makes the overall result FAIL even when performance is UNKNOWN. A failure rate within policy does not turn unavailable performance into PASS.

Failed jobs still require complete timestamps, a noncached standalone SELECT classification and an explicit failure reason. BigQuery documents normalized fingerprints for successful, noncached queries, but does not guarantee one for failures. A failed job may include a fingerprint or omit it. Its identity comes from the explicitly selected job ID and registered workload; no fingerprint is invented. Successful jobs still require fingerprints, and multiple known fingerprints within a cohort still make it unusable. Missing classification or timestamps and all other exclusions remain UNKNOWN. See the [BigQuery JOBS schema](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs).

`collection-status.json` distinguishes `eligible` for successful performance observations from `reliability_eligible` for complete success/failure cohorts. `used` means the cohort was included in verification within its configured window, not that performance is usable. The existing collection files continue to list failed jobs as excluded from performance observations.

To reproduce a failure-rate regression offline, replace the candidate fixture in the command above with `examples/bigquery/experiment/candidate-failed-jobs.json`. One of three candidate executions fails, compared with zero baseline failures. The result exits 1 with reliability FAIL, performance UNKNOWN and a candidate failure rate of approximately 33.33 percent. Saved input replays through `verify`, the policy gate and the viewer.

The bundled collections use `bigquery-collection-0.2` to include start and completion timestamps. The existing `collect-bigquery` command retains its `bigquery-collection-0.1` output for compatibility.

## Real failed-job validation

On 2026-11-18, a bounded synthetic experiment in `sandbox-platform-services`, EU, ran three successful baseline jobs and a candidate cohort with two successes and one deliberate runtime failure. All six jobs were table-free SELECT queries over a generated integer sequence. Six successful metadata queries collected only the selected job IDs. Two earlier metadata attempts were stopped by the 100 MB billing cap; these validation reads then used a 200 MB cap per query. The collector's default budget is unchanged.

Reliability reported zero baseline failures and one candidate failure out of three, approximately 33.33 percent, producing FAIL under a zero-failure policy. Performance and the independently missing correctness assertion remained UNKNOWN. The saved report matched offline CLI and viewer replay exactly. A permissive reliability policy returned reliability PASS but overall UNKNOWN. A deliberately missing selected job returned reliability UNKNOWN.

The real failed job included a fingerprint, so this live evidence validates the known-fingerprint path. Missing failure fingerprints are covered by offline regression tests based on the provider's documented metadata contract. No production workload, performance improvement, or general reliability claim follows from this small synthetic experiment.
