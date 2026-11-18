"""Lint and render Helm deployment contracts; install a verified CI-only Helm if needed."""

import hashlib
import io
import json
import platform
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CHART = ROOT / "deployment/helm/datavouch"
VERSION = "v4.2.0"
DIGESTS = {
    "arm64": "1f8de130dfbd04de64978e7b852a7a547be1404956a366608276d2520b678670",
    "amd64": "97dbeb971be4ac4b27e3839976d9564c0fb35c6f3b1da89dd1e292d236af4096",
}


def helm_binary(directory: Path) -> str:
    existing = shutil.which("helm")
    if existing:
        version = subprocess.check_output([existing, "version", "--short"], text=True).strip()
        if version.split("+")[0] == VERSION:
            return existing
    if platform.system() != "Linux":
        raise ValueError(f"Install Helm {VERSION} for local deployment validation")
    architecture = {"aarch64": "arm64", "x86_64": "amd64"}[platform.machine()]
    url = f"https://get.helm.sh/helm-{VERSION}-linux-{architecture}.tar.gz"
    with urllib.request.urlopen(url, timeout=60) as response:
        data = response.read(40_000_001)
    if hashlib.sha256(data).hexdigest() != DIGESTS[architecture]:
        raise ValueError("Helm archive checksum mismatch")
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        source = archive.extractfile(f"linux-{architecture}/helm")
        if source is None:
            raise ValueError("Missing Helm binary")
        binary = directory / "helm"
        binary.write_bytes(source.read())
        binary.chmod(0o700)
    return str(binary)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="datavouch-chart-") as temporary:
        directory = Path(temporary)
        helm = helm_binary(directory)
        subprocess.run([helm, "lint", str(CHART), "--strict"], check=True)
        cases = {
            "default": {},
            "live-gateway": {
                "auth": {"mode": "gateway"},
                "execution": {"enabled": True},
                "config": {
                    "connections": [
                        {
                            "id": "test",
                            "label": "Test",
                            "project": "client-project",
                            "location": "us",
                            "maximum_bytes_billed": 100000000,
                            "timeout_seconds": 60,
                        }
                    ],
                    "gatewayPolicy": {
                        "allowed_hosts": ["datavouch.example.test"],
                        "trusted_proxy_networks": ["10.10.0.0/24"],
                        "principals": {},
                    },
                },
                "credentials": {"existingSecret": "external-adc", "quotaProject": "client-project"},
            },
            "live-discovery": {
                "execution": {"enabled": True},
                "config": {
                    "discovery": {
                        "quota_project": "client-quota",
                        "allowed_projects": ["client-project"],
                        "allowed_locations": ["*"],
                        "maximum_bytes_billed": 100000000,
                        "timeout_seconds": 60,
                    }
                },
            },
            "existing-storage": {"persistence": {"existingClaim": "customer-evidence"}},
            "ephemeral-viewer": {"persistence": {"enabled": False}},
        }
        for name, values in cases.items():
            supplied = directory / (name + ".json")
            supplied.write_text(json.dumps(values))
            rendered = subprocess.check_output(
                [helm, "template", "check", str(CHART), "-f", str(supplied)], text=True
            )
            resources = {r["kind"]: r for r in yaml.safe_load_all(rendered) if r}
            deployment = resources["Deployment"]
            assert deployment["spec"]["replicas"] == 1
            assert deployment["spec"]["strategy"]["type"] == "Recreate"
            pod = deployment["spec"]["template"]["spec"]
            assert pod["securityContext"]["runAsNonRoot"]
            assert pod["automountServiceAccountToken"] is False
            assert pod["terminationGracePeriodSeconds"] > 630
            for container in pod["containers"] + pod["initContainers"]:
                security = container["securityContext"]
                assert security["readOnlyRootFilesystem"]
                assert security["allowPrivilegeEscalation"] is False
                assert security["capabilities"]["drop"] == ["ALL"]
            assert resources["Service"]["spec"]["type"] == "ClusterIP"
            assert "Secret" not in resources and "Ingress" not in resources
            assert resources["NetworkPolicy"]["spec"]["ingress"] == []
            args = pod["containers"][0]["args"]
            assert ("--enable-live-execution" in args) == (
                name in {"live-gateway", "live-discovery"}
            )
            if name == "live-discovery":
                config = json.loads(resources["ConfigMap"]["data"]["connections.json"])
                assert config["connections"] == []
                assert config["discovery"]["quota_project"] == "client-quota"
            assert ("--gateway-config" in args) == (name == "live-gateway")
            if name in {"existing-storage", "ephemeral-viewer"}:
                assert "PersistentVolumeClaim" not in resources
            else:
                assert (
                    resources["PersistentVolumeClaim"]["metadata"]["annotations"][
                        "helm.sh/resource-policy"
                    ]
                    == "keep"
                )
        for values in (
            {"replicaCount": 2},
            {"auth": {"mode": "none"}},
            {"auth": {"existingSecret": ""}},
            {"execution": {"enabled": True}},
            {"auth": {"mode": "gateway"}},
            {"unknownOption": True},
            {"execution": {"enabled": True}, "persistence": {"enabled": False}},
        ):
            supplied = directory / "invalid.json"
            supplied.write_text(json.dumps(values))
            result = subprocess.run(
                [helm, "template", "check", str(CHART), "-f", str(supplied)], capture_output=True
            )
            assert result.returncode != 0, values
        subprocess.run([helm, "package", str(CHART), "--destination", str(directory)], check=True)
    print(
        "Helm lint, safe defaults, deployment variants, invalid configurations and packaging passed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
