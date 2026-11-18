"""Local-only server command with explicit access controls."""

import getpass
import os
import sys
from pathlib import Path


def serve_command(catalog: Path, port: int, allow_raw_reports: bool) -> int:
    if not 1024 <= port <= 65535:
        print("Port must be between 1024 and 65535.", file=sys.stderr)
        return 2
    password = os.environ.get("DATAVOUCH_WEB_PASSWORD")
    if not password and sys.stdin.isatty():
        password = getpass.getpass("Set local viewer password (16+ ASCII characters): ")
    if not password:
        print("Set DATAVOUCH_WEB_PASSWORD or run from an interactive terminal.", file=sys.stderr)
        return 2
    try:
        import uvicorn

        from datavouch.web.app import create_app
    except ImportError:
        print("Install datavouch[web] to run the viewer.", file=sys.stderr)
        return 2
    try:
        app = create_app(catalog, password, allow_raw_reports=allow_raw_reports)
    except (ValueError, TypeError, OSError, OverflowError, RecursionError):
        print("Invalid catalog or password. Check the viewer setup guide.", file=sys.stderr)
        return 2
    print(f"DataVouch: http://127.0.0.1:{port} (username: datavouch)", flush=True)
    uvicorn.run(app, host="127.0.0.1", port=port, access_log=False, proxy_headers=False)
    return 0
