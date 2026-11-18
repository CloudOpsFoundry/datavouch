# Run an experiment from the local UI

The optional execution mode collects metadata for selected existing BigQuery jobs, verifies the evidence and retains the results. It does not execute your workload SQL, run correctness assertions or query billing exports. Reviewing reports, validating a plan and downloading it remain offline operations.

## Enable execution on your machine

These steps target macOS or Linux with Python 3.15.2. Shared hosting and Windows execution have not been validated.

1. Follow the [local setup](getting-started.md) and [connection configuration](connections.md). Keep your connection file outside the checkout and writable only by the administrator.
2. Install both optional dependencies from the project folder:

```sh
.venv/bin/python -m pip install ".[web,bigquery]"
```

Developers using the locked environment can use `uv sync --locked --all-extras` instead.

3. Configure backend Application Default Credentials with the permissions described in [BigQuery setup](bigquery.md). Do not put credentials in the form or connections file. For this project's real validation, use only `sandbox-platform-services`, location `eu`, and the matching quota project. Other deployments must configure their own approved identity and scope.
4. Create a private run directory outside the checkout:

```sh
mkdir -p "$HOME/.local/share/datavouch/runs"
chmod 700 "$HOME/.local/share/datavouch/runs"
```

5. Start the server. Replace the connections path with your actual file:

```sh
.venv/bin/python -m datavouch serve examples/viewer.json \
  --port 8766 \
  --connections /absolute/path/to/connections.json \
  --run-directory "$HOME/.local/share/datavouch/runs" \
  --enable-live-execution
```

Enter the local password and open http://127.0.0.1:8766. Without the final opt-in flag, no browser execution is available and no run store is opened.

## Submit and inspect

1. Open **New experiment** and choose an approved project/location.
2. Enter the workload, separate baseline/candidate job IDs, UTC windows and acceptance checks. Live windows must already be closed and within the provider's supported 180-day history range.
3. Select **Validate plan** to check the inputs without cloud access.
4. Confirm metadata collection and its possible query charges. Select **Run experiment**.
5. The run page displays RUNNING and refreshes every three seconds. The backend continues if you close the page. Select **Runs** to return later.
6. On completion, inspect the checks and download the summary. Raw reports remain disabled unless the administrator supplies `--allow-raw-reports`.

Each run can issue two metadata queries, one per cohort. Each query uses the plan's byte cap and timeout, constrained by the connection configuration. These caps are not currency estimates. The worker reloads the administrator's connection file on submission and immediately before launching the CLI. Google Cloud IAM is independently enforced by the provider. Revocation after a query starts cannot retroactively stop it.

A completed run can be PASS, FAIL or UNKNOWN. ERROR means execution failed or was interrupted; it is not a correctness result. Forms accept independently supplied correctness outcomes and references, or advanced evidence JSON. Each record is bound to this experiment and its candidate executions. Leaving evidence unavailable preserves UNKNOWN; a required failure still produces overall FAIL. DataVouch evaluates the supplied evidence but does not execute or authenticate assertions.

## Reliability and storage

- One run at a time, with no queue. Additional distinct submissions are rejected while it is busy.
- Identical canonical plans and connections reuse their existing run, including after restart. There are no automatic retries. For an intentional rerun, first investigate errors or outstanding cloud jobs, then use a new experiment name.
- A worker subprocess runs the same `run-bigquery` command as the CLI. Its wall-clock deadline is the sum of the two collection timeouts plus 30 seconds, at most 630 seconds. A timed-out local process does not guarantee remote query cancellation.
- A SQLite ownership lock prevents two servers from using the same run directory. It is released by the operating system after a crash. Unfinished saved runs become ERROR on restart and are never automatically resumed. After an abrupt shutdown, check for surviving local workers and remote jobs before starting a new experiment.
- A normal shutdown waits for the bounded active worker to finish. Run history and submitted plans survive restart. Unsubmitted form drafts do not.
- History is capped at 50 runs. Stop the server before an administrator archives or deletes complete run directories. There is no automatic deletion or archival UI yet. Do not remove the ownership database while a server is running.
- The private directory contains plan JSON, state JSON and the CLI's replayable inputs, collections and reports. It may contain sensitive job IDs, labels and evidence. Apply your organization's backup, retention and deletion policy to it. Do not commit it to Git.

Local Basic authentication remains the default. Shared deployments use an [existing OIDC gateway](gateway-access.md), explicit roles and connection scopes. Admins can export audit events and delete completed experiments. This is not enterprise certification. See [manual sandbox acceptance](sandbox-acceptance.md) for the final real UI walkthrough.

## Correctness, resources and costs

Choose runtime, slot consumption, processed bytes or billed bytes as the comparison metric. Required checks accept a passed/failed attestation with an independent evidence reference. Advanced JSON supports the existing correctness contract; records must exactly match the experiment and candidate IDs. Changing required check names requires refreshing the form before supplying their guided fields. Missing evidence remains UNKNOWN.

Completed runs show cohort measurements and a financial form. Guided prices produce estimates from saved usage. Advanced supplied billing/review evidence is bound to the same execution windows and IDs. Capacity consumption does not establish billed slot-hours. Assessments are immutable and limited to ten per run.

Search history by workload or experiment, filter outcomes, and revisit the workload catalog. Admin deletion requires confirmation and removes the local plan, evidence, reports and assessments. The audit event remains. Keep raw report downloads disabled unless needed for private replay.
