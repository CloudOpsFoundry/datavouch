# Local report viewer

The optional FastAPI application provides workload history, experiment details, correctness and reliability checks, financial classifications, and JSON downloads. It calculates a bounded snapshot once at startup using the same engines as the CLI. Requests do not query BigQuery or recalculate reports.

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

The command binds only to loopback, requires HTTP Basic authentication, rejects unexpected Host headers and cross-site browser requests, and supplies restrictive browser security headers. Static CSS and the icon contain no report data. There are no upload, mutation, cloud collection or browser-side calculation routes. A restart creates a new immutable snapshot.

This is a single-user local viewer. Do not expose it through port forwarding or a public proxy. Multi-user identity, TLS deployment, session revocation, public hosting and containers are outside this phase. HTTP Basic credentials remain cached by the browser; close the browser session when finished. No production security claim is made.

For real validation, first prepare sanitized comparison or verification inputs from authorized runs in `sandbox-platform-services`, location `eu`; keep them in a private catalog directory and set `synthetic` to false only for real evidence. Check CLI results against the UI and compare full report downloads locally. Real billing validation requires separately authorized billing evidence and independent reconciliation.
