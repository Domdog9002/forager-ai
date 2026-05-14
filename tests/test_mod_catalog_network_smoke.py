"""Network smoke: Modrinth catalog APIs (optional; set FORAGER_RUN_NET_TESTS=1)."""

import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.mark.skipif(not os.environ.get("FORAGER_RUN_NET_TESTS"), reason="set FORAGER_RUN_NET_TESTS=1 for live Modrinth API")
def test_verify_mod_catalog_apis_script():
    script = os.path.join(ROOT, "scripts", "verify_mod_catalog_apis.py")
    r = subprocess.run(
        [sys.executable, script],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert r.returncode == 0, r.stdout + r.stderr
