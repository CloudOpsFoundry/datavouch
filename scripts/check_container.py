"""Smoke-test a built application image locally without cloud credentials.

Run: python scripts/check_container.py [image]
Requires Docker and a built image. Creates and removes only its own test container.
"""

import base64
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def main() -> int:
    image = sys.argv[1] if len(sys.argv) > 1 else "datavouch-app:local"
    name = "datavouch-acceptance-" + secrets.token_hex(6)
    password = secrets.token_urlsafe(32)
    with tempfile.TemporaryDirectory(prefix="datavouch-container-") as temporary:
        config = Path(temporary)
        (config / "password").write_text(password)
        (config / "password").chmod(0o600)
        try:
            subprocess.run(
                [
                    "docker",
                    "run",
                    "--detach",
                    "--name",
                    name,
                    "--read-only",
                    "--cap-drop=ALL",
                    "--security-opt=no-new-privileges",
                    "--pids-limit=128",
                    "--memory=1g",
                    "--cpus=1",
                    "--user",
                    f"{os.getuid()}:{os.getgid()}",
                    "--tmpfs",
                    "/tmp:size=67108864,mode=1777",
                    "--publish",
                    "127.0.0.1::8765",
                    "--mount",
                    f"type=bind,source={config},target=/config,readonly",
                    image,
                    "serve",
                    "/opt/datavouch/examples/viewer.json",
                    "--bind-address",
                    "0.0.0.0",
                    "--port",
                    "8765",
                    "--password-file",
                    "/config/password",
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            info = json.loads(subprocess.check_output(["docker", "inspect", name]))[0]
            assert info["HostConfig"]["ReadonlyRootfs"]
            assert info["HostConfig"]["CapDrop"] == ["ALL"]
            port = info["NetworkSettings"]["Ports"]["8765/tcp"][0]["HostPort"]
            base = f"http://127.0.0.1:{port}"
            token = base64.b64encode(f"datavouch:{password}".encode()).decode()
            for _attempt in range(100):
                try:
                    urllib.request.urlopen(base, timeout=2)
                except urllib.error.HTTPError as error:
                    assert error.code == 401
                    break
                except urllib.error.URLError, ConnectionError:
                    time.sleep(0.1)
                else:
                    raise AssertionError("Anonymous access unexpectedly succeeded")
            else:
                raise AssertionError("Container did not become ready")
            for path in ("/", "/workloads", "/experiments/new"):
                request = urllib.request.Request(
                    base + path, headers={"Authorization": "Basic " + token}
                )
                with urllib.request.urlopen(request, timeout=5) as response:
                    assert response.status == 200
                    assert response.headers["Cache-Control"] == "no-store"
                    if path == "/":
                        page = response.read().decode()
                        assert all(status in page for status in ("PASS", "FAIL", "UNKNOWN"))
            subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "python",
                    "-c",
                    "import os,sys,importlib.util; assert os.getuid()!=0; "
                    "assert sys.version_info[:2]==(3,15); "
                    "assert importlib.util.find_spec('pytest') is None; "
                    "assert importlib.util.find_spec('datavouch.web.access') is not None",
                ],
                check=True,
            )
            print(
                "Container passed: Python 3.15, non-root, restricted runtime, "
                "authentication and sample UI; no cloud calls"
            )
        finally:
            subprocess.run(["docker", "rm", "--force", name], capture_output=True, check=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
