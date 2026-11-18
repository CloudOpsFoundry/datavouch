# Supported operation and rollback

DataVouch currently supports an offline CLI and a single-user, loopback-only viewer. Public hosting, reverse proxies, shared servers, containers and multi-user identity have not been validated. Do not treat a successful local test as production deployment approval.

## Install and run

Use a dedicated virtual environment and an explicitly reviewed wheel. Install the base wheel for offline CLI work; include `[web]` for the viewer or `[bigquery]` for explicitly authorized cloud collection. Use the lockfile-backed source environment when reproducing the project's development validation. See [installation](installation.md).

Keep input catalogs and evidence in a private directory separate from public source. Back up inputs and reports using the host's approved access-controlled storage; do not commit credentials or evidence extracts. The application does not provide encrypted storage, backup scheduling or retention enforcement.

Start the local viewer with `datavouch serve /path/to/private/catalog.json`. Set the password interactively, then use `http://127.0.0.1:8765` with username `datavouch`. A URL is reachable only while that process is running. Keep the terminal/process alive during use; stop with Ctrl+C. Catalog contents are snapshotted at startup, so restart to see changed evidence. Passwords are not persisted by DataVouch; browser HTTP Basic credential caching is outside application control.

The CLI does not collect cloud data unless `--live` is selected. For authorized real tests in this project, always use `sandbox-platform-services`, `eu`, matching quota project and bounded selected-job queries. No additional BigQuery API setup is needed if the previously configured environment remains valid. Financial verification still uses supplied offline evidence; billing export access is separate authorization.

## Update or roll back

1. Keep the prior reviewed wheel, dependency lockfile, reports and private inputs.
2. Stop the viewer and install the new reviewed version into a fresh virtual environment. Avoid changing the active environment in place.
3. Run synthetic CLI fixtures and inspect viewer authentication and report downloads before selecting real evidence.
4. If validation fails, stop the new process and restart the prior environment against the preserved inputs. There is no managed database or schema migration in this version.
5. Preserve the failure's sanitized diagnostic and exact package/artifact version for investigation. Do not blindly retry a timed-out BigQuery request; first check whether the query is still running.

Report and configuration schema versions are explicit. An older release may reject newer inputs; do not overwrite the only copy of an earlier compatible input or report. Partial artifact output from a failed write is not accepted evidence.
