"""
Optional local Forge MDK / Gradle runner (user-owned paths only).
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional


def _real_dir(path: str) -> Optional[str]:
    raw = (path or "").strip()
    if not raw:
        return None
    try:
        p = Path(raw).expanduser()
        if not p.is_dir():
            return None
        return str(p.resolve())
    except OSError:
        return None


def find_gradle_wrapper(mdk_root: str) -> Optional[str]:
    root = _real_dir(mdk_root)
    if not root:
        return None
    bat = Path(root) / "gradlew.bat"
    if bat.is_file():
        return str(bat)
    sh = Path(root) / "gradlew"
    if sh.is_file():
        return str(sh)
    return None


def run_gradle(*, mdk_root: str, task: str, timeout_s: int = 900) -> subprocess.CompletedProcess[str]:
    """
    Run ``gradlew <task>`` with cwd ``mdk_root``.

    On Windows the wrapper is invoked via ``gradlew.bat``; on Unix, ``./gradlew`` if needed.
    """
    root = _real_dir(mdk_root)
    if not root:
        raise FileNotFoundError(f"MDK root is not a directory: {mdk_root!r}")
    gw = find_gradle_wrapper(root)
    if not gw:
        raise FileNotFoundError(f"No gradlew / gradlew.bat under {root!r}")

    t = (task or "build").strip() or "build"
    args: List[str]
    if gw.endswith(".bat"):
        args = [gw, t]
    else:
        args = [gw, t]
        if os.name != "nt":
            try:
                os.chmod(gw, 0o755)
            except OSError:
                pass

    return subprocess.run(
        args,
        cwd=root,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        shell=False,
    )
