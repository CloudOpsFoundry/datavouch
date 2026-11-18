"""Run isolated Helm acceptance in an explicitly selected cluster, then remove test resources.

Requires the built datavouch-app:local image in that cluster, Helm and compatible kubectl.
Creates its own namespace; does not change kubeconfig or existing workloads.
"""

import argparse
import base64
import json
import secrets
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deployment/helm/datavouch"
LOCAL = ROOT / "deployment/helm/examples/local.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--context", required=True)
    parser.add_argument("--kubectl", default="kubectl")
    args = parser.parse_args()
    namespace = "datavouch-acceptance-" + secrets.token_hex(4)
    kube = [args.kubectl, "--context", args.context, "-n", namespace]
    helm = ["helm", "--kube-context", args.context, "--namespace", namespace]
    name = "acceptance-datavouch"
    created = False
    forward = None
    with tempfile.TemporaryDirectory(prefix="datavouch-kubernetes-") as temporary:
        folder = Path(temporary)
        password = secrets.token_urlsafe(32)
        backend_secret = secrets.token_urlsafe(48)
        (folder / "password").write_text(password)
        (folder / "gateway-secret").write_text(backend_secret)
        for secret_file in folder.iterdir():
            secret_file.chmod(0o600)

        def run(command: list[str]) -> str:
            return subprocess.check_output(command, text=True, stderr=subprocess.PIPE)

        def connect() -> str:
            nonlocal forward
            if forward:
                forward.terminate()
                forward.wait(timeout=10)
            with socket.socket() as listener:
                listener.bind(("127.0.0.1", 0))
                port = listener.getsockname()[1]
            forward = subprocess.Popen(
                kube + ["port-forward", "service/" + name, f"{port}:8765"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            base = f"http://127.0.0.1:{port}"
            for _attempt in range(100):
                try:
                    urllib.request.urlopen(base, timeout=1)
                except urllib.error.HTTPError:
                    return base
                except urllib.error.URLError, ConnectionError:
                    time.sleep(0.2)
            raise AssertionError("Port-forward did not become ready")

        def request(
            base: str, path: str = "/", *, gateway: str = "", anonymous: bool = False
        ) -> tuple[int, bytes]:
            headers = {}
            if gateway:
                headers = {
                    "X-DataVouch-Gateway-Token": gateway,
                    "X-Auth-Request-User": "acceptance-viewer",
                }
            elif not anonymous:
                token = base64.b64encode(f"datavouch:{password}".encode()).decode()
                headers = {"Authorization": "Basic " + token}
            try:
                with urllib.request.urlopen(
                    urllib.request.Request(base + path, headers=headers), timeout=5
                ) as response:
                    return response.status, response.read()
            except urllib.error.HTTPError as error:
                return error.code, error.read()

        try:
            run(kube + ["create", "namespace", namespace])
            created = True
            run(
                kube
                + ["label", "namespace", namespace, "pod-security.kubernetes.io/enforce=restricted"]
            )
            run(
                kube
                + [
                    "create",
                    "secret",
                    "generic",
                    "datavouch-auth",
                    "--from-file=password=" + str(folder / "password"),
                    "--from-file=gateway-secret=" + str(folder / "gateway-secret"),
                ]
            )
            run(
                helm
                + [
                    "install",
                    "acceptance",
                    str(CHART),
                    "-f",
                    str(LOCAL),
                    "--wait",
                    "--timeout",
                    "3m",
                ]
            )
            base = connect()
            assert request(base, anonymous=True)[0] == 401
            assert request(base)[0] == 200
            demo = json.loads(
                run(
                    kube
                    + [
                        "exec",
                        "deployment/" + name,
                        "--",
                        "python",
                        "-m",
                        "datavouch",
                        "demo",
                        "--output-dir",
                        "/data/aggregation-demo",
                    ]
                )
            )
            assert demo["results"][1]["status"] == "FAIL"
            run(
                helm
                + [
                    "upgrade",
                    "acceptance",
                    str(CHART),
                    "-f",
                    str(LOCAL),
                    "--set",
                    "config.catalogPath=/data/aggregation-demo/catalog.json",
                    "--set",
                    "execution.allowRawReports=true",
                    "--wait",
                    "--timeout",
                    "3m",
                ]
            )
            base = connect()
            url = "/workloads/weighted-aggregation/experiments/incorrect/report.json"
            code, original = request(base, url)
            assert code == 200 and json.loads(original)["overall_status"] == "FAIL"
            assert "Weighted aggregation" in request(base, "/workloads")[1].decode()
            run(kube + ["rollout", "restart", "deployment/" + name])
            run(kube + ["rollout", "status", "deployment/" + name, "--timeout=180s"])
            base = connect()
            assert request(base, url) == (200, original)
            run(
                kube
                + [
                    "exec",
                    "deployment/" + name,
                    "--",
                    "python",
                    "-c",
                    "import os;from pathlib import Path;assert os.getuid()==10001;"
                    "assert Path('/data/runs').stat().st_mode&0o777==0o700",
                ]
            )
            gateway_values = folder / "gateway.json"
            gateway_values.write_text(
                json.dumps(
                    {
                        "auth": {"mode": "gateway"},
                        "config": {
                            "gatewayPolicy": {
                                "allowed_hosts": ["127.0.0.1"],
                                "trusted_proxy_networks": ["127.0.0.1/32"],
                                "principals": {
                                    "acceptance-viewer": {"role": "viewer", "connections": []}
                                },
                            }
                        },
                    }
                )
            )
            run(
                helm
                + [
                    "upgrade",
                    "acceptance",
                    str(CHART),
                    "-f",
                    str(LOCAL),
                    "-f",
                    str(gateway_values),
                    "--wait",
                    "--timeout",
                    "3m",
                ]
            )
            base = connect()
            assert request(base)[0] == 403
            assert request(base, gateway="forged")[0] == 403
            assert request(base, gateway=backend_secret)[0] == 200
            assert request(base, "/experiments/new", gateway=backend_secret)[0] == 403
            run(helm + ["rollback", "acceptance", "2", "--wait", "--timeout", "3m"])
            base = connect()
            assert request(base, url) == (200, original)
            run(helm + ["uninstall", "acceptance", "--wait", "--timeout", "3m"])
            pvc = json.loads(run(kube + ["get", "pvc", name, "-o", "json"]))
            assert pvc["status"]["phase"] == "Bound"
            print(
                json.dumps(
                    {
                        "kubernetes": "PASS",
                        "context": args.context,
                        "namespace": namespace,
                        "restart_and_rollback_persistence": "PASS",
                        "gateway_header_boundary": "PASS",
                        "pvc_retained_on_uninstall": "PASS",
                        "measured_demo": demo,
                        "limits": [
                            "No real OIDC login or cloud access",
                            "Port-forward does not validate CNI network-policy enforcement",
                        ],
                    },
                    indent=2,
                )
            )
        finally:
            if forward:
                forward.terminate()
                forward.wait(timeout=10)
            if created:
                # This namespace and its generated evidence were created only by this test.
                run(kube + ["delete", "namespace", namespace, "--wait=true", "--timeout=180s"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
