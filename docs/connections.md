# Deployment-owned BigQuery connections

The project dropdown lists connections approved by the deployment administrator. Each entry binds a project to a location and upper collection limits. This keeps the application generic while preventing a browser request from substituting an unapproved scope. The dropdown is an allowlist, not automatic Google Cloud discovery or evidence of cloud authorization.

## Local setup

1. Copy `examples/web/connections.json` to a private configuration directory outside the checkout.
2. Replace the example project, label and location with your own. Add one entry per approved project/location pair, with a unique ID. Set the maximum bytes and timeout your deployment permits.
3. Keep the configuration writable only by the deployment administrator. Do not include credentials in this file.
4. Start the UI, replacing the configuration path below with your actual path:

```sh
.venv/bin/python -m datavouch serve examples/viewer.json --port 8766 --connections /absolute/path/to/connections.json
```

5. Select **New experiment**, choose a project/location, and enter the remaining fields. The server revalidates the selected connection and limits for preview and download. Without a configuration, report review still works but plan creation is disabled. Restart after changing connections.

The bundled example is a configuration template; its project is not a live integration. No cloud calls occur at startup, when opening the dropdown, or when validating/downloading a plan. Selecting a connection neither grants IAM permissions nor changes credentials. Existing CLI commands continue to accept their own configurations and do not inherit this UI allowlist.

For optional local execution, follow [Run an experiment from the UI](ui-execution.md). The worker reloads this allowlist at submission and immediately before launching collection.

## Client-hosted architecture

The intended deployment keeps the application, evidence, credentials and execution workers within the client's controlled environment. These controls are requirements for future shared deployment, not capabilities already delivered by the local viewer:

- Use organization identity, roles and per-user/project authorization. Currently every authenticated local user shares the same allowlist; there is no tenant isolation.
- Use workload identity or an approved credential provider on the backend. Never ask the browser to submit service-account keys. Give execution workers only the permissions needed for the approved projects and job metadata.
- Continue enforcing scope and collection limits at execution time. The local worker now performs these checks; shared deployments also need per-user authorization. A downloaded plan can be edited, so plan-time validation is not an execution authorization boundary.
- Record who requested a run, selected scope, policy, execution status and evidence references. Exclude secrets and raw sensitive content from operational logs.
- Define data classification, access, retention, deletion, backups and regional storage for evidence. A BigQuery location selection alone does not establish residency or GDPR compliance. Labels and job identifiers can themselves be sensitive.
- Add TLS, secure sessions, access revocation, bounded background workers, concurrency limits and recovery before shared hosting.

Automatic project discovery can be added later as an explicit administrator action using the deployment identity. Its results must be intersected with the configured allowlist and user authorization, then refreshed on a bounded schedule. A project visible to an identity is not necessarily approved for DataVouch or usable for BigQuery execution. The current static configuration avoids adding discovery permissions or API calls to each page request.

Local authentication is the default. Shared deployments require the explicit controls in [OIDC gateway setup](gateway-access.md), including private backend networking, TLS, verified-subject mapping, role policies and real IdP acceptance.
