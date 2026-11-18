# Release-readiness assessment

DataVouch remains **experimental, unpublished, and not production ready**. The version is `0.1.0a1`. Local engineering checks are distinct from approval to publish or deploy.

## Assessment matrix

| Area | Evidence or action | State |
| --- | --- | --- |
| Dependencies | Core has no dependencies; optional SDK/web dependencies locked; installed environment vulnerability audit | Locally tested; inventory available |
| Security | Automated source scan, tested input/authentication boundaries, documented threat assessment | Local assessment; independent review pending |
| Installation | Clean wheel CLI and external adapter replay; prior isolated web-wheel HTTP test | Locally tested |
| Packaging | Wheel/source metadata, version consistency, LICENSE, typing marker, private-file exclusions; source rebuild compared with wheel | Automated local checks |
| Python compatibility | Full suite on Python 3.12.14 and 3.15.2, macOS | Tested endpoints; other interpreter/OS combinations unverified |
| Benchmarks | Reproducible synthetic comparison benchmark on both interpreters | Measured; no service-level guarantee |
| Documentation | Setup, CLI, policy, adapter, web and deployment guides | Locally reviewed; external onboarding pending |
| Versioning/changelog | Alpha version retained, Unreleased section, package/artifact consistency checks | Implemented |
| Licensing | MIT file present in source and distributions; dependency license metadata inventoried | Ownership and compatibility approval pending |
| Source publication | Exclusion checks and artifact hashes; no configured remote or published release | Blocked pending repository/owner decisions |
| GitHub Actions | Pinned actions, read-only permissions, local workflow lint/replay | Actual remote execution pending |
| External users | Scripted contributor acceptance exercise below | Independent participation pending |
| Deployment | Single-user local viewer and offline CLI only | Public/multi-user deployment unsupported |

## Repeatable local evidence

```sh
uv sync --locked --all-extras
uv run --no-sync python scripts/validate.py
uv run --no-sync python scripts/benchmark.py
uv run --no-sync python scripts/check_release.py > /tmp/datavouch-release-inventory.json
```

The validator stops at the first failure. It checks formatting, lint, types, tests/coverage, source and dependency security scans, builds, archive boundaries, clean installation, source-archive rebuild and release metadata. `check_release.py` emits artifact hashes and a bounded inventory of the installed validation environment, including development tools. It is not a complete SBOM, license opinion, or approval gate. A successful exit means local checks passed; it does not clear external readiness requirements. Inventory hashes change when artifacts are rebuilt; retain the report with the exact artifacts reviewed.

The standard build command already builds a wheel via its source archive. `check_sdist.py` adds an explicit direct-checkout wheel build and a separate source-archive rebuild using installed build dependencies, then compares every wheel member. This proves archive completeness under the tested toolchain; it does not establish reproducibility across all platforms or dependency versions.

## Security assessment

| Boundary | Implemented controls | Remaining limits |
| --- | --- | --- |
| Offline JSON | Size limits, duplicate-key rejection, strict schemas, finite numeric validation, explicit missing evidence | Inputs and attestations are not authenticated |
| BigQuery | Explicit live mode, project/location scope, selected job IDs, parameterized reads, byte/time bounds, lazy credentials | Metadata queries can cost money; denied-access behavior tested with mocks; no production workload certification |
| Local viewer | Loopback binding, password authentication, Host allowlist, cross-site checks, CSP, no-store, escaped templates, bounded startup snapshot | HTTP Basic has no application logout/session revocation; local machine/browser must be trusted; no public deployment assessment |
| Evidence display | Allowlisted viewer/workflow summaries and opt-in raw viewer downloads | Labels can contain sensitive text; CLI collection/raw reports include execution metadata |
| Adapter extension | Explicit registration, version/mode/metric checks, immutable result contracts, generic errors | Adapter Python code is trusted and not sandboxed; claims and side effects cannot be independently enforced |
| CI | Hosted PR jobs, read-only permissions, pinned action commits, checkout credential persistence disabled, no cloud secrets | Repository writers can alter policies/workflows; branch protection and trusted evidence production must be configured |
| Releases | Private-context exclusions, artifact metadata/content checks and hashes | Pattern-based secret scan is incomplete; independent source/security review and private reporting channel are required |

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

Before public publication, the owner must confirm the destination repository, ownership/license decision, private vulnerability-reporting channel and release maintainers. Establish branch protection and run the actual GitHub workflows, including a deliberately failing and a blocked-UNKNOWN fixture. Obtain independent security and user-testing results and resolve material findings.

For each release, update `pyproject.toml` and `src/datavouch/__init__.py` together, move reviewed changes from Unreleased into the versioned changelog, and state report/API compatibility changes and known limitations. Regenerate the lockfile only when dependencies deliberately change. Validate the final source revision, rebuild artifacts, retain their hashes and test installation from those artifacts. Publish only the reviewed artifacts after explicit authorization. No automated publishing or release credentials are configured in this project.

See [deployment guidance](deployment.md) for supported operation and rollback. No global originality, award eligibility, production reliability or realized-savings claim is established by this assessment.
