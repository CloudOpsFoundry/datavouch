# DataVouch

[![CI](https://github.com/CloudOpsFoundry/datavouch/actions/workflows/main.yml/badge.svg?branch=main)](https://github.com/CloudOpsFoundry/datavouch/actions/workflows/main.yml?query=branch%3Amain)
[![Workload verification](https://github.com/CloudOpsFoundry/datavouch/actions/workflows/workload_verification.yml/badge.svg?branch=main)](https://github.com/CloudOpsFoundry/datavouch/actions/workflows/workload_verification.yml?query=branch%3Amain)

The badges show the latest workflow results on `main`. Check each pull request's Checks tab for its own revision. Private repository badges require repository access.

Measure. Validate. Trust.

A project of **CloudOpsFoundry**. *Tomorrow takes shape in today’s open source.*

DataVouch is an experimental data engineering assurance framework. Its purpose is to compare workload executions using reproducible evidence, with explicit PASS, FAIL and UNKNOWN conclusions.

## Available capabilities

The package compares offline workload observations using configurable regression thresholds, explicit units, minimum sample counts and optional input volume normalization. It returns PASS, FAIL or UNKNOWN for the selected metric and includes the underlying evidence in deterministic JSON. The experimental BigQuery adapter collects bounded job metadata from offline fixtures or an explicitly requested live query. A live smoke test with three synthetic SELECT jobs has passed. Broader workload validation remains outstanding.

The `run-bigquery` command collects baseline and candidate jobs, verifies the experiment, and saves replayable inputs, reports and a local viewer catalog. See [BigQuery experiments](docs/bigquery-experiments.md).

The `verify` command combines performance, execution windows, independently supplied correctness evidence and reliability thresholds. Required failures produce FAIL and missing evidence produces UNKNOWN. See [verification](docs/verification.md).

The offline `finance` command distinguishes usage-based estimates, supplied net spending and reviewed counterfactual differences. It rejects overlapping claims and requires matching verification evidence for attribution. See [financial verification](docs/financial.md).

The optional authenticated local viewer shows workload history, evidence and report downloads. See [local viewer setup](docs/web.md).

The `gate` command applies an external verification policy for local and CI workflows, with explicit UNKNOWN handling and optional JSON/Markdown/HTML artifacts. See [workflow integration](docs/workflow.md).

Versioned adapter contracts support explicit registration and capability checks. The BigQuery bridge and an independent fixture adapter are covered by [adapter documentation and contract tests](docs/adapters.md).

## Installation and quick start

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

This is an experimental release. Comparisons are descriptive and do not establish statistical confidence or causation. The metric-only `compare` command reports correctness as UNKNOWN. Full `verify` results apply only to configured checks and supplied evidence. DataVouch does not independently execute assertion queries, authenticate billing evidence, prove realized savings or authenticate billing sources. Financial examples use synthetic rates and amounts, not actual billing. Live BigQuery use requires the optional SDK and authorized credentials. No production readiness claim is made.

See [release readiness](docs/release-readiness.md) for completed local checks and outstanding independent review, and [deployment guidance](docs/deployment.md) for supported local operation.

## Contributing, licence and security

Read [CONTRIBUTING.md](CONTRIBUTING.md). DataVouch uses the [MIT licence](LICENSE). Follow [SECURITY.md](SECURITY.md) to report vulnerabilities without publishing sensitive information.
