# Installation

Install from a trusted source checkout with `python -m pip install .` using Python 3.15. Use a virtual environment. The base package has no third party dependencies; web and BigQuery support are optional extras.

For development install uv, run `uv sync --locked --all-extras`, then `uv run python scripts/validate.py`. The lockfile records exact development dependencies. Refresh it deliberately with `uv lock --upgrade`, review the changes and run full validation.

The development default is pinned in `.python-version` to Python 3.15.2. Python 3.15 is required; other minor versions are not supported. Use `uv sync --locked --all-extras --python 3.15.2` to reproduce CI. Python 3.15.2 is documented in the [official release notes](https://www.python.org/downloads/release/python-3152/). Tool versions are resolved in `uv.lock`, including Ruff 0.17.5, mypy 2.4.1, pytest 9.2.0 and coverage 7.17.3. The environment was resolved using uv 0.13.9.

For authorized live BigQuery collection, install `python -m pip install ".[bigquery]"`. The optional SDK is locked at google-cloud-bigquery 3.47.0 for development. Core installation and offline fixture collection do not install or import Google libraries.
