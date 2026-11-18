# Local experiment workspace

The optional FastAPI application provides workload history, experiment details, correctness and reliability checks, financial classifications, and JSON downloads. It calculates a bounded snapshot once at startup using the same engines as the CLI. Default viewer requests do not query BigQuery. Explicitly enabled execution and financial forms use the same CLI engines.

For a first-time walkthrough, use [Get DataVouch running locally](getting-started.md). The UI stays in this monorepo; see the [delivery roadmap](product-roadmap.md).

## Start locally

From the source checkout:

```sh
uv sync --locked --all-extras
uv run --no-sync datavouch serve examples/viewer.json
```

Enter a password of 16–256 printable ASCII characters at the terminal prompt. Open http://127.0.0.1:8765 and sign in with username `datavouch` and that password. For noninteractive launches, supply `DATAVOUCH_WEB_PASSWORD` through your environment's secret handling. Do not put real passwords in source files or shell history. Stop with Ctrl+C. Use `--port` to select another unprivileged port.

The bundled catalog is synthetic. Confirm the passing verification, failed correctness example, and UNKNOWN financial estimate. Open each detail page and download its summary. These are demonstrations, not real financial evidence.

## Curate a catalog

Copy the structure of [viewer.json](../examples/viewer.json). Each workload has a unique URL-safe `id`, `name`, `description`, and `experiments` array. Each experiment has an `id`, `title`, timezone-aware `recorded_at`, `kind` (`compare`, `verify`, or `finance`), relative `input` path, and boolean `synthetic`. Inputs use the existing CLI schemas. Dates are curator-supplied, not provenance evidence.

All referenced files must reside inside the catalog directory. Parent traversal and symlinks escaping that directory are rejected. Limits are 50 workloads, 100 experiments, 5 MB per JSON input, 20 MB combined report inputs, and 50 MB rendered reports. Missing or invalid experiment inputs display UNKNOWN and disable full downloads. Invalid catalog structure prevents startup. Restart after updating files.

Choose catalog labels and assertion names suitable for display. The UI omits raw source documents, execution identifiers and evidence references, but curator-supplied labels can still contain sensitive text. The default download is an allowlisted summary. `--allow-raw-reports` explicitly enables complete reports, including their original evidence metadata; these downloads match CLI report bytes exactly.

## Access model and limits

By default the command binds to loopback, requires HTTP Basic authentication, rejects unexpected Host headers and cross-site browser requests, and supplies restrictive browser security headers. Static CSS and the icon contain no report data. Report routes remain read-only. The bounded plan form validates submitted fields and returns a preview or JSON download without saving server-side state or collecting cloud data. It requires authentication and a server-issued form token; cross-site submissions are rejected. A restart creates a new immutable catalog snapshot. Optional execution mode persists submitted runs separately; see [UI execution](ui-execution.md).

Basic authentication is intended for local use. For shared access, follow [OIDC gateway setup](gateway-access.md); for packaged operation, follow [container setup](container.md). HTTP Basic credentials remain cached by the browser; close the browser session when finished. Real client identity and infrastructure acceptance remains required.

For real validation, first prepare sanitized comparison or verification inputs from authorized runs in your approved project and location; keep them in a private catalog directory and set `synthetic` to false only for real evidence. Check CLI results against the UI and compare full report downloads locally. Real billing validation requires separately authorized billing evidence and independent reconciliation.

## Plan a BigQuery experiment

1. Start the local UI and sign in, following the [setup guide](getting-started.md).
2. Configure [deployment connections](connections.md), restart with `--connections`, and select **New experiment** in the navigation. Choose your approved project/location.
3. Describe the workload, input snapshot and change. Explain why the original and changed executions are comparable.
4. Enter separate baseline and candidate job IDs, one per line, and execution windows using the date-and-time pickers. All five fields, including change time, are explicitly UTC. Your browser may display dates in its locale, but the selected time is never interpreted as local time. Minute, second and millisecond precision are supported; exported plans carry the UTC `Z` suffix. The baseline must end before the change; the candidate must start at or after the change. Each window may span at most 31 days.
5. Set the minimum run count, permitted metric regression and reliability thresholds. Name the required correctness checks. Supply independent outcomes/references or advanced evidence JSON; leave unavailable evidence empty.
6. Review the metadata query byte cap and timeout. Choose an approved project/location from the deployment dropdown. See [connection configuration](connections.md). It does not submit queries.
7. Confirm cohort completeness only if all selected executions, including failures, are accounted for. Mark synthetic data explicitly where applicable.
8. Select **Validate plan**. Errors retain your entries. A valid plan is not a PASS result and does not establish that job IDs exist or that correctness checks passed.
9. Select **Validate and download** to save `datavouch-plan.json`. The file contains workload and job identifiers, so keep it private. It uses the same schema and validator as `run-bigquery`.

For authorized collection, follow [BigQuery experiment setup](bigquery-experiments.md) and run the downloaded plan through the CLI. Missing correctness evidence remains UNKNOWN. With explicit [execution setup](ui-execution.md), the browser can submit a validated plan to the backend and retain its result. Without execution enabled, downloading is how you preserve a plan. Unsubmitted drafts are not stored. Restarting the server invalidates outstanding form tokens, so reload the form before submitting again.
