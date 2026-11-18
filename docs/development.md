# Development

Use Python 3.15.2 and `uv sync --locked --all-extras`. Run `uv run --no-sync python scripts/validate.py` for the same product validation used by CI. Required failures stop validation. Install actionlint 1.7.12 and Helm 4.2.0 for local workflow and deployment checks. Dependency auditing requires access to the vulnerability service.

Run `uv run --no-sync pytest` for focused tests. Optional hooks are installed with `python scripts/install_hooks.py`; `--with-push` enables full push validation and `--uninstall` removes managed hooks. Existing unmanaged hooks are preserved.

## Shared CI

The small [public caller workflow](../.github/workflows/public.yml) imports [CloudOpsFoundry/ci-templates](https://github.com/CloudOpsFoundry/ci-templates) at an exact reviewed commit. The template handles checkout, verified tools, the Python runtime and locked dependency installation. DataVouch supplies its Python version and validation command. Product tests and validation scripts stay here so contributors can run them locally.

Public pushes, pull requests and manual dispatch run on disposable hosted runners with read-only tokens and no cloud credentials. All validation runs in one environment, so dependencies are installed once. No packages, images or CI artifacts are uploaded. Main remains protected by `Public CI passed`; the small final gate rejects failed, cancelled or skipped shared validation. It does not repeat any tests.

## Visible CI stages

The shared workflow exposes tool setup, dependency installation, workflow syntax and project validation steps. Within project validation, expandable stage groups show formatting, lint, workflow checks, Helm contracts, typing, unit tests, adapter contracts, integration/regression tests, coverage, source security, dependency audit, package build, archive boundaries, clean installation, source/wheel parity and release metadata.

`python scripts/validate.py --stage NAME` runs an individual stage. Unit, contract and integration stages accumulate coverage in order. The full validator resets coverage before collecting results. Local test reports remain in ignored `.ci-artifacts/`; distribution checks build locally without publishing.

## Template updates

Templates are independent of DataVouch and do not contain its application code or tests. Updating the template repository does not change a pinned consumer. Change the caller SHA through a PR and require the full DataVouch pipeline before merging. The organization allowlist must allow that exact workflow revision. Keep the existing required check while testing migrations. Retired private runner workflows and their release helpers have been removed; local runner tooling remains ignored for optional private testing.

## Deployment and release checks

Helm lint, schema rejection, rendering/security contracts and packaging run in the validator. Linux validation downloads the pinned Helm archive and checks its digest. Real infrastructure checks are separate: `scripts/check_compose.py` validates local containers, while `scripts/check_kubernetes.py --context YOUR_CONTEXT` uses an explicitly approved cluster and its own temporary namespace. No cloud infrastructure is provisioned by CI.

Releases remain manual through protected PRs; see [release procedure](automated-releases.md). Static checks use Ruff, mypy and Bandit; pip-audit checks dependencies. These provide engineering evidence, not independent production certification. See [performance methodology](performance.md) and [client validation](client-validation.md).
