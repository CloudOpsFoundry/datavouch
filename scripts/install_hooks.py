"""Install opt-in hooks without replacing existing hooks."""

import argparse
import shlex
import subprocess
import sys
from pathlib import Path

MARKER = "# DataVouch managed hook"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--with-push", action="store_true")
    args = parser.parse_args()
    hooks = Path(
        subprocess.check_output(["git", "rev-parse", "--git-path", "hooks"], text=True).strip()
    )
    selected = ["pre-commit", "pre-push"] if args.with_push or args.uninstall else ["pre-commit"]
    for name in selected:
        path = hooks / name
        if path.exists() and MARKER not in path.read_text():
            parser.error(f"Refusing to replace unmanaged hook: {path}")
    for name in selected:
        path = hooks / name
        if args.uninstall:
            path.unlink(missing_ok=True)
            continue
        hooks.mkdir(parents=True, exist_ok=True)
        python = shlex.quote(sys.executable)
        body = (
            f"{python} -m ruff format --check .\n{python} -m ruff check .\n"
            if name == "pre-commit"
            else f"{python} scripts/validate.py\n"
        )
        path.write_text(f"#!/bin/sh\n{MARKER}\nset -eu\n{body}")
        path.chmod(0o755)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
