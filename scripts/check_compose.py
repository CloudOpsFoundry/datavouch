"""Exercise the actual Compose configuration and measured demo without cloud credentials."""

import base64
import json
import os
import secrets
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "deployment/container/compose.yaml"
DEMO = ROOT / "deployment/container/compose.demo.yaml"


def page(url: str, password: str) -> str:
    authorization = base64.b64encode(f"datavouch:{password}".encode()).decode()
    for _attempt in range(60):
        try:
            request = urllib.request.Request(
                url, headers={"Authorization": "Basic " + authorization}
            )
            with urllib.request.urlopen(request, timeout=2) as response:
                return response.read().decode()
        except urllib.error.URLError, ConnectionError:
            time.sleep(0.2)
    raise AssertionError("Compose workspace did not become ready")


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="datavouch-compose-") as temporary:
        root = Path(temporary)
        config, data = root / "config", root / "data"
        config.mkdir(mode=0o700)
        data.mkdir(mode=0o700)
        password = secrets.token_urlsafe(32)
        (config / "password").write_text(password)
        (config / "password").chmod(0o600)
        (config / "connections.json").write_text('{"connections": []}')
        env = {
            **os.environ,
            "DATAVOUCH_CONFIG_DIR": str(config),
            "DATAVOUCH_DATA_DIR": str(data),
            "DATAVOUCH_UID": str(os.getuid()),
            "DATAVOUCH_GID": str(os.getgid()),
            "DATAVOUCH_PORT": "0",
        }
        command = [
            "docker",
            "compose",
            "--project-name",
            "dv-acceptance-" + secrets.token_hex(4),
            "-f",
            str(BASE),
        ]

        def run(args: list[str], *, demo: bool = False) -> str:
            prefix = command + (["-f", str(DEMO)] if demo else [])
            return subprocess.check_output(
                prefix + args, env=env, text=True, stderr=subprocess.STDOUT
            )

        def base_url(demo: bool = False) -> str:
            address = run(["port", "datavouch", "8765"], demo=demo).strip()
            return "http://" + address

        try:
            run(["up", "-d", "--no-build", "--pull", "never"])
            assert "No connections configured" in page(base_url() + "/experiments/new", password)
            try:
                urllib.request.urlopen(base_url(), timeout=5)
            except urllib.error.HTTPError as error:
                assert error.code == 401
            else:
                raise AssertionError("Anonymous access must fail")
            run(["run", "--rm", "--no-deps", "datavouch", "demo", "--output-dir", "/data/demo"])
            summary = json.loads((data / "demo/summary.json").read_text())
            assert summary["results"][1]["status"] == "FAIL"
            run(["up", "-d", "--no-build", "--pull", "never"], demo=True)
            assert "Weighted aggregation" in page(base_url(True) + "/workloads", password)
            before = (data / "demo/incorrect-report.json").read_bytes()
            run(["restart", "datavouch"], demo=True)
            assert "Weighted aggregation" in page(base_url(True) + "/workloads", password)
            assert before == (data / "demo/incorrect-report.json").read_bytes()
            print(
                json.dumps(
                    {
                        "compose": "PASS",
                        "empty_configuration": "PASS",
                        "authentication": "PASS",
                        "restart_persistence": "PASS",
                        "measured_demo": summary,
                    },
                    indent=2,
                )
            )
        finally:
            run(["down", "--remove-orphans"], demo=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
