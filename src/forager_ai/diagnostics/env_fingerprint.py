"""Lightweight environment fingerprint for support / sanity checks."""

from __future__ import annotations

import os
import platform
import subprocess
from typing import Any, Dict


def collect_env_fingerprint(*, java_command: str = "java", timeout_s: float = 8.0) -> Dict[str, Any]:
    """Best-effort: OS, Python, Java ``-version`` stderr (where vendors print), cwd."""
    out: Dict[str, Any] = {
        "os": platform.platform(),
        "python": platform.python_version(),
        "cwd": os.getcwd(),
        "java_command": java_command,
        "java_version_lines": [],
    }
    try:
        pr = subprocess.run(
            [java_command, "-version"],
            capture_output=True,
            text=True,
            timeout=timeout_s,
            encoding="utf-8",
            errors="replace",
        )
        err = (pr.stderr or "").strip().splitlines()
        out["java_version_lines"] = err[:8]
        out["java_exit_code"] = int(pr.returncode)
    except (OSError, subprocess.TimeoutExpired) as exc:
        out["java_error"] = str(exc)
    try:
        gr = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            timeout=4.0,
            encoding="utf-8",
            errors="replace",
        )
        out["git_version_line"] = ((gr.stdout or gr.stderr) or "").strip().splitlines()[:2]
    except (OSError, subprocess.TimeoutExpired) as exc:
        out["git_version_error"] = str(exc)
    try:
        import streamlit as st

        out["streamlit_version"] = str(getattr(st, "__version__", "?"))
    except Exception as exc:
        out["streamlit_version_error"] = str(exc)
    return out


def format_env_fingerprint_text(*, timeout_s: float = 6.0, max_chars: int = 1200) -> str:
    """Single readable block for AI context bundles and support exports."""
    fp = collect_env_fingerprint(timeout_s=timeout_s)
    lines: list[str] = [
        "[Environment fingerprint]",
        f"OS: {fp.get('os')}",
        f"Python: {fp.get('python')}",
        f"CWD: {fp.get('cwd')}",
    ]
    jl = fp.get("java_version_lines") or []
    if isinstance(jl, list) and jl:
        lines.append("Java:")
        lines.extend(f"  {ln}" for ln in jl[:4])
    elif fp.get("java_error"):
        lines.append(f"Java: (error) {fp.get('java_error')}")
    gl = fp.get("git_version_line") or []
    if isinstance(gl, list) and gl:
        lines.append(f"Git: {gl[0]}")
    if fp.get("git_version_error"):
        lines.append(f"Git: (error) {fp.get('git_version_error')}")
    if fp.get("streamlit_version"):
        lines.append(f"Streamlit: {fp.get('streamlit_version')}")
    text = "\n".join(lines).strip()
    return text[:max_chars] if text else ""
