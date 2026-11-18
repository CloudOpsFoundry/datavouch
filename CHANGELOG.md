# Changelog

## v1.0.0

Initial source release for BigQuery workload verification with CLI, authenticated UI, replayable evidence, financial assessments, Docker Compose and Helm deployment. Public CI uses disposable hosted runners. No package, image or CI artifact is published. Client-specific identity, network and recovery acceptance remains the deployment owner’s responsibility; this version is not an independent security certification.

## v0.2.1a0 (2026-11-18)

### Fix

- preserve historical changelog entries during releases (#8)

## v0.2.0a0 (2026-11-18)

### Feat

- automate private alpha releases and generalize examples

Add automatic private alpha versions, annotated tags and release notes after successful main CI, with Conventional Commit classification, synchronized package/Helm metadata and retry-safe atomic pushes.

Replace the industry-specific demonstration with a neutral synthetic weighted aggregation example. The demo now uses `--groups`, generic result fields and `/guide/weighted-aggregation`; regenerate sample catalogs rather than mixing old and new example outputs. Existing saved verification reports are not modified. Add a technical dependency-license review; independent ownership and publication approval remain pending.

## 0.1.0a2

Private alpha for acceptance testing. Existing report schemas remain unchanged; stable API compatibility is not promised. Independent client, security, onboarding and license acceptance remains pending.

- Add deployment-approved, authenticated Google Cloud project and observed BigQuery location discovery with bounded requests, caching and refresh.
- Add a synthetic aggregation example walkthrough, measured local and opt-in BigQuery examples, report recommendations and a same-page path to the first experiment.

- Add an authenticated user guide and contextual explanations for workloads, experiments, runs, report types and outcomes.
- Prepare real client identity/network acceptance and independent security, onboarding, financial-method and license review procedures.
- Fix legitimate browser form submissions rejected by the referrer policy while retaining cross-site protection.

- Add admin selection and all-history deletion with exact-instance confirmation, connection isolation, durable file removal and explicit failure handling.

- Add a measured local SQL demo with independently checked results and replayable PASS/FAIL/UNKNOWN evidence.
- Fix empty connection allowlists so fresh offline deployments start with planning disabled.
- Add Helm deployment, schema/security checks, persistent storage and local Kubernetes acceptance tooling.
- Add Compose execution, gateway, ADC and demo overrides with repeatable runtime checks.

- Add guided correctness evidence, resource metric selection, saved financial assessments and workload history filters.
- Add existing OIDC gateway integration, explicit roles and connection scopes, subject-bound forms, audit export and confirmed retention deletion.
- Add a non-root application container, client deployment guidance and final BigQuery acceptance walkthrough.

Added opt-in local UI execution through a bounded CLI worker, with deployment scope revalidation, explicit collection consent, duplicate-plan protection, persistent run history and result downloads. Concurrent submissions are bounded and interrupted runs never automatically retry.

Added UTC calendar and time controls for baseline, change and candidate windows, with explicit UTC serialization and server-side calendar validation.

Added deployment-owned project/location connections with a dropdown, server-side scope validation and collection limits. Missing configuration disables planning without affecting report review.

Added guided local BigQuery experiment planning with bounded authenticated form submission, shared CLI validation, conservative evidence defaults and plan downloads. Clarified the product purpose and first optimization use case.

Classified BigQuery failures may omit the provider's optional normalized fingerprint without losing reliability evidence. Successful jobs still require fingerprints, and all other exclusions remain conservative.

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
