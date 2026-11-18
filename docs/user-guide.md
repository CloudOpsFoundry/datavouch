# Workloads, experiments and runs

DataVouch answers: **did this specific change preserve the required business result while meeting our performance and reliability policy?** The authenticated UI also includes this explanation under **User guide**.

## The main concepts

| Concept | Meaning | Example |
| --- | --- | --- |
| Connection | Administrator-approved project/location pair and collection limits | A client's analytics project in its approved region |
| Workload | Stable name for a data-processing task | Daily revenue |
| Change | What you altered and why | Replace a correlated subquery with an aggregate |
| Baseline | Original completed executions used as the reference | Three uncached jobs using the original SQL |
| Candidate | Completed executions after the change | Three uncached jobs using the rewritten SQL |
| Experiment | One change, selected baseline/candidate groups, comparison contract and check policy | Revenue rewrite, revision 2 |
| Plan | Validated configuration for an experiment | Job IDs, UTC windows, required assertions and byte limit |
| Run | Saved execution of a DataVouch plan, with collection state and result | One evaluation of the six selected jobs |
| Evidence | Measurements or independently supplied checks supporting a conclusion | Job runtime plus independently verified revenue totals |
| Financial assessment | Separate evaluation of pricing, spending and attribution evidence | A usage estimate or a reviewed spending difference |

A cloud job and a DataVouch run are different. A run evaluates groups of existing jobs. Clicking **Run experiment** collects metadata; it does not execute the workload SQL, rerun failed jobs, or execute your assertion SQL.

## Different workloads

Workloads are business tasks you name, not a fixed list of built-in product types.

| Use case | Example change | Useful independent correctness evidence |
| --- | --- | --- |
| Revenue aggregate | Rewrite a query or change joins | Totals including quantities, refunds and currency rules |
| ETL/ELT transformation | Refactor transformation SQL | Business assertions, schema and stable output checksum |
| Incremental refresh | Change watermark or partition logic | Freshness, duplicate/missing-record checks and input snapshot |
| Resource optimization | Reduce processed bytes or slot consumption | Same business result under comparable inputs and conditions |

Live collection currently supports BigQuery. These examples do not imply that DataVouch orchestrates pipelines or already has every cloud adapter. The core accepts explicit adapter contracts and offline evidence; additional live platforms need implementations.

The bundled **Daily summary** workload contains synthetic comparison, verification and financial reports. The generated **Event ticket sales** demo executes real SQLite queries on generated data. These examples are not automatically discovered client workloads. In gateway mode, startup sample catalogs are disabled to keep the shared workspace limited to authorized runs.

## Report types

The sample catalog contains three kinds of report. **Comparison** evaluates a selected metric and leaves correctness UNKNOWN. **Verification** combines configured performance, correctness, execution-window and reliability checks. **Financial** evaluates supplied pricing, spending and attribution evidence. These report types can describe the same workload; they do not select a different cloud provider.

## Use the interface

1. **Overview:** see available outcomes and recent authorized runs. An outcome is evidence about one experiment, not a health score for an entire platform.
2. **Workloads:** inspect imported catalog reports and names registered by saved runs. Keep the same workload identity for related changes. Catalog files are read-only snapshots loaded at startup; collected runs are stored by the application.
3. **New experiment:** if live discovery is enabled, select a Google Cloud project and choose **Load locations** first. Then choose an approved project/location connection, identify the change and supply existing job IDs. Select the change time and baseline/candidate windows in **UTC**, even if your browser is in another time zone. End times are exclusive. Use comparable inputs and include failures, not just favorable samples.
4. **Validate plan:** fix structural errors and download the plan if needed. This performs no cloud collection and is not a verification PASS.
5. **Run experiment:** explicitly authorize bounded metadata collection. This option appears only when execution is enabled and your role permits it. Supply independent correctness evidence; leave it missing if it has not been checked.
6. **Runs:** open the saved report, examine each reason, measurements, excluded jobs and limitations. Investigate ERROR before resubmitting. The same plan in the same execution context reuses its saved result; use a new experiment identity for a distinct evaluation.
7. **Financial assessment:** optionally attach pricing or reviewed spending evidence matching this experiment. A runtime reduction does not by itself establish a lower bill.

A plan does not automatically discover job IDs, create test data or establish comparable inputs. Follow [the BigQuery walkthrough](bigquery-acceptance.md) for an explicit end-to-end example, or [the local demo](local-demo.md) without cloud access.

## States and conclusions

| Label | Meaning | Next action |
| --- | --- | --- |
| RUNNING | Collection is in progress | Wait; only one experiment runs at a time |
| COMPLETED | A report was produced | Read its PASS, FAIL or UNKNOWN conclusion |
| ERROR | Collection or processing failed | Inspect the sanitized error and backend configuration |
| PASS | Configured checks passed with sufficient supplied evidence | Review evidence and scope before accepting the change |
| FAIL | A required check failed | Investigate the failed check; do not waive it just to pass |
| UNKNOWN | Evidence is missing, insufficient or unsuitable | Obtain the missing evidence or leave the decision unresolved |

A required failure takes precedence over UNKNOWN. Matching row counts alone do not establish correctness. PASS does not establish statistical significance, causation, whole-system correctness or future reliability.

In the local revenue demo, the correct total is **55,500,000 cents (€555,000)**. An incorrect rewrite returns **24,000,000 cents (€240,000)** because it ignores quantities. It can run faster and execute successfully, but must fail the business check. With that check absent, correctness is UNKNOWN. This is why a query execution status alone is not enough.

## Permissions, history and data

Viewers inspect permitted results. Operators also create experiments, collect metadata and add financial assessments. Administrators additionally delete history and export scoped audit events. Access is scoped by connection, not by individual workload within that connection.

Admins can delete one, selected or all permitted saved runs. Bulk deletion previews the exact selection; all-history includes permitted runs hidden by filters. Active runs cannot be deleted. Deletion removes local plans, evidence, reports and financial assessments. It does not remove cloud jobs, imported catalog files, audit events or backups. SQLite holds only the store-ownership lock; experiment history is stored in private files.

Current deployment limits are one process, one active experiment, 50 saved runs and ten financial assessments per run. Shared team access uses an existing client identity gateway. Raw report downloads are an explicit deployment option and are unavailable to viewers. See [client validation](client-validation.md) before shared use.

For a complete event-booking story, open **Example walkthrough** in the UI or follow the [ticket-sales walkthrough](ticket-sales-walkthrough.md). Report recommendations explain whether to proceed to review, reject a failed change, or hold for evidence.
