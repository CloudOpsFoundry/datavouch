# Security

This experimental package has no security support guarantee. Do not include credentials, customer SQL or personal data in reports or issues. No cloud access is enabled by default.

Report suspected vulnerabilities privately to [security@sourabhsharma.com](mailto:security@sourabhsharma.com). Include the affected version, a description of the issue, and minimal reproduction steps using synthetic data. Do not post vulnerability details in public issues. Email forwarding and delivery have been confirmed by the maintainer. Confirm the response owner, backup and ongoing monitoring during release review.

The implemented scope includes the offline CLI, bounded BigQuery metadata collection, local viewer, optional execution workspace and existing-gateway access controls, with Compose and Helm deployment paths. Shared use still requires validation of the real identity and network boundary. Third-party adapters are trusted Python code, not sandboxed plugins. Raw reports and caller-supplied labels may contain sensitive metadata. See [the security assessment](docs/release-readiness.md#security-assessment) and [deployment guidance](docs/deployment.md).

Local source scans, dependency audits and boundary tests do not constitute an independent security review. The repository remains private until independent reviews are complete. Follow the [review pack](docs/review-pack.md) and [client validation procedure](docs/client-validation.md); automated checks do not establish production readiness.
