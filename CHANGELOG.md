# Changelog

## Unreleased

BigQuery experiments now retain complete, otherwise eligible failed executions for reliability evaluation. Failure rates can fail the verification policy while performance remains UNKNOWN. Missing or otherwise excluded execution evidence still withholds the entire cohort.

Added `run-bigquery` to collect and verify explicit baseline and candidate cohorts, retain collection diagnostics, and generate replayable verification input and a local viewer catalog. Partial or out-of-window cohorts cannot produce PASS. Existing collection command output remains unchanged.

Release-readiness assessment, source-archive rebuild validation, version/license metadata checks, dependency inventory, security/deployment guidance and contributor onboarding. No public release has been published.

## 0.1.0a1

Experimental package foundation, offline comparison engine, strict JSON input and deterministic evidence reports. No stable public interface is promised.

Added bounded BigQuery metadata collection, offline fixtures, optional live SDK transport and explicit collection eligibility. A controlled synthetic BigQuery smoke test and verification experiment passed; broader production workload validation remains outstanding.

Added full configured verification with execution windows, baseline selection, independent correctness evidence, freshness and reliability thresholds. The new verification-0.1 report and verify CLI leave metric-only compare behaviour unchanged.

Added offline financial-0.1 reports, on-demand and capacity interpretations, supplied net-spend comparison, reviewed counterfactual attribution and bounded claim-conflict diagnostics. Pricing and billing fixtures are synthetic. No realized-savings or live-billing validation claim.

### Local viewer

- Added optional authenticated, loopback-only workload and experiment viewer.
- Added curated catalog validation, bounded startup snapshots, safe summaries and opt-in exact CLI report downloads.

### Workflow integration

- Added offline gate command with external policy, explicit UNKNOWN handling, deterministic workflow-0.1 JSON and optional Markdown/HTML artifacts.
- Added hosted GitHub Actions verification example with read-only permissions, run summary and retained reports.

### Adapter extension contracts

- Added adapter-1 interfaces, explicit registry, capability/version checks and generic collection CLI.
- Bridged existing BigQuery collection without changing its legacy report.
- Added an independent fixture adapter, contributor contract template and external typing support.
