# Development

Use `uv sync --locked --all-extras` and activate `.venv`. Run `python scripts/validate.py` for formatting, lint, typing, tests, coverage, security scans, package build and archive checks. Required failures are not skipped. Dependency auditing requires access to the public vulnerability service.

Run `python -m pytest` for focused tests. Install optional Git hooks with `python scripts/install_hooks.py`, adding `--with-push` for full push validation. Existing unmanaged hooks are preserved. Remove managed hooks with `python scripts/install_hooks.py --uninstall`. Reinstall after moving your virtual environment. Do not combine this installer with another hook manager.

Main and public pull requests use isolated GitHub hosted runners. The private feature workflow is manual and disabled unless `DATAVOUCH_TRUSTED_RUNNER` is set to `true` in a private repository. Register a runner with label `datavouch_local` using the [official instructions](https://docs.github.com/en/actions/hosting-your-own-runners/managing-self-hosted-runners/adding-self-hosted-runners). Only enable it when every repository writer and selected branch is trusted. Never run public contributor code on a personal runner. Do not store registration tokens. Runner availability and account quotas must be verified by the repository administrator.

The credential pattern check detects selected private key and access key formats. It is not an exhaustive secret audit. Bandit inspects runtime source. pip-audit checks installed third party dependencies and explicitly skips the editable DataVouch package, which has no runtime dependencies. Independent security review remains a release requirement.

See [performance methodology](performance.md) for the reproducible local benchmark.
