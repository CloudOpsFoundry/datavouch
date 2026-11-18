# Adapter extension contract

Adapters translate bounded platform evidence into DataVouch's provider-independent observations. Version 1 supports collection only. It does not certify correctness, completeness, billing, comparability or causal improvements. The core comparison, verification and financial engines do not import adapters or provider SDKs.

## Use registered adapters

```sh
.venv/bin/datavouch adapters
.venv/bin/datavouch collect examples/adapters/bigquery_connector.json \
  --fixture examples/bigquery/jobs.json
```

Both commands run offline. `adapters` lists versions, supported modes and metrics without loading a Google SDK or authenticating. `collect` requires exactly one of `--fixture PATH` or `--live`; exit 0 means eligible collection, 3 means ineligible/incomplete, and 2 means configuration, compatibility or collection error. Collection eligibility is not verification PASS. Only use observations from eligible batches for comparison, and still supply explicit comparability evidence and required correctness checks.

The existing `collect-bigquery` command and its `bigquery-collection-0.1` report remain supported unchanged. The generic bridge produces `adapter-collection-1` and preserves the existing collector's observations and eligibility rules. Provider-specific fingerprint groups and timestamps remain available through the original command; the generic report carries observations, missing IDs, exclusions, notes and adapter identity.

The bundled BigQuery fixture is synthetic and contains its original example scope. Do not use it with `--live`. For this project's real validation, create a private connector with project `sandbox-platform-services`, location `eu`, matching quota project, selected authorized job IDs and bounded windows/budgets. No new cloud setup is required when existing credentials and API access remain valid.

## Connector envelope

```json
{
  "adapter": "bigquery",
  "api_version": "adapter-1",
  "config_version": "bigquery-config-0.1",
  "config": {
    "...": "provider-specific configuration"
  }
}
```

The example above illustrates the envelope; replace `config` with the full documented provider schema. Envelope fields are exact. Unknown adapters and incompatible API/configuration versions are rejected before validation or collection. Configuration must be an object; the CLI rejects JSON larger than 5 MB or with duplicate keys. Provider configuration is validated again by the adapter. No import paths or executable code are read from connector JSON.

## Implement an adapter

Public interfaces are in `datavouch.adapters.contracts` and `datavouch.adapters.registry`, and shared evidence types are in `datavouch.core.models`. The package includes a `py.typed` marker for external type checking.

An adapter implements the structural `Adapter` protocol:

- `info: AdapterInfo`: immutable name, implementation version, API/config versions, modes and metrics.
- `validate_config(config: object) -> None`: validate without network access, authentication or writes.
- `collect(config: object, *, fixture: Path | None, live: bool) -> ObservationBatch`: perform only the explicitly requested collection.

Implementation versions use numeric `major.minor.patch`. API version must equal `adapter-1`; configuration versions are adapter-owned opaque strings matched exactly. Declare fixture/live capabilities truthfully and metrics with exact names, units and direction. Changing a contract incompatibly requires a new API or configuration version; reports record the implementation version for reproducibility. Pin the trusted adapter package/revision separately; the registry does not install or upgrade dependencies.

Use immutable `ObservationBatch` records. Each of 1–100 unique requested execution IDs must appear exactly once as an observation, a missing ID, or an `Exclusion`. Failed, cached or unmeasured executions belong in exclusions. Missing/excluded records prevent eligibility. Complete collections may still be ineligible, for example because BigQuery fingerprints differ. Always include bounded notes explaining limitations. Measurements must match declared metrics, units and direction. Core models reject invalid/nonfinite/negative measurements and duplicate metric names.

The registry copies configuration and retains an immutable descriptor snapshot at registration. It validates the returned batch type and declared metrics and normalizes execution ordering for deterministic JSON. Adapter exceptions become generic diagnostics to avoid exposing provider messages. Keyboard interrupts and process termination are not swallowed. Keep provider details and SDK imports inside the adapter. Import SDKs lazily for live calls, apply timeouts and budgets, and never run workload mutations as metadata collection.

## Explicit registration and example

[The example adapter](../examples/adapters/local_metrics.py) is outside the DataVouch package and uses synthetic local runtime fixtures. It introduces no second real platform. Run it with:

```sh
.venv/bin/python examples/adapters/run_example.py
.venv/bin/python -m pytest examples/adapters/test_contract_template.py
.venv/bin/python -m mypy examples/adapters/local_metrics.py examples/adapters/run_example.py
```

Its runner explicitly constructs `Registry()` and calls `register(LocalMetricsAdapter())`. A contributor can do the same in a trusted integration script; no core engine edits or adapter inheritance are required. The stock CLI uses the built-in registry containing BigQuery. There is no automatic package discovery, import-by-string configuration, or third-party CLI loading in this version. Duplicate registration is rejected, and the registry should be configured before concurrent use.

Registered adapters are trusted Python code, not sandboxed plugins. Contract validation catches incompatible outputs; it cannot prove that a plugin truthfully reports requested scope, refrains from network access, or produces authentic observations. Review plugin code and dependencies before importing it. Reports include execution IDs and caller-supplied metadata; keep real collection files private.

## Contributor acceptance

Copy [the contract test template](../examples/adapters/test_contract_template.py) and replace its adapter, connector and fixtures. It tests deterministic offline collection, explicit source selection, unsupported live calls, missing evidence, incompatible versions and unexpected records. Add provider-specific tests for duplicate/malformed records, scope/window enforcement, credentials unavailable, denied permission, timeouts, budgets and SDK import isolation. Mock transport first. Declare the exact supported API/config versions and document unsupported evidence.

The repository's tests additionally check the BigQuery bridge against the existing output, exclusions and fingerprint eligibility, safe error boundaries, undeclared metric rejection, and an external adapter feeding the unchanged comparison engine. Passing these tests is extension compatibility evidence, not independent external adoption.

## Next real validation

1. Run the offline commands above and the full `python scripts/validate.py` checks.
2. Have an independent contributor implement and run the contract template in a separate package against the built wheel.
3. If fresh cloud validation is needed, prepare a private BigQuery connector for `sandbox-platform-services/eu` and use `collect private-connector.json --live` only for the explicitly authorized bounded metadata query. Compare its observations and eligibility with `collect-bigquery` using the equivalent provider config. Never infer savings or correctness from collection eligibility.
