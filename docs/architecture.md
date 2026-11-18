# Architecture

The CLI loads bounded JSON through `core.configuration`. Immutable records in `core.models` validate measurements and experiment metadata. `analysis.comparison` checks eligibility and evaluates one metric against a policy. `reports.json_report` serializes the raw observations and conclusions with stable ordering and an input digest.

The core and adapter registry use only the standard library. Shared verification does not import provider libraries. Adapters translate bounded provider records into the shared model. The BigQuery adapter validates collection scope, converts minimal job metadata, and exposes optional SDK transport. Its offline path requires no cloud libraries. The live client has mocked transport tests and a successful synthetic live smoke test. The optional web layer is described below. Product readiness remains experimental.

The separate verification layer selects fully contained baseline and candidate executions around an explicit change time. It evaluates declared schema, checksum, boolean assertion and freshness evidence, then computes failure rates from caller-attested complete cohorts. Required results combine with FAIL before UNKNOWN before PASS. Evidence references do not execute code or trigger network requests. The existing metric-only compare contract remains unchanged.

The financial layer validates immutable pricing, usage, billing and claim records. It uses exact rational arithmetic for costs and normalization. Billing attribution requires bound verification inputs and declared review evidence. Claim overlap checks cover shared billing IDs and intersecting windows on the same billing scope. The finance CLI reads bounded local JSON and never queries a billing export or pricing endpoint.

## Local viewer

The optional FastAPI/Jinja2 presentation layer loads an explicit, bounded catalog into immutable startup snapshots. Existing comparison, verification and financial engines own calculations and JSON serialization. HTTP routes render allowlisted fields and require local authentication; full evidence downloads require an explicit flag. The core package remains dependency-free. See [web setup](web.md).

## Workflow gate

The standard-library workflow layer applies an explicit external policy to a copied verification input, delegates to the existing engine, and projects safe report fields. Evidence status and gate decision are separate; UNKNOWN never becomes PASS. Artifact writes require an explicit new output directory. See [workflow integration](workflow.md).

## Versioned adapters

The explicit registry checks API/config versions and declared modes before calling a trusted adapter. Immutable batches account for observations, missing executions and exclusions without changing verification engines. The existing BigQuery collector is bridged to adapter-1; SDK imports remain confined to explicit live calls. A separate fixture adapter demonstrates extension without core edits. See [adapter contracts](adapters.md).
