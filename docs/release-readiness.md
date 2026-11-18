# Release-readiness assessment

DataVouch 1.0 is a source release for the supported scope in [the release notes](releases/1.0.0.md). **Client-specific production acceptance and independent security review remain unverified.** Use `datavouch --version` and the corresponding Git tag to identify the installed revision. Local engineering checks are distinct from approval to publish or deploy.

## Assessment matrix

| Area | Evidence or action | State |
| --- | --- | --- |
| Dependencies | Core has no dependencies; optional SDK/web dependencies locked; installed environment vulnerability audit | Locally tested; inventory available |
| Security | Automated source scan, tested input/authentication boundaries, documented threat assessment | Local assessment; independent review pending |
| Installation | Clean wheel CLI and external adapter replay; prior isolated web-wheel HTTP test | Locally tested |
| Packaging | Wheel/source metadata, version consistency, LICENSE, typing marker, private-file exclusions; source rebuild compared with wheel | Automated local checks |
| Python compatibility | Full suite on Python 3.15.2, macOS and Linux ARM64 | Python 3.15 required; other OS combinations require validation |
| Benchmarks | Reproducible synthetic comparison benchmark on Python 3.15.2 | Measured; no service-level guarantee |
| Documentation | Setup, CLI, policy, adapter, web and deployment guides | Locally reviewed; external onboarding pending |
| Versioning/changelog | Automated private alpha versions, annotated tags, preserved changelog history and package/artifact consistency checks | Implemented; verify each main release run |
| Licensing | MIT file present in source and distributions; dependency license metadata inventoried | Owner confirmed source ownership; independent dependency review pending |
| Source publication | Source-only CloudOpsFoundry/datavouch release; local context and infrastructure excluded | Owner authorized publication; client acceptance remains unverified |
| GitHub Actions | Pinned actions, read-only permissions, self-hosted push/PR/main validation | Merged main validation passed; each new revision requires checks |
| External users | Scripted contributor acceptance exercise below | Independent participation pending |
| Deployment | Local workspace, opt-in execution, Compose and Helm deployments, OIDC gateway roles/scopes | Real IdP and client infrastructure acceptance pending |

## Repeatable local evidence

```sh
uv sync --locked --all-extras
uv run --no-sync python scripts/validate.py
uv run --no-sync python scripts/benchmark.py
uv run --no-sync python scripts/check_release.py > /tmp/datavouch-release-inventory.json
```

The validator stops at the first failure. It checks formatting, lint, types, tests/coverage, source and dependency security scans, builds, archive boundaries, clean installation, source-archive rebuild and release metadata. `check_release.py` emits artifact hashes and a bounded inventory of the installed validation environment, including development tools. It is not a complete SBOM, license opinion, or approval gate. A successful exit means local checks passed; it does not clear external readiness requirements. Inventory hashes change when artifacts are rebuilt; retain the report with the exact artifacts reviewed.

The validator builds the source archive and wheel directly from the checkout. `check_sdist.py` rebuilds one wheel from that source archive using installed build dependencies, then compares every member with the existing wheel. This proves archive completeness under the tested toolchain; it does not establish reproducibility across all platforms or dependency versions.

## Security assessment

| Boundary | Implemented controls | Remaining limits |
| --- | --- | --- |
| Offline JSON | Size limits, duplicate-key rejection, strict schemas, finite numeric validation, explicit missing evidence | Inputs and attestations are not authenticated |
| BigQuery | Explicit live mode, project/location scope, selected job IDs, parameterized reads, byte/time bounds, lazy credentials | Metadata queries can cost money; denied-access behavior tested with mocks; synthetic failed-job validation completed in an authorized test project; no production workload certification |
| Local viewer | Loopback binding, password authentication, Host allowlist, cross-site checks, CSP, no-store, escaped templates, bounded startup snapshot | HTTP Basic has no application logout/session revocation; local machine/browser must be trusted; no public deployment assessment |
| Evidence display | Allowlisted viewer/workflow summaries and opt-in raw viewer downloads | Labels can contain sensitive text; CLI collection/raw reports include execution metadata |
| Adapter extension | Explicit registration, version/mode/metric checks, immutable result contracts, generic errors | Adapter Python code is trusted and not sandboxed; claims and side effects cannot be independently enforced |
| CI | Isolated self-hosted jobs, read-only permissions, pinned action commits, checkout credential persistence disabled, no cloud secrets | Repository writers can alter policies/workflows; branch protection and trusted evidence production must be configured |
| Releases | Private-context exclusions, artifact metadata/content checks and hashes | Pattern-based secret scan is incomplete; independent source/security review is required; security@sourabhsharma.com is the configured reporting channel |

Actions were pinned to official [checkout v7.0.1](https://github.com/actions/checkout/releases/tag/v7.0.1) and [setup-python v7.1.0](https://github.com/actions/setup-python/releases/tag/v7.1.0), replacing moving major-version tags. Dependabot can propose pin updates. Pinning fixes the reviewed reference; it is not an independent audit of those actions.

## External contributor acceptance exercise

Use an authorized clean machine without production credentials. Record OS, Python version, package version, artifact hash, commands, actual outcomes and problems encountered.

1. Install the reviewed wheel into a new virtual environment. Run `datavouch --version` and `datavouch adapters`.
2. Using the accompanying source examples, run the PASS, FAIL and UNKNOWN cases in [workflow integration](workflow.md). Verify exits 0, 1 and 3. Inspect JSON, Markdown and HTML; explicitly allowed UNKNOWN must remain labeled UNKNOWN.
3. Implement a small fixture adapter in a separate package using [the contributor template](adapters.md). Verify incompatibility rejection, missing evidence and deterministic output without editing core modules.
4. With the web extra installed, follow [local viewer setup](web.md). Verify authentication, filtering, failure/missing states and downloads. Keep raw evidence downloads disabled unless reviewing safe fixtures.
5. Report reproducible results through the agreed private channel. Do not include credentials, customer SQL, raw billing or personal data. Maintainers triage failures and rerun the relevant checks after fixes.

This exercise has been simulated by local automated tests, but no independent external contributor has completed it yet.

## Release process and outstanding decisions

The destination is CloudOpsFoundry/datavouch, the selected source license is MIT, and the confirmed private reporting address is security@sourabhsharma.com. Before publication, obtain ownership/dependency-license approval and confirm release maintainers. Review the GitHub Free private-repository protection limitations and establish enforceable protections for public release. The self-hosted workflow remains restricted to trusted private-repository pushes. A separate public-contribution workflow is prepared on disposable hosted runners; hosted execution, removal of self-hosted access and enforceable branch protections remain publication gates. See [public CI preparation](development.md#public-contribution-ci-preparation). Run the actual workflows, including failing and blocked-UNKNOWN fixtures. Obtain independent security and user-testing results and resolve material findings.

The [automatic release workflow](automated-releases.md) synchronizes package, lockfile and Helm versions and generates the versioned changelog after main CI succeeds. It validates stamped artifacts before atomically pushing the release commit and tag. Dependency upgrades and compatibility changes remain reviewed product changes; manual version edits are not part of the routine release process. Retain artifact hashes with the exact artifacts reviewed. Public publication requires the independent gates and explicit owner authorization; it is not enabled by the private alpha workflow.

See [deployment guidance](deployment.md) for supported operation and rollback. No global originality, award eligibility, production reliability or realized-savings claim is established by this assessment.

See [product acceptance](product-acceptance.md) for delivery coverage and [BigQuery acceptance](bigquery-acceptance.md) for the final manual UI validation.

The measured [local demo](local-demo.md) and [deployment validation](deployment-validation.md) provide concrete end-user evidence. Independent acceptance requirements above remain distinct from software implementation.

## Review handoff

Use the [independent review pack](review-pack.md), [client identity/network acceptance procedure](client-validation.md) and [private sign-off template](review-record.md). The owner has authorized source publication; independent deployment acceptance remains unverified. No publication or production approval is implied by a passing local validator.

## Private alpha 0.1.0a2

See the [release notes and acceptance handoff](releases/0.1.0a2.md). This tag identifies a tested source revision for private evaluation. It is not public distribution or production certification.

## Dependency license assessment

The [technical dependency-license review](dependency-licenses.md) covers 39 locked optional runtime dependencies and their included license files. It does not close the independent ownership or publication gates.
