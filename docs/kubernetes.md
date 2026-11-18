# Kubernetes deployment with Helm

The chart deploys DataVouch into a namespace you select. It contains no project, location, credentials, ingress hostname or identity-provider defaults. Use your registry, storage class, identity configuration and approved connections. The default is an empty authenticated workspace with cloud execution disabled.

## Deployment model

DataVouch currently has a single-process file-backed evidence store and one active collection worker. The chart enforces one replica and uses `Recreate`, avoiding two processes owning the same volume during an upgrade. It provides a ClusterIP service, private PVC, non-root containers, read-only root filesystems, dropped capabilities, resource limits, startup/readiness/liveness probes and a default-deny NetworkPolicy. It creates no Ingress or external load balancer.

These controls follow Kubernetes guidance on [deployment strategies](https://kubernetes.io/docs/concepts/workloads/controllers/deployment/), [volume security contexts](https://kubernetes.io/docs/tasks/configure-pod-container/security-context/) and [network policies](https://kubernetes.io/docs/concepts/services-networking/network-policies/). NetworkPolicy requires a supporting CNI; rendering or installing a policy does not prove traffic isolation. Helm uses a [values schema](https://helm.sh/docs/topics/charts/) to reject unsupported settings such as multiple replicas.

## Prerequisites

- A reviewed source revision, Docker, Helm 4.2.0, and kubectl within one minor version of your Kubernetes server.
- A namespace you may administer, sufficient capacity, and a storage class supporting POSIX permissions and SQLite file locking. Test the actual storage driver.
- A built image in the chosen cluster or your private registry. No public DataVouch image is assumed.
- A strong authentication secret supplied outside chart values. For shared access, an existing OIDC gateway, TLS and least-privilege workload identity.

The chart requires Kubernetes 1.30 or later. Local runtime validation does not establish compatibility with every distribution, architecture or storage driver.

## Install locally

Set an explicit context before every operation. These examples use shell variables, not a hard-coded cluster or cloud project:

```sh
export DATAVOUCH_CONTEXT='your-local-context'
export DATAVOUCH_NAMESPACE='datavouch-demo'
export DATAVOUCH_RELEASE='workspace'
export DATAVOUCH_CONFIG_DIR="$HOME/.config/datavouch"
mkdir -p "$DATAVOUCH_CONFIG_DIR"
chmod 700 "$DATAVOUCH_CONFIG_DIR"
```

Create a password only if one does not already exist:

```sh
python -c 'import os,secrets; from pathlib import Path; p=Path(os.environ["DATAVOUCH_CONFIG_DIR"])/"password"; f=p.open("x"); f.write(secrets.token_urlsafe(32)); f.close(); p.chmod(0o600)'
```

Build the product image and make it available to your cluster. Docker Desktop with a shared image store can use it directly. For kind, use `kind load docker-image datavouch-app:local --name YOUR_CLUSTER`; for a remote cluster, push a versioned image to your own registry and configure its immutable digest.

```sh
docker build -f deployment/container/Dockerfile -t datavouch-app:local .
kubectl --context "$DATAVOUCH_CONTEXT" create namespace "$DATAVOUCH_NAMESPACE"
kubectl --context "$DATAVOUCH_CONTEXT" -n "$DATAVOUCH_NAMESPACE" create secret generic datavouch-auth --from-file=password="$DATAVOUCH_CONFIG_DIR/password"
helm lint deployment/helm/datavouch --strict
helm upgrade --install "$DATAVOUCH_RELEASE" deployment/helm/datavouch \
  --kube-context "$DATAVOUCH_CONTEXT" --namespace "$DATAVOUCH_NAMESPACE" \
  -f deployment/helm/examples/local.yaml --wait --timeout 5m
kubectl --context "$DATAVOUCH_CONTEXT" -n "$DATAVOUCH_NAMESPACE" port-forward "service/$DATAVOUCH_RELEASE-datavouch" 8768:8765
```

Open `http://127.0.0.1:8768`, username `datavouch`, using the password file. The local values file shows illustrative examples and pulls no remote image. Port forwarding is local access; it does not validate gateway or CNI enforcement.

## Run the measured demo in Kubernetes

In another terminal with the same variables:

```sh
kubectl --context "$DATAVOUCH_CONTEXT" -n "$DATAVOUCH_NAMESPACE" exec "deployment/$DATAVOUCH_RELEASE-datavouch" -- python -m datavouch demo --output-dir /data/revenue-demo
helm upgrade "$DATAVOUCH_RELEASE" deployment/helm/datavouch \
  --kube-context "$DATAVOUCH_CONTEXT" --namespace "$DATAVOUCH_NAMESPACE" \
  -f deployment/helm/examples/local.yaml \
  --set config.catalogPath=/data/revenue-demo/catalog.json --wait --timeout 5m
```

Restart the port-forward after the pod changes. The UI now displays the measured local SQL results. The demo directory lives on the PVC; use a new directory for another run. Follow [the use-case guide](local-demo.md) to interpret the results. No cloud credentials are needed.

## Configure client-hosted team access

Keep customer-specific values in a private file outside this repository. See the complete [values reference](../deployment/helm/datavouch/values.yaml).

1. Set `image.repository` and `image.digest` to your reviewed image. Use `imagePullSecrets` when required.
2. Set `auth.mode: gateway` and `auth.existingSecret` to an existing Secret containing `gateway-secret`. Do not put secret values in Helm files or command-line `--set` arguments.
3. Set `config.gatewayPolicy` following [gateway access](gateway-access.md): exact allowed hosts, actual gateway peer CIDRs, verified stable subjects, roles and connection IDs. Configure the gateway to strip incoming authentication headers and inject verified identity and the backend secret.
4. Set `config.connections` to approved project/location pairs and collection limits. These are client-provided values. Set `execution.enabled: true` only after those scopes and credentials are reviewed.
5. Configure your platform's workload identity using `serviceAccount.annotations`, an existing service account, and `automountServiceAccountToken` only if required by that platform. No Kubernetes API permissions are granted by this chart. Alternatively, `credentials.existingSecret` mounts an existing ADC file; `credentials.quotaProject` is optional and client-defined.
6. Set `networkPolicy.ingress` to allow only the verified gateway on port 8765. Set `networkPolicy.egress` for DNS, identity endpoints and approved provider endpoints. Defaults deny both. Use the client's egress gateway for hostname-based restrictions; standard Kubernetes NetworkPolicy does not express domain names.
7. Put TLS and OIDC sign-in on the existing gateway. Route its private upstream to the ClusterIP service and preserve the configured application Host header. Do not expose Basic mode as a public service.
8. Install with `helm upgrade --install ... -f /private/client-values.yaml`. Validate real login/logout, revoked access, direct-access denial, cross-project isolation and actual network-policy enforcement before use.

Helm stores rendered ConfigMaps in release history. Connection IDs and subject mappings belong in the namespace's access-controlled configuration; passwords and ADC keys must remain in existing Secrets. Secret/config changes can require a rollout restart; backend secrets are loaded at startup. The chart hashes configuration to trigger configuration rollouts but deliberately does not read Secret contents.

## Storage, upgrades and recovery

A chart-created PVC is retained on Helm uninstall. **Deleting the namespace still deletes that PVC** and may delete its backing storage. Preserve reviewed backups before teardown. Use `persistence.existingClaim` to attach a retained or restored volume; Helm does not copy evidence to a replacement PVC.

Stop execution, wait for active collection to finish, scale the deployment to zero, and back up the complete data directory using the storage platform's approved mechanism. The application does not schedule backups or encrypt volumes. Restore onto a separate test volume and verify reports and audit history before relying on recovery. The non-root init container restores private mode `0700` on the run directory after volume group setup.

Use `helm history`, `helm upgrade --wait` and `helm rollback --wait` with explicit context/namespace. A rollback changes Kubernetes resources and images; it does not roll back evidence files or migrate their schema. Preserve compatible source, image and volume backups. There is a brief outage on replacement because the store has one owner; high availability is not implemented.

The 660-second termination grace period exceeds the maximum bounded worker deadline. Forced node termination can still interrupt collection, which is marked ERROR on recovery without automatic retry. TCP probes establish listener availability, not authentication or provider permissions. Review pod events/logs for failures; never print mounted secrets.

## Repeatable local cluster acceptance

After loading the built image, run:

```sh
python scripts/check_kubernetes.py --context "$DATAVOUCH_CONTEXT"
```

Use `--kubectl /path/to/compatible/kubectl` if your default client is outside the server's supported version skew. The script creates a uniquely named test namespace, tests install, demo, restart, gateway-header authorization, rollback and PVC retention on Helm uninstall, then deletes its own namespace and generated data. It does not change kubeconfig or inspect Secret values. Actual IdP login and CNI enforcement remain separate acceptance steps.
