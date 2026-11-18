# Configured verification

Run `datavouch verify examples/verification/passing.json`. The complete example is synthetic. It compares a 100 ms baseline mean with an 80 ms candidate mean and supplies independently specified correctness evidence. No data or credentials are fetched by this command.

The input has `comparison` and `assurance` objects. `comparison` uses the existing [comparison schema](configuration.md). Its metric policy still controls units, direction, minimum samples, regression threshold and optional per-input normalization. The source document is retained in the report, so provide references and compact evidence instead of sensitive records.

## Execution selection

`assurance.windows` defines `baseline_start`, `baseline_end`, `change_at`, `candidate_start` and `candidate_end`. All are ISO timestamps with explicit time zones. Require `baseline_start < baseline_end <= change_at <= candidate_start < candidate_end`. `started_at` and `completed_at` map every supplied execution ID to its timestamps. Missing mappings produce UNKNOWN. Invalid timestamps, overlapping execution IDs or completion before start are input errors.

All executions fully contained in their respective half-open windows are selected. Start may equal the lower bound, but completion must be earlier than the upper bound. An execution spanning the change or a window boundary is excluded, with its ID retained in the report. No baseline subset is chosen based on its performance. Minimum sample counts apply after selection. DataVouch cannot establish whether the supplied history is complete or timestamps are truthful.

## Required correctness evidence

`required_checks` is a nonempty list of unique check names. `evidence` supplies records for those names. Missing evidence is UNKNOWN. Unrequested or duplicate records are rejected.

Every evidence record identifies its `name`, `kind`, `experiment_id`, exact selected candidate `execution_ids`, an independent `reference`, and `expected` and `observed` values. Evidence must cover the entire selected candidate cohort. The producer must define its checks and execute them separately, for example with dbt, Great Expectations or an independent validation script. DataVouch does not execute expressions, follow references or authenticate attestations.

Supported checks:

- `assertion`: compare boolean expected and observed outcomes from an independently executed business assertion.
- `schema`: compare nonempty ordered lists of field descriptors. Define descriptors consistently, including names, types, nullability and nested paths where relevant. This is exact structural comparison, not proof of value equivalence.
- `sha256`: compare lowercase SHA256 digests. `method` must describe the shared canonicalization and whole-output coverage contract, including column ordering, row ordering and duplicate/null handling. Matching sampled hashes do not establish full output equivalence. The producer is responsible for truthful coverage.
- `freshness`: `expected` is maximum age in seconds, `observed` is the data timestamp and `as_of` is the explicit evaluation timestamp. Age at the limit passes. Future data timestamps or an evaluation time before candidate completion produce UNKNOWN. Nothing depends on the current machine clock.
- `row_count`: always UNKNOWN as a correctness check, including equal counts. Counts alone do not prove correctness.

A schema-only PASS means the declared schema check passed. It does not imply equal output values or whole-system correctness. Declare the checks your change actually requires. The input digest binds the policy and supplied evidence for reproducibility, not authentication.

## Reliability

`assurance.reliability.complete` must explicitly attest that all executions in the selected windows, including failures, are included. `max_failure_percent` limits the candidate failure rate. `max_increase_points` limits its increase over baseline in percentage points. Both default to zero and must be between 0 and 100. Rate calculation is `100 * failures / executions`. Threshold equality passes, and comparisons use exact rational arithmetic. Different execution counts are normalized through rates.

Missing completeness, insufficient samples, unmatched workloads or unavailable windows produce UNKNOWN. A known rate violation produces FAIL. The performance engine conservatively refuses cohorts containing failed executions. Failures must not be filtered out just to obtain a performance PASS. BigQuery collection currently excludes failed jobs from usable observations, so its successful observation list alone does not establish a complete reliability cohort. An authorized evidence producer must preserve those failure outcomes before attesting completeness. Automatic collection-to-experiment assembly is not implemented.

## Conclusions and exit codes

Any required FAIL makes the overall result FAIL, even if performance passes or another check is UNKNOWN. Otherwise any UNKNOWN makes the overall result UNKNOWN. PASS requires every declared check, window validation, performance and reliability to pass. Exit codes are 0 PASS, 1 FAIL, 2 invalid input and 3 UNKNOWN.

The report includes all check results, selected observations, excluded IDs, reliability counts and rates, evidence quality counts, the source input and its SHA256 digest. The schema is `verification-0.1`. Identical inputs produce identical output bytes. The separate `compare` command remains metric-only and has unchanged exit semantics.

## Validation scope and next real test

Automated fixtures cover improved runtime with failed assertions, schema and checksum mismatches, stale or future timestamps, missing/wrong-scope evidence, row-count limitations, unequal execution volumes, exact rate boundaries, window selection and all CLI exit codes.

For real validation, use the authorized project and region recorded in your private environment configuration. Execute a small synthetic baseline and candidate with independently known results. Preserve every job outcome and provider start/end timestamps. Compare canonical output digests and schema separately, then assemble verification evidence with exact job IDs and a complete-cohort attestation. Also test a deliberately incorrect synthetic result and confirm that correctness FAIL cannot be overridden by a performance PASS. A small live test is not a performance benchmark or production-readiness assessment.

Existing tools already provide assertion execution and schema validation. See [dbt data tests](https://docs.getdbt.com/docs/build/data-tests) and [Great Expectations schema checks](https://docs.greatexpectations.io/docs/reference/learn/data_quality_use_cases/schema/). DataVouch consumes compact evidence for change verification rather than replacing those tools.

On 2026-11-17, a controlled live sandbox experiment in eu used three baseline executions, three correct arithmetic rewrites and three deliberately incorrect rewrites. The correct candidate passed all configured checks. The incorrect candidate failed its business assertion, checksum and performance check while schema and execution reliability passed. Saved reports reproduced byte for byte on Python 3.12 and 3.15. These were tiny table-free queries, not a performance benchmark. Freshness validation in this release uses deterministic offline fixtures.
