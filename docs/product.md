# What DataVouch is for

DataVouch helps data engineers evaluate a workload change before treating it as a successful optimization or release. It brings configured correctness, performance and reliability checks into a reproducible experiment, with explicit PASS, FAIL and UNKNOWN conclusions.

## The problem

A query can finish successfully and run faster while producing the wrong business result. A handful of successful runs can hide intermittent failures. Reduced resource usage can be mistaken for realized financial savings. Evidence for a change often ends up scattered across query histories, spreadsheets and review comments.

The target product turns that review into a repeatable workflow: select original and changed executions, define acceptance checks, collect evidence and inspect a report that another engineer can replay.

## Example: a faster aggregate that omits weights

An engineer rewrites a weighted aggregation query. The following numbers are illustrative, not a DataVouch benchmark.

| Check | Original query | Rewritten query | Result |
| --- | --- | --- | --- |
| Average runtime | 10 minutes | 5 minutes | PASS |
| Output rows | 200,000 | 200,000 | PASS |
| Weighted total | 555,000 units | 240,000 units | FAIL |
| Failed runs | 0 of 10 | 0 of 10 | PASS |

The overall result is FAIL because a required business check failed. Matching row counts and faster execution did not make the changed calculation correct. After fixing the logic and providing passing evidence for every required check, the experiment can pass. If weighted-total evidence is absent, correctness stays UNKNOWN.

PASS applies only to configured checks, comparable inputs and supplied evidence. It is not proof that all future executions or untested business rules are correct.

## Who benefits

- Data engineers reviewing SQL optimizations, pipeline refactoring and configuration changes.
- Reviewers who need a reproducible explanation of why a change is acceptable.
- Platform teams that want consistent evidence requirements in local and CI release workflows.
- FinOps stakeholders who need resource reductions, financial estimates and supported spending differences distinguished clearly.

The first focused use case is validating a BigQuery SQL optimization against a baseline. Additional platforms and migration scenarios require suitable adapters and comparable evidence; they are not all supported today.

## Benefits and boundaries

The intended benefit is earlier detection of regressions and less manual work assembling evidence for review. Saved inputs and consistent UI/CLI conclusions make the decision easier to inspect and repeat. These benefits still need validation with representative workloads and users.

DataVouch does not replace orchestration, continuous monitoring or every data quality tool. It evaluates the evidence for a selected change. Lower runtime or fewer processed bytes do not alone establish a lower bill or prove that the change caused an improvement.

## Available now

- Bounded BigQuery job metadata collection and offline replay.
- Comparison, supplied correctness evidence, execution-window and reliability evaluation.
- Financial evidence classification and configurable workflow gates.
- Local report review, a guided BigQuery plan builder and opt-in backend execution with persistent run history.

Correctness assertions must currently be supplied independently. The plan builder does not run assertion queries or collect metadata, and validating a plan is not a verification result. Explicitly enabled backend execution collects metadata and retains submitted plans/results; browser correctness-evidence entry and financial assessments bind supplied evidence to the experiment. Shared access uses an existing client OIDC gateway with explicit roles and connection scopes. See [product acceptance](product-acceptance.md).

## Product direction

The target experience is **choose a workload → define the change and checks → collect evidence → review results → use the result in a release decision**. The UI, CLI, engines, adapters, tests and documentation stay in one repository.

Start with the [local walkthrough](getting-started.md), then follow [guided experiment planning](web.md#plan-a-bigquery-experiment). See the [delivery milestones](product-roadmap.md) for the distinction between available and planned capabilities.
