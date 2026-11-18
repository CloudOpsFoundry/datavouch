# BigQuery adapter

The experimental adapter reads minimal job metadata from one project's regional `INFORMATION_SCHEMA.JOBS_BY_PROJECT` view. Offline fixtures and SDK transport contracts are tested. On 2026-11-17, a live smoke test in the eu location collected three synthetic SELECT jobs. Runtime, slot usage and byte measurements matched the jobs API. This validates basic connectivity, not general production readiness.

## Offline use

```sh
datavouch collect-bigquery examples/bigquery/collection_config.json \
  --fixture examples/bigquery/jobs.json > collection.json
```

This command does not import Google libraries or load credentials. The fixture rows are synthetic. The configuration specifies a project ID, lowercase location, start and end timestamps with time zones, 1 to 100 unique job IDs, and an explicitly registered workload. The workload records the logical ID, environment and input snapshot. These are caller assertions, not facts inferred from job metadata.

Creation windows are half open (`start <= creation_time < end`) and at most 31 days. Live collection also requires the window to fall within the last 180 days. Offline fixtures can retain older historical dates. JSON files are limited to 5 MB. The query uses parameters for timestamps, IDs and limits. Validated project and location identifiers determine the view.

Collection requires standalone SELECT jobs. Scripts, child jobs, nonquery jobs, pending jobs, failures, cached executions and incomplete critical metadata are retained as excluded evidence. They are not silently converted to successful observations. Missing requested job IDs and multiple fingerprint groups make the whole collection ineligible. Duplicate or out of scope records fail collection. Missing optional resource measurements remain absent, not zero.

Runtime is `end_time - start_time` in milliseconds and excludes queue time. Other metrics are slot milliseconds, processed bytes and billed bytes when present. Bytes processed are not an input row count. Billed bytes are not a monetary savings measurement. SQL text, email, query results and full error messages are never selected or serialized. Error classifications are retained without their messages.

A normalized query hash groups related executions but ignores parameters, literals and other query details. It cannot prove output equivalence or matching inputs. Validate workload conditions independently before using collection observations in a comparison. Multiple hashes within one collection must be separated and investigated. A rewrite can legitimately have a different hash in its separate candidate collection.

Collection JSON includes source, scope, job evidence, missing IDs, fingerprint groups, observations and an `eligible` flag. Exit 0 means collection eligibility, 3 means incomplete or unsupported evidence, and 2 means an input or transport error. Eligibility is not a PASS verdict for the workload. Only use `observations` from an eligible collection to populate the comparison input's baseline or candidate arrays, then provide independent comparability evidence. Use the separate [verify command](verification.md) to apply execution windows and independently supplied correctness evidence. Automatic experiment assembly and assertion execution are not implemented.

## Authorized real environment validation

1. Select a GCP test project and the region containing existing synthetic SELECT jobs. Do not use production or organizational workloads without explicit authorization.
2. Ask the project administrator to provide only the required permissions: `bigquery.jobs.create` for the metadata query and `bigquery.jobs.listAll` for project job metadata. Predefined `roles/bigquery.jobUser` and `roles/bigquery.resourceViewer` provide these permissions. Metadata access can expose other jobs in the project, so choose a dedicated test project. No table write role is required.
3. Install `python -m pip install ".[bigquery]"` in a virtual environment. Configure Application Default Credentials using an approved local login or service identity. For an approved developer login, `gcloud auth application-default login` is the standard interactive command. Never place credentials in a fixture or repository.
4. Obtain three completed, uncached, standalone SELECT job IDs from an existing synthetic test workload. Keep data, parameters and environment stable. If new executions are needed, run only authorized read-only queries with the cache disabled. DataVouch does not execute the workload itself.
5. Copy the example collection configuration to a private file outside the checkout. Set the actual project, lowercase location, explicit job IDs, a short UTC creation window and meaningful workload identity. Derive the window from provider job creation timestamps. If local and server clocks differ, synchronize the host clock and wait until the window ends before collection. Set `maximum_bytes_billed` to an approved budget, at most 1000000000 bytes. The default is 100000000 bytes. Set a timeout between 1 and 300 seconds, default 60.
6. Explicitly request collection:

   ```sh
   datavouch collect-bigquery /private/path/collection_config.json --live > /private/path/collection.json
   ```

7. Compare each returned duration, slot time and byte count against the same job's BigQuery metadata. Confirm all selected IDs are present and the scope matches. Check the output for SQL text, email and error message exclusions. Retain sanitized validation evidence privately. A matching fingerprint alone does not complete validation.
8. Test a missing job ID and a denied metadata permission in the test environment. Expect exit 3 with missing IDs for the former and exit 2 with a sanitized access error for the latter. Do not broaden permissions automatically to make a test pass.

The metadata SELECT creates a query job and may incur charges or consume capacity. The row limit does not cap bytes scanned. The partition filter and `maximum_bytes_billed` constrain the request. SDK retries and job retries are disabled. The server job timeout is a best effort bound, and a local timeout does not prove the query stopped. Inspect query status before retrying. No workload data or infrastructure is modified by the collector.

## Sources and overlap

Google's [JOBS metadata reference](https://docs.cloud.google.com/bigquery/docs/information-schema-jobs) defines retention, permissions, regional scope, query hashes and metrics. [INFORMATION_SCHEMA pricing](https://docs.cloud.google.com/bigquery/docs/information-schema-intro) describes query charges and capacity usage. [Application Default Credentials setup](https://docs.cloud.google.com/docs/authentication/provide-credentials-adc) describes authentication options.

[BigQuery performance insights](https://docs.cloud.google.com/bigquery/docs/query-insights) already provides query execution diagnostics. DataVouch reuses supported metadata to produce reproducible experiment evidence. It does not duplicate the query execution graph or claim unique diagnostic capabilities. The [Python SDK reference](https://docs.cloud.google.com/python/docs/reference/bigquery/latest/google.cloud.bigquery.client.Client) documents query controls.
