# Security

This experimental package has no security support guarantee. Do not include credentials, customer SQL or personal data in reports or issues. No cloud access is enabled by default.

Report suspected vulnerabilities privately to [security@sourabhsharma.com](mailto:security@sourabhsharma.com). Include the affected version, a description of the issue, and minimal reproduction steps using synthetic data. Do not post vulnerability details in public issues. Email forwarding is configured; delivery and monitoring must be confirmed before public release.

Supported scope is the offline CLI and single-user loopback viewer. Third-party adapters are trusted Python code, not sandboxed plugins. Raw reports and caller-supplied labels may contain sensitive metadata. See [the security assessment](docs/release-readiness.md#security-assessment) and [deployment guidance](docs/deployment.md).

Local source scans, dependency audits and boundary tests do not constitute an independent security review. Public release remains blocked until a private reporting channel and responsible maintainers are confirmed.
