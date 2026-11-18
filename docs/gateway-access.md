# Client identity through an existing OIDC gateway

DataVouch delegates sign-in to the client's existing OIDC gateway. The gateway validates the identity-provider session; DataVouch authorizes an explicit subject against locally configured roles and connection scopes. DataVouch does not issue tokens or accept browser-supplied identity claims directly.

## Trust boundary

Deploy the gateway behind HTTPS. Keep the DataVouch backend reachable only from that gateway on a private network. The gateway must validate the expected issuer, audience and session, remove incoming identity and gateway-token headers, and replace them with:

| Header | Trusted value |
| --- | --- |
| `X-Auth-Request-User` | Verified stable subject, explicitly mapped in the policy |
| `X-DataVouch-Gateway-Token` | Random backend secret injected by the gateway |
| `Host` | Exact application host configured in `allowed_hosts` |

Use the identity provider's stable subject, not a mutable display name. Confirm your gateway's user header mapping; do not assume it contains the OIDC `sub`. Never expose the backend secret in browser responses or client-side code. Strip duplicate header values. Authentication fails if the token, subject, actual peer address or host is invalid. Forwarded IP headers cannot establish gateway trust.

The [OAuth2 Proxy configuration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/) and [NGINX integration](https://oauth2-proxy.github.io/oauth2-proxy/configuration/integrations/nginx/) describe authenticated response-header forwarding. The client must configure the verified-subject mapping and secret injection in its chosen gateway. Reverse proxies must sanitize security headers as described in [OAuth security best current practice](https://www.rfc-editor.org/rfc/rfc9700.html). These requirements apply regardless of identity provider.

## Configure DataVouch

Copy [the example policy](../examples/web/gateway-policy.json) to a private configuration directory. Replace every example value. List only the gateway's actual peer IP/CIDR, exact public host, approved stable subjects and connection IDs from your connections file. A connection scopes a configured project/location pair; it does not limit access within that connection to individual workloads.

```sh
mkdir -p "$HOME/.config/datavouch" "$HOME/.local/share/datavouch/runs"
chmod 700 "$HOME/.config/datavouch" "$HOME/.local/share/datavouch/runs"
python -c 'import secrets; from pathlib import Path; p=Path.home()/".config/datavouch/gateway-secret"; p.write_text(secrets.token_urlsafe(48)); p.chmod(0o600)'
cp examples/web/gateway-policy.json "$HOME/.config/datavouch/gateway-policy.json"
```

Edit the policy and prepare connections using [connection setup](connections.md). Provide the same secret to your gateway through its secret manager. Then start one backend process:

```sh
datavouch serve examples/web/empty-catalog.json \
  --gateway-config "$HOME/.config/datavouch/gateway-policy.json" \
  --gateway-secret-file "$HOME/.config/datavouch/gateway-secret" \
  --connections "$HOME/.config/datavouch/connections.json" \
  --run-directory "$HOME/.local/share/datavouch/runs" \
  --enable-live-execution
```

The default binding is loopback, suitable for a gateway on the same host. A private container network requires `--bind-address 0.0.0.0` inside the container and firewall isolation. Do not expose that port publicly. Gateway mode disables Basic authentication and startup sample catalogs. Saved experiments are visible only through approved connections.

| Role | Permissions within approved connections |
| --- | --- |
| Viewer | History, measurements, summaries, financial summaries |
| Operator | Viewer permissions plus planning, execution and financial assessment |
| Admin | Operator permissions plus deletion and scoped audit export |

Raw downloads require a separate server opt-in and are unavailable to viewers. Policy roles and connections are reloaded per request, with authorization rechecked before collection starts. Changing trusted hosts or backend secrets requires restart. Revocation does not cancel a query already submitted. Forms use subject-bound anti-forgery tokens.

## Operations and acceptance

This deployment supports one process, one active experiment, up to 50 saved experiments, ten financial assessments per experiment and 100 explicit subjects. There is no distributed worker queue, automatic group synchronization, high availability or billing integration. These are bounded deployment limits, not an enterprise capacity guarantee.

Stop the service before backing up the complete private run directory. Use encrypted, access-controlled storage and test restoration. Admin deletion removes the experiment files but preserves a minimal audit event. `audit.jsonl` contains timestamps, opaque actor identifiers, connection IDs, run hashes and outcomes; it is not tamper-proof. Forward it to your controlled audit system if required. Maintain retention for backups and audit data separately under your organization's policy. Archive the audit log while stopped before it reaches 10 MB; operations fail closed at the limit.

Before team use, validate the real IdP login/logout and expired sessions, stripped forged headers, blocked direct backend access, each role, two disjoint connection scopes, revoked access, TLS, backup recovery and audit retention. Automated tests cover the application boundary; they do not certify a particular client's gateway configuration or regulatory compliance.
