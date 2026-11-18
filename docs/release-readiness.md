# Release-readiness assessment

DataVouch remains **experimental, unpublished, and not production ready**. The version is `0.1.0a1`. Local engineering checks are distinct from approval to publish or deploy.

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
| Versioning/changelog | Alpha version retained, Unreleased section, package/artifact consistency checks | Implemented |
| Licensing | MIT file present in source and distributions; dependency license metadata inventoried | Ownership and compatibility approval pending |
| Source publication | Private CloudOpsFoundry/datavouch repository; exclusion checks and artifact hashes; no published release | Private development; public release requires owner approval |
| GitHub Actions | Pinned actions, read-only permissions, self-hosted push/PR/main validation | Merged main validation passed; each new revision requires checks |
| External users | Scripted contributor acceptance exercise below | Independent participation pending |
| Deployment | Local workspace, opt-in execution, application container, OIDC gateway roles/scopes | Real IdP and client infrastructure acceptance pending |

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
| BigQuery | Explicit live mode, project/location scope, selected job IDs, parameterized reads, byte/time bounds, lazy credentials | Metadata queries can cost money; denied-access behavior tested with mocks; synthetic failed-job validation completed in the sandbox; no production workload certification |
| Local viewer | Loopback binding, password authentication, Host allowlist, cross-site checks, CSP, no-store, escaped templates, bounded startup snapshot | HTTP Basic has no application logout/session revocation; local machine/browser must be trusted; no public deployment assessment |
| Evidence display | Allowlisted viewer/workflow summaries and opt-in raw viewer downloads | Labels can contain sensitive text; CLI collection/raw reports include execution metadata |
| Adapter extension | Explicit registration, version/mode/metric checks, immutable result contracts, generic errors | Adapter Python code is trusted and not sandboxed; claims and side effects cannot be independently enforced |
| CI | Isolated self-hosted jobs, read-only permissions, pinned action commits, checkout credential persistence disabled, no cloud secrets | Repository writers can alter policies/workflows; branch protection and trusted evidence production must be configured |
| Releases | Private-context exclusions, artifact metadata/content checks and hashes | Pattern-based secret scan is incomplete; independent source/security review and review are required; security@sourabhsharma.com is the configured reporting channel |

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

The destination is CloudOpsFoundry/datavouch, the selected source license is MIT, and the confirmed private reporting address is security@sourabhsharma.com. Before publication, obtain ownership/dependency-license approval and confirm release maintainers. Review the GitHub Free private-repository protection limitations and establish enforceable protections for public release. The current self-hosted workflow is intentionally restricted to trusted private-repository pushes and must be replaced or adapted for an isolated public-contribution trust model before visibility changes. Run the actual workflows, including failing and blocked-UNKNOWN fixtures. Obtain independent security and user-testing results and resolve material findings.

For each release, update `pyproject.toml` and `src/datavouch/__init__.py` together, move reviewed changes from Unreleased into the versioned changelog, and state report/API compatibility changes and known limitations. Regenerate the lockfile only when dependencies deliberately change. Validate the final source revision, rebuild artifacts, retain their hashes and test installation from those artifacts. Publish only the reviewed artifacts after explicit authorization. No automated publishing or release credentials are configured in this project.

See [deployment guidance](deployment.md) for supported operation and rollback. No global originality, award eligibility, production reliability or realized-savings claim is established by this assessment.

See [product acceptance](product-acceptance.md) for delivery coverage and [sandbox acceptance](sandbox-acceptance.md) for the final manual UI validation.
