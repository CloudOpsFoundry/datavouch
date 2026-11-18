# DataVouch: BigQuery Optimization Validation

[![CI](https://github.com/CloudOpsFoundry/datavouch/actions/workflows/public.yml/badge.svg?branch=main)](https://github.com/CloudOpsFoundry/datavouch/actions/workflows/public.yml?query=branch%3Amain)

## **Measure. Validate. Trust.**

A project of **CloudOpsFoundry**. *Tomorrow takes shape in today’s open source.*

DataVouch is a Python tool for **BigQuery optimization validation, data correctness checks and performance regression testing**. Compare baseline and candidate workloads, review reliability and FinOps evidence, and use explicit **PASS, FAIL or UNKNOWN** results in your release decisions. [Purpose, use cases and benefits](docs/product.md).

**Did your SQL optimization make the query faster without changing the result?** DataVouch brings the measurements and independently supplied correctness checks into one replayable report. Use the CLI, authenticated web UI or CI workflow gate in your own environment.

See the benefit through [a synthetic aggregation walkthrough](docs/aggregation-walkthrough.md): compare a query rewrite against an independently checked weighted sum. Open **Example walkthrough** in the UI, or run the local example without a cloud account.

Learn [workloads, experiments, runs and results](docs/user-guide.md), or open **User guide** in the application.

Start with the [step-by-step local guide](docs/getting-started.md). DataVouch is developed as a monorepo; see the [product and UI roadmap](docs/product-roadmap.md) for delivery scope. The [acceptance checklist](docs/product-acceptance.md) maps product requirements to implementation and final release gates.

## Available capabilities

| Your question | DataVouch capability |
| --- | --- |
| Did a BigQuery SQL change cause a performance regression? | Compare baseline and candidate execution measurements against configured thresholds. |
| Does the optimized query still produce the expected result? | Evaluate independently supplied correctness evidence; missing evidence stays UNKNOWN. |
| Did failures increase after the change? | Evaluate observed execution reliability alongside performance. |
| Does reduced resource usage support a cost claim? | Separate usage estimates, supplied spending and reviewed attribution in a FinOps assessment. |
| Can a reviewer reproduce the release decision? | Replay saved evidence and apply an explicit CI acceptance policy. |

The package compares offline workload observations using configurable regression thresholds, explicit units, minimum sample counts and optional input volume normalization. It returns PASS, FAIL or UNKNOWN for the selected metric and includes the underlying evidence in deterministic JSON. The experimental BigQuery adapter collects bounded job metadata from offline fixtures or an explicitly requested live query. The generated weighted-aggregation walkthrough exercises real BigQuery jobs and verification. Acceptance against real client workloads remains a separate requirement.

The `run-bigquery` command collects baseline and candidate jobs, verifies the experiment, and saves replayable inputs, reports and a local viewer catalog. See [BigQuery experiments](docs/bigquery-experiments.md).

The `verify` command combines performance, execution windows, independently supplied correctness evidence and reliability thresholds. Required failures produce FAIL and missing evidence produces UNKNOWN. See [verification](docs/verification.md).

The `finance` command and saved-run financial form distinguishes usage-based estimates, supplied net spending and reviewed counterfactual differences. It rejects overlapping claims and requires matching verification evidence for attribution. See [financial verification](docs/financial.md).

The optional authenticated local UI shows workload history, evidence and report downloads, guides you through creating a validated BigQuery experiment plan, and optionally runs bounded collection with persistent local history. It accepts independently supplied correctness evidence and shows collected resource measurements and financial assessments. See [UI execution](docs/ui-execution.md), [Docker Compose](docs/container.md), [Kubernetes with Helm](docs/kubernetes.md), and [client OIDC gateway access](docs/gateway-access.md).

The `gate` command applies an external verification policy for local and CI workflows, with explicit UNKNOWN handling and optional JSON/Markdown/HTML artifacts. See [workflow integration](docs/workflow.md).

Versioned adapter contracts support explicit registration and capability checks. The BigQuery bridge and an independent fixture adapter are covered by [adapter documentation and contract tests](docs/adapters.md).

## Installation and quick start

CI imports a pinned reusable workflow from CloudOpsFoundry/ci-templates and runs the product validator with visible stage groups. See the [pipeline stages](docs/development.md#visible-ci-stages).

Python 3.15 is required. From this source checkout:

```sh
python -m pip install .
datavouch --version
python -m datavouch --help
datavouch compare examples/bigquery/comparison.json > report.json
datavouch verify examples/verification/passing.json > verification.json
datavouch finance examples/financial/reviewed.json > financial.json
datavouch collect-bigquery examples/bigquery/collection_config.json --fixture examples/bigquery/jobs.json > collection.json
```

See [installation](docs/installation.md), [development](docs/development.md) and [architecture](docs/architecture.md), [BigQuery setup](docs/bigquery.md) and [input configuration](docs/configuration.md).

The synthetic example has baseline mean 100 ms and candidate mean 80 ms, a 20 percent runtime reduction. This is an illustrative fixture, not a measured product performance claim. The metric passes its 5 percent regression limit. Correctness remains UNKNOWN.

## Limitations

Version 1.0 covers the implemented BigQuery and offline verification workflows. Comparisons are descriptive and do not establish statistical confidence or causation. The metric-only `compare` command reports correctness as UNKNOWN. Full `verify` results apply only to configured checks and supplied evidence. DataVouch does not independently execute assertion queries, authenticate billing evidence, prove realized savings or authenticate billing sources. Financial examples use synthetic rates and amounts, not actual billing. Live BigQuery use requires the optional SDK and authorized credentials. No production readiness claim is made.

This is a source-only release. No wheel, container image or CI artifact is published. Client-specific acceptance and independent reviews remain unverified. The [review pack](docs/review-pack.md) and [client validation procedure](docs/client-validation.md) define the required evidence and sign-offs.

See [release readiness](docs/release-readiness.md) for completed local checks and outstanding independent review, and [deployment guidance](docs/deployment.md) for supported local operation.

## Contributing, licence and security

Read [CONTRIBUTING.md](CONTRIBUTING.md). DataVouch uses the [MIT licence](LICENSE). Follow [SECURITY.md](SECURITY.md) to report vulnerabilities without publishing sensitive information.

Google Cloud projects and observed locations can be discovered using backend workload credentials, with deployment and user access controls. See [Google Cloud connections and discovery](docs/connections.md) for setup and permissions.

## Release workflow

See [version 1.0 scope and acceptance](docs/releases/1.0.0.md). Public CI validates each push and pull request. Release tags identify reviewed main revisions; packages and images are built by users in their own environments. Releases are maintained manually through protected PRs; see the [release procedure](docs/automated-releases.md).
