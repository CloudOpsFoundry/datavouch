import subprocess
import sys


def test_module_entrypoint():
    result = subprocess.run([sys.executable, "-m", "datavouch", "--version"], capture_output=True)
    assert result.returncode == 0
    assert b"0.1.0a1" in result.stdout
