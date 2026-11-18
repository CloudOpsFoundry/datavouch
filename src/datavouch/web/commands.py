"""Local-only server command with explicit access controls."""

import getpass
import os
import sqlite3
import sys
from pathlib import Path


def serve_command(
    catalog: Path,
    port: int,
    allow_raw_reports: bool,
    connections: Path | None = None,
    run_directory: Path | None = None,
    enable_live_execution: bool = False,
    gateway_config: Path | None = None,
    gateway_secret_file: Path | None = None,
    password_file: Path | None = None,
    bind_address: str = "127.0.0.1",
) -> int:
    if not 1024 <= port <= 65535:
        print("Port must be between 1024 and 65535.", file=sys.stderr)
        return 2
    # Explicit container option; authenticated service defaults to loopback.
    if bind_address not in {"127.0.0.1", "0.0.0.0"}:  # nosec B104
        print("Unsupported bind address.", file=sys.stderr)
        return 2
    try:
        password = (
            password_file.read_text().strip()
            if password_file
            else os.environ.get("DATAVOUCH_WEB_PASSWORD", "")
        )
        gateway_secret = gateway_secret_file.read_text().strip() if gateway_secret_file else ""
    except OSError:
        print("Cannot read the configured secret file.", file=sys.stderr)
        return 2
    if gateway_config is None and not password and sys.stdin.isatty():
        password = getpass.getpass("Set local viewer password (16+ ASCII characters): ")
    if gateway_config is None and not password:
        print("Set DATAVOUCH_WEB_PASSWORD or run from an interactive terminal.", file=sys.stderr)
        return 2
    try:
        import uvicorn

        from datavouch.web.app import create_app
    except ImportError:
        print("Install datavouch[web] to run the viewer.", file=sys.stderr)
        return 2
    try:
        app = create_app(
            catalog,
            password,
            allow_raw_reports=allow_raw_reports,
            connections=connections,
            run_directory=run_directory,
            enable_live_execution=enable_live_execution,
            gateway_config=gateway_config,
            gateway_secret=gateway_secret,
        )
    except ValueError, TypeError, OSError, OverflowError, RecursionError, sqlite3.Error:
        print(
            "Invalid catalog, connections, private run directory, store ownership or password. "
            "Check the viewer setup guide.",
            file=sys.stderr,
        )
        return 2
    print(f"DataVouch: http://127.0.0.1:{port} (username: datavouch)", flush=True)
    uvicorn.run(app, host=bind_address, port=port, access_log=False, proxy_headers=False)
    return 0
