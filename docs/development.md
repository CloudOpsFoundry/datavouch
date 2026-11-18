# Development

Use `uv sync --locked --all-extras` and activate `.venv`. Run `python scripts/validate.py` for formatting, lint, typing, tests, coverage, security scans, package build and archive checks. Required failures are not skipped. Dependency auditing requires access to the public vulnerability service.

Run `python -m pytest` for focused tests. Install optional Git hooks with `python scripts/install_hooks.py`, adding `--with-push` for full push validation. Existing unmanaged hooks are preserved. Remove managed hooks with `python scripts/install_hooks.py --uninstall`. Reinstall after moving your virtual environment. Do not combine this installer with another hook manager.

CI runs on a separately managed self-hosted Linux runner with the `datavouch_local` label. The runner must provide Python 3.15.2, uv and actionlint. Runner images and management scripts are maintained outside this repository. Workflows require a private repository, `DATAVOUCH_TRUSTED_RUNNER=true` and the actor configured in `DATAVOUCH_TRUSTED_ACTOR`. Pushes to every branch containing these workflows are validated, along with pull requests targeting main. Fork pull requests are excluded. Main and new feature branches inherit this configuration after merge; existing branches must incorporate the workflow changes.

The validation script accepts `--stage` for named CI steps and runs every stage by default. Unit, contract and integration stages accumulate coverage in order. Run them in a clean checkout or run the full validator to reset coverage before collecting results. Actionlint 1.7.12 must be on PATH for workflow checks. Test and coverage XML is written to ignored `.ci-artifacts/`.

The credential pattern check detects selected private key and access key formats. It is not an exhaustive secret audit. Bandit inspects runtime source. pip-audit checks installed third party dependencies and explicitly skips the editable DataVouch package, which has no runtime dependencies. Independent security review remains a release requirement.

See [performance methodology](performance.md) for the reproducible local benchmark.
