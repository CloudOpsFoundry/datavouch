import os
import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "install_hooks.py"


def test_hooks_preserve_existing_and_uninstall(tmp_path):
    subprocess.run(["git", "init", str(tmp_path)], check=True, capture_output=True)
    hook = tmp_path / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\necho user hook\n")
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp_path, capture_output=True)
    assert result.returncode != 0
    assert "user hook" in hook.read_text()
    hook.unlink()
    subprocess.run([sys.executable, str(SCRIPT), "--with-push"], cwd=tmp_path, check=True)
    assert os.access(hook, os.X_OK)
    assert "DataVouch managed hook" in hook.read_text()
    subprocess.run([sys.executable, str(SCRIPT), "--uninstall"], cwd=tmp_path, check=True)
    assert not hook.exists()
    assert not (tmp_path / ".git/hooks/pre-push").exists()
