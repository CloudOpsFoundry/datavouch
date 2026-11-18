import subprocess
import sys

from datavouch import __version__


def test_module_entrypoint():
    result = subprocess.run([sys.executable, "-m", "datavouch", "--version"], capture_output=True)
    assert result.returncode == 0
    assert __version__.encode() in result.stdout
