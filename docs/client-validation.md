# Validate a real client deployment

This is an acceptance procedure, not a record of completed client validation. A deployment owner must supply the real identity provider, gateway, HTTPS hostname, private backend topology, approved test identities and permitted cloud connections. Do not modify another environment to satisfy a test. The development test environment is not authorization to change client infrastructure.

Use synthetic evidence and dedicated test users. Keep screenshots, identity mappings, network addresses and results in the client's private evidence store. Never put tokens, cookies, secrets, customer SQL or raw reports in an issue. Record the exact source commit, image digest, chart version and configuration hash in [the review record](review-record.md).

## 1. Agree the deployment boundary

Before changing configuration, record:

- Application URL, expected OIDC issuer/audience, stable subject mapping, session duration, logout and revocation requirements.
- Gateway peer addresses as seen by DataVouch; allowed application hosts; where incoming identity headers are stripped and trusted replacements injected.
- Namespace/network ownership, CNI network-policy support, gateway ingress path, required DNS/BigQuery/identity egress and approved firewall policy.
- Viewer, operator and admin test identities, a disabled identity, and two disjoint connection scopes. A single cloud project can use two connection IDs for application-scope tests; that does not prove cloud IAM isolation.
- Backend credentials, quota project, least-privilege permissions, secret rotation owner, encrypted storage, retention and recovery objectives.

Prepare the [gateway policy](gateway-access.md), [connections](connections.md) and either [Compose](container.md) or [Helm](kubernetes.md). Use an empty connection allowlist until the owner approves live access. No public backend port, wildcard trusted proxy CIDR or browser-delivered gateway secret is acceptable.

## 2. Run application checks without cloud credentials

From a clean reviewed checkout with Python 3.15.2 and the documented developer prerequisites:

```sh
uv sync --locked --all-extras
uv run --no-sync python -m pytest tests/integration/test_product_workspace.py tests/integration/test_history_deletion.py tests/integration/test_web.py
```

These validate the application boundary with fixtures. They do not test your real identity provider, TLS or CNI. Run the full validator before approving the artifact.

## 3. Validate real identity and browser behavior

Use separate browser profiles for each identity. Record actual outcomes, timestamps and evidence references for every row. Missing access to perform a test is **NOT RUN**, never PASS.

| ID | Action in the approved deployment | Required observation |
| --- | --- | --- |
| AUTH-01 | Open the application without a session | Redirect to the approved sign-in flow or deny access; no report data |
| AUTH-02 | Sign in as viewer/operator/admin | The expected stable identity, role and approved connections are applied |
| AUTH-03 | Use a disabled or unmapped identity | Access denied even if the IdP login succeeds |
| AUTH-04 | Log out, expire the session, then revisit a protected page | Gateway requires fresh authentication; no access from cached credentials |
| AUTH-05 | Revoke application access while a session exists | Subsequent protected requests fail; an already-submitted query may finish |
| AUTH-06 | Try viewer planning, collection, financial writes and deletion URLs | Read-only access remains enforced server-side |
| AUTH-07 | Compare two disjoint subjects and directly request the other run URL/download/audit scope | No other connection's evidence or existence details are exposed |
| AUTH-08 | Send forged or duplicate identity/token headers through the public gateway | Headers are stripped/replaced; cannot impersonate another subject |
| AUTH-09 | Use wrong issuer/audience or an expired token in an authorized gateway test | Gateway rejects it before the application; do not send tokens in shared logs |
| AUTH-10 | Rotate the backend shared secret and restart the backend and gateway coherently | Old secret rejected; new secret works; secret absent from browser/network responses |
| UI-01 | Validate a synthetic plan in a real browser | Success with same-origin form POST; no cloud collection |
| UI-02 | Delete a disposable individual run and then selected/all disposable history | Confirmation, successful removal, unrelated records retained |
| UI-03 | Submit from another origin or without the subject-bound form token | Rejected without a state change |

Application Basic authentication is for local use; it does not supply team logout or session revocation. Gateway mode disables that fallback. The gateway must preserve the application's security headers, including `Referrer-Policy: same-origin`; replacing it with `no-referrer` breaks HTML form Origin checks.

## 4. Validate the network boundary

An authorized operator can check the HTTPS endpoint without printing cookies or redirect parameters:

```sh
export DATAVOUCH_URL='https://REPLACE_WITH_APPROVED_HOST'
curl --silent --show-error --output /dev/null --write-out '%{http_code}\n' --max-time 15 "$DATAVOUCH_URL/runs"
```

Do not use `--insecure`. A 200 from a gateway login page is not automatically a failure or a pass: inspect the browser journey to confirm that no application data is exposed. A redirect alone does not prove secure authentication.

| ID | Test | Required observation |
| --- | --- | --- |
| NET-01 | Check certificate chain, hostname and HTTPS enforcement from the user's network | Valid TLS and approved redirect policy; no plaintext credential transmission |
| NET-02 | Attempt backend access from outside the gateway network and an unauthorized pod/host | Connection denied; backend is not publicly exposed |
| NET-03 | Access through the approved gateway path | Authenticated requests succeed; actual peer is in the narrow configured range |
| NET-04 | Send spoofed forwarded-IP headers from an untrusted peer | No gateway trust is granted |
| NET-05 | Test denied ingress/egress using the actual deployed CNI and approved test pod | Forbidden paths blocked; required DNS and approved service paths work |
| NET-06 | Review service endpoints, ingress routes and runtime mounts | No alternate unprotected route, Docker socket or unrelated credentials |

Port forwarding bypasses parts of this topology. Do not use a port-forward success or rendered NetworkPolicy manifest as proof of network isolation. Never apply cluster-wide policies or use another namespace without its owner's approval.

## 5. Validate recovery and the workload

Stop new work, wait for collection to finish and stop the single store owner. Back up the complete private data directory using the approved encrypted mechanism. Restore to a separate test volume, start one owner, and compare report/financial/audit hashes and permissions. Verify deletion remains deleted after restart. Restore tests need the actual storage platform; the local file-copy test only establishes local application recovery.

Run the [synthetic BigQuery walkthrough](bigquery-acceptance.md) in an explicitly approved project. Obtain explicit authorization for the test project; do not change another project's resources, IAM, APIs or billing. Client connection examples and deployment defaults remain generic. Record the correct and deliberately incorrect outputs, missing-evidence outcome, collection overhead and actual policy reasons. Do not increase permissions or thresholds just to produce PASS.

## Exit criteria

All required rows need observed outcomes, private evidence references and a named deployment owner. Resolve security failures before shared use. Record approved residual limitations, recovery objectives and the next revalidation date. Changes to gateway, IdP, CNI, image or policy invalidate the affected acceptance results. Link the signed result from [the independent review pack](review-pack.md); this document alone is not a certification.
