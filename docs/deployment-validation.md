# Product and deployment validation

Validation date: 18 November 2026. This record distinguishes implemented functionality and measured acceptance from independent release approval. Private runtime logs and generated evidence remain outside Git.

## What the local use case demonstrated

Previous local validation exercised a correlated aggregate, an equivalent rewrite and an intentionally incorrect rewrite against generated data. It verified actual execution measurements, independent correctness checks and byte-identical replay. These historical checks are not a benchmark of the current example. Use the [aggregation walkthrough](aggregation-walkthrough.md) to generate fresh measurements for the current code.

## Executed validation

| Path | Actual checks | Scope |
| --- | --- | --- |
| Local product | SQL execution, independent oracle, PASS/FAIL/UNKNOWN, report replay, authenticated UI | Python 3.15.2 on macOS ARM64 |
| Compose | Empty connection configuration, anonymous denial, authenticated pages, measured demo, restart and retained evidence | Restricted Linux ARM64 container on Docker Desktop |
| Helm contracts | Lint/schema, security defaults, gateway/live/storage variants, invalid-config rejection, chart packaging | Helm 4.2.0 |
| Kubernetes | Install, non-root/private volume, authenticated UI, measured demo, PVC persistence across pod restart, trusted/forged gateway headers, viewer restriction, rollback, PVC retention on uninstall | Isolated namespace on local Kubernetes 1.34.1; kubectl 1.34.13 |
| Release packages | Wheel/source builds, clean installation, demo CLI, report parity, archive exclusions | Automated validator and self-hosted CI |

The Kubernetes acceptance namespace, generated test Secrets and temporary evidence were removed after the check. Existing workloads were not changed. No live cloud workload or billing API was accessed for these tests. Generic deployment defaults contain no selected cloud project or location.

## Findings fixed during review

- Browser form submissions were rejected by cross-site protection because `Referrer-Policy: no-referrer` caused Chrome to send `Origin: null`. The policy now uses `same-origin`, preserving same-origin form submissions without sending referrers to other origins. Null and foreign origins remain rejected. Actual Chrome clicks reproduced the failure before the fix and verified individual, selected and all-history deletion afterward, including removal of the disposable history directories. Earlier HTTP-client journey tests did not cover this browser behavior.
- A fresh connections file with an empty allowlist previously failed startup despite being documented for initial Compose use. Empty configuration now starts safely and leaves planning disabled; it grants no cloud scope.
- Kubernetes deployment support was missing. The chart now expresses the actual single-owner store model rather than implying unsupported horizontal scaling.
- Users lacked a measured, self-contained example demonstrating a business error. The local demo now supplies real SQL results and independently derived correctness evidence.
- Container dependency downloads could repeat after documentation/source changes. Build layers and the shared build cache now reuse resolved dependencies; runtime dependencies are installed offline from that cache.

## What is complete and what remains

A stopped-store backup was also copied to a separate location, the original fixture store removed, and the backup restored and reopened. Both experiment reports, financial files and audit history retained identical hashes. This validates local file recovery with disposable data; client volume snapshots, encryption, access controls and recovery objectives still require deployment-specific acceptance.

The initial product workflow in [the acceptance matrix](product-acceptance.md) is implemented: explicit workload registration, baseline/candidate collection, declared comparability, configured correctness/performance/reliability evaluation, supplied financial assessment, reproducible reports, CLI/UI/workflow use and adapter extension contracts. Compose and Helm deployment paths are now implemented and locally exercised.

This is not unrestricted production or public-release approval. The following remain:

- A client's actual BigQuery workloads, permissions, quota project and independently produced correctness evidence must pass that client's acceptance. Existing bounded synthetic test-project validation does not certify arbitrary workloads.
- Real identity-provider login/logout, gateway header sanitization, TLS, credential rotation, backup restore and actual CNI network-policy enforcement require deployment-specific validation. Port forwarding and simulated verified headers do not test an IdP or network isolation.
- Independent onboarding, security review, financial-method review and ownership/dependency-license approval remain release gates.
- Before going public, replace the private trusted-runner contribution model with an isolated public-contribution CI model and establish enforceable repository protections. No visibility change or paid upgrade was made.

Additional provider implementations, automatic workload discovery, high availability, distributed worker queues and automated billing ingestion are future extensions. The current product does not claim those capabilities. User-supplied assertions are evaluated, not independently executed by the BigQuery metadata collector; the demo includes its own independent checker to make this distinction observable.

## Reproduce

```sh
uv sync --locked --all-extras
uv run --no-sync python scripts/validate.py
python scripts/check_compose.py
python scripts/check_kubernetes.py --context YOUR_LOCAL_CONTEXT
```

The two infrastructure checks require a built `datavouch-app:local` image. The Kubernetes check requires that image in the selected cluster and permission to create/delete its own test namespace. It does not alter kubeconfig. See [container setup](container.md) and [Kubernetes setup](kubernetes.md) for prerequisites. Both checks deliberately remove only their generated test resources; retain required results before running unrelated teardown commands.
