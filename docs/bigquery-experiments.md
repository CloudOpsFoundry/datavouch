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

A missing, failed, cached, incomplete, unsupported or mixed-fingerprint job makes its whole collection unusable for this command. An execution crossing its configured window also withholds the whole cohort. Diagnostics remain in the collection files and `collection-status.json`. The assembled input has an empty cohort instead of silently dropping undesirable runs, which makes performance and reliability UNKNOWN. A known independent correctness failure in the remaining candidate cohort can still produce FAIL.

Different fingerprints between baseline and candidate are allowed for a query rewrite. Matching fingerprints alone do not establish comparability. Missing optional metrics or required assertions remain UNKNOWN. Input volume normalization also remains UNKNOWN because job metadata does not supply input row counts.

Reliability requires explicit `complete: true`, adequate samples and usable collections. This asserts completeness of the selected experiment, not all project jobs. Failed job cohorts currently produce UNKNOWN rather than a computed failure-rate result through this command. The separate verification engine accepts independently prepared complete success/failure cohorts.

The bundled collections use `bigquery-collection-0.2` to include start and completion timestamps. The existing `collect-bigquery` command retains its `bigquery-collection-0.1` output for compatibility.
