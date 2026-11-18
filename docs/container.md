# Application container

The product container is separate from local GitHub runner infrastructure. It installs the locked Python 3.15 environment, runs as a non-root user and contains no private evidence or credentials. Base images are pinned by digest. The default Compose service binds to localhost and starts a sample viewer with collection disabled.

From the repository root, with Docker running:

```sh
export DATAVOUCH_CONFIG_DIR="$HOME/.config/datavouch"
export DATAVOUCH_DATA_DIR="$HOME/.local/share/datavouch"
export DATAVOUCH_UID="$(id -u)"
export DATAVOUCH_GID="$(id -g)"
export DATAVOUCH_PORT=8787
mkdir -p "$DATAVOUCH_CONFIG_DIR" "$DATAVOUCH_DATA_DIR"
chmod 700 "$DATAVOUCH_CONFIG_DIR" "$DATAVOUCH_DATA_DIR"
python -c 'import secrets, os; from pathlib import Path; p=Path(os.environ["DATAVOUCH_CONFIG_DIR"])/"password"; p.write_text(secrets.token_urlsafe(32)); p.chmod(0o600)'
printf '{"connections": []}\n' > "$DATAVOUCH_CONFIG_DIR/connections.json"
docker compose -f deployment/container/compose.yaml up --build -d
cat "$DATAVOUCH_CONFIG_DIR/password"
```

Open `http://127.0.0.1:8787`, username `datavouch`, and use the displayed password. The setup commands initialize fresh configuration; preserve an existing password and connections file rather than overwriting them. Use the [connection guide](connections.md) to configure approved projects. No credentials are mounted and no cloud requests run in this default setup.

```sh
docker compose -f deployment/container/compose.yaml ps
docker compose -f deployment/container/compose.yaml logs --tail 30
docker compose -f deployment/container/compose.yaml down
```

The image has a TCP liveness probe. It confirms the listener, not authenticated readiness or cloud permissions. Compose uses a read-only root filesystem, a bounded temporary filesystem, dropped capabilities, no privilege escalation, and CPU/memory/process limits. The private data directory remains writable.

For collection, supply backend credentials through your platform's workload identity or a read-only ADC secret mount, configure the approved quota project, and add `--run-directory /data/runs --enable-live-execution` to the service command. Do not bake credentials into an image or mount the Docker socket. Test least-privilege access and denied access before use. Container credentials are separate from a host's gcloud login.

For team access, replace password arguments with the gateway policy and secret-file arguments from [gateway access](gateway-access.md), and put the backend on the gateway's private network. Keep private secrets outside this repository. Rebuild after source or lockfile changes; run the acceptance checks against the exact rebuilt image before deploying it. Only the locally tested architecture is validated; publishing a multi-architecture image requires testing each target architecture.

After building, run the repeatable offline smoke check from the repository root:

```sh
python scripts/check_container.py datavouch-app:local
```

It creates a temporary restricted container on an automatically assigned localhost port, checks authentication and sample pages, verifies Python/non-root execution and absence of development tools, then removes its own container. It does not mount cloud credentials or submit cloud queries. Run it from a non-root host account.

## Execution and gateway configurations

The base file is an offline viewer. Use exactly one application-mode override:

| Override | Purpose |
| --- | --- |
| `compose.demo.yaml` | View the generated local SQL demo from `/data/demo` |
| `compose.live.yaml` | Enable bounded collection with local Basic authentication |
| `compose.gateway.yaml` | Enable bounded collection behind your existing OIDC gateway |
| `compose.adc.yaml` | Optional read-only ADC mount, combined with live or gateway mode |

For example, after preparing your own connections file and credentials:

```sh
docker compose -f deployment/container/compose.yaml -f deployment/container/compose.live.yaml up -d
```

Gateway mode additionally requires `/config/gateway-policy.json` and `/config/gateway-secret`, configured according to [gateway access](gateway-access.md). Determine the actual peer address seen through Docker networking; forwarding headers do not make an address trusted. The published port remains localhost-only for a gateway on the same host.

For an explicit local ADC mount, set `DATAVOUCH_ADC_FILE` to the absolute private ADC filename and `DATAVOUCH_QUOTA_PROJECT` to your approved quota project, then add `-f deployment/container/compose.adc.yaml`. No project or location is supplied by the product. Prefer platform workload identity for managed deployments.

Set `DATAVOUCH_IMAGE` to use your own reviewed registry image and run `up --no-build`. The default `datavouch-app:local` is built from this checkout; it is not an assumed public image. All overrides keep the base runtime restrictions and private writable data mount. Live modes use a 660-second shutdown grace period for the bounded worker.

To verify the actual Compose configuration, including empty connection setup, authentication, real SQL execution and restart persistence:

```sh
python scripts/check_compose.py
```

The check creates and removes its own temporary containers, network and generated data. For Kubernetes, use [the Helm deployment guide](kubernetes.md).
