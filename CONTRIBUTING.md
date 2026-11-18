# Contributing

Use a feature branch and synthetic fixtures. Keep cloud integration code separate from deterministic analysis. Add tests for behaviour and failure cases. Run `python scripts/validate.py` in the development environment before submitting changes. See [development](docs/development.md).

For first-time onboarding, install with `uv sync --locked --all-extras`, run the synthetic verification examples, then run the full validator. Adapter contributors should start with [the external fixture example and contract template](docs/adapters.md). Policy and report changes need explicit compatibility review and independently specified expected values.

Describe the concrete behavior change, tests and limitations in each pull request. Add user-visible changes under **Unreleased** in CHANGELOG.md. Do not publish private evidence or `.local_context`. See [release readiness](docs/release-readiness.md) for independent acceptance exercises and release gates. Follow SECURITY.md for vulnerabilities rather than filing public details.
