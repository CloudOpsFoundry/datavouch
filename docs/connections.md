# Google Cloud connections and live discovery

DataVouch supports explicit project/location connections and optional live discovery. There are no built-in client project IDs or locations. The deployment administrator controls scope; the backend Google Cloud identity and each user's access policy further restrict what is usable.

## Enable live discovery

1. Install DataVouch with its `web` and `bigquery` extras, or use the provided Docker image.
2. Copy [the discovery configuration](../examples/web/discovery.json) to a private configuration directory outside the checkout. Replace `client-quota` and `client-analytics` with your approved projects. The quota project accounts for API usage; it is not an execution-project default.
3. Configure backend Application Default Credentials (ADC), as described below. Never put credentials in the connections file or browser.
4. Start the server with `--connections /absolute/path/to/connections.json`. Docker Compose mounts the same file; Helm accepts the discovery object under `config.discovery` in your private values file.
5. Open **New experiment**, select a **Google Cloud project**, and select **Load locations**. Choose the discovered project/location pair, then fill out the experiment. **Refresh cloud metadata** explicitly refreshes discovery. Loading or refreshing starts a new form, so choose the project first.

```json
{
  "connections": [],
  "discovery": {
    "quota_project": "client-quota",
    "allowed_projects": ["client-analytics"],
    "allowed_locations": ["*"],
    "maximum_bytes_billed": 100000000,
    "timeout_seconds": 60
  }
}
```

`allowed_projects` and `allowed_locations` accept explicit names or a single `"*"`. An explicit project list is recommended for controlled deployments. A wildcard permits discovery within the backend identity's access; it does not grant IAM access. Locations use lowercase names, including `eu`, `us` and regional names. Collection limits apply to each metadata query, not to workload execution or monetary cost.

Project discovery uses BigQuery's `projects.list`: results depend on the backend identity's project access and enabled BigQuery API. Location discovery reads locations from visible datasets and recent jobs in the selected project. It does not enumerate every possible BigQuery region, execute SQL, inspect table rows, or fetch query text/user email. Projects without visible datasets or jobs may have no discovered location. Configure an explicit connection in that case.

Each endpoint is limited to three pages, 64 KiB per response and a 25-second metadata-fetch budget with five-second request timeouts. A warning identifies truncated or unreachable results. Metadata is cached for up to 60 seconds, with explicit refresh limited to once every five seconds. Failed refreshes do not serve expired results. Discovery is a bounded current view, not a complete inventory or continuous real-time subscription.

## Production authentication and permissions

On Compute Engine, attach a dedicated service account to the private VM and let ADC obtain short-lived credentials from the metadata service. Use the `cloud-platform` OAuth scope and restrict access with IAM. On GKE, use Workload Identity Federation for GKE. Outside Google Cloud, use Workload Identity Federation with the client's approved identity provider. Do not distribute service-account JSON keys. See Google's [attached service account guidance](https://docs.cloud.google.com/docs/authentication/set-up-adc-attached-service-account) and [Workload Identity Federation](https://docs.cloud.google.com/iam/docs/workload-identity-federation).

Permissions serve different purposes:

| Operation | Access required |
| --- | --- |
| List projects | Project visibility for the backend identity and BigQuery API enabled; see [projects.list](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/projects/list) |
| Discover dataset locations | `bigquery.datasets.get` on relevant datasets; inaccessible datasets are filtered from [datasets.list](https://docs.cloud.google.com/bigquery/docs/reference/rest/v2/datasets/list) |
| Discover recent job locations | `bigquery.jobs.listAll` for project-wide job metadata; included in BigQuery Resource Viewer |
| Collect selected job evidence | BigQuery Job User and BigQuery Resource Viewer on approved execution projects; see [collection setup](bigquery.md) |
| Charge API quota to the configured quota project | `serviceusage.services.use` on that quota project, where required by the API/credential flow |

Use a custom least-privilege role or appropriately scoped predefined roles according to the client's IAM policy. Discovery does not require table-data read access. An empty or partial inventory is not proof that resources do not exist. Actual collection still checks Google Cloud authorization; selection alone never proves execution access.

For local development, use `gcloud auth application-default login` and `gcloud auth application-default set-quota-project YOUR_QUOTA_PROJECT`. An interactive `gcloud auth login` session alone does not configure Python ADC. Production containers should use workload credentials instead of personal developer credentials.

The web user's OIDC gateway identity is separate from the backend Google Cloud identity. In gateway policy, allow discovered connections explicitly as `gcp:PROJECT_ID:LOCATION`, for example `gcp:client-analytics:eu`. No wildcard is supported in user connection lists. Projects and locations are intersected with those exact connection IDs. The application rechecks current deployment and user policy at submission and before collection. Cached metadata can lag IAM changes for up to 60 seconds; Google Cloud still enforces current IAM on API requests. Revocation does not cancel an already submitted query.

## Explicit connections and offline planning

Copy [the explicit configuration](../examples/web/connections.json), replace its example values, and provide one entry per approved project/location pair. Existing configurations remain valid without `discovery`. Static IDs must not begin with `gcp:`, which is reserved for discovered connections. Static and discovered connections can coexist; a visible explicit connection takes precedence for the same project/location pair.

With discovery disabled, opening the form and validating/downloading a plan make no cloud calls. With discovery enabled, those actions may read metadata to resolve the scope, but only an explicitly confirmed **Run experiment** executes collection SQL. Both modes validate the same limits and CLI plan semantics. A downloaded plan can be edited; the UI's policy is not an authorization boundary for separate CLI use.

Keep configuration administrator-owned. Policy is reread for authorization; restart after changing static choices so the form displays the new list. Run history and evidence remain in the client's environment. Location choice alone does not establish GDPR compliance or evidence-storage residency. Shared deployments require the [OIDC gateway controls](gateway-access.md), private networking and client acceptance tests. See [UI execution](ui-execution.md) for collection and retention behavior.
