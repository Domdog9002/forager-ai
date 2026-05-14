"""Optional, budgeted text snippets for pack-aware AI context (Batch 1)."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any, List

from ..launcher.install_provenance import read_install_provenance_tail
from ..trace.change_log import read_recent_traces


def snippet_lock_json_excerpt(pack_root: str, *, max_chars: int = 2000) -> str:
    """First bytes of ``forager_mods.lock.json`` if present."""
    p = Path(str(pack_root or "").strip()) / "forager_mods.lock.json"
    if not p.is_file():
        return ""
    try:
        raw = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    t = raw.strip()
    if len(t) > max_chars:
        return t[: max_chars - 24] + "\n… (lockfile truncated)"
    return t


def snippet_trace_tail_text(pack_root: str, *, limit: int = 8, max_chars: int = 1400) -> str:
    """Compact lines from ``.forager/change_trace.jsonl``."""
    rows = read_recent_traces(str(pack_root or "").strip(), limit=max(1, min(int(limit), 40)))
    if not rows:
        return ""
    lines: List[str] = []
    for r in rows[-limit:]:
        if not isinstance(r, dict):
            continue
        ts = str(r.get("ts") or "")[:24]
        fn = str(r.get("feature_name") or "?")[:80]
        n = r.get("actions_executed")
        lines.append(f"- {ts} · {fn} · actions={n}")
    blob = "[Recent change trace]\n" + "\n".join(lines)
    return blob[:max_chars]


def snippet_provenance_compact(cache_dir: str, *, max_lines: int = 10, max_chars: int = 1400) -> str:
    """Short lines from install provenance tail (Modrinth/Curse installs)."""
    rows = read_install_provenance_tail(cache_dir, max_lines=max(1, min(int(max_lines), 40)))
    if not rows:
        return ""
    lines: List[str] = []
    for r in rows[-max_lines:]:
        if not isinstance(r, dict):
            continue
        src = str(r.get("source") or "")
        pid = str(r.get("project_id") or "")[:40]
        fn = str(r.get("file_name") or "")[:60]
        lines.append(f"- {src} `{pid}` → {fn}")
    blob = "[Recent catalog installs (provenance)]\n" + "\n".join(lines)
    return blob[:max_chars]


def _git_repo_root(path: str) -> str | None:
    root = Path(str(path or "").strip()).resolve()
    if not root.is_dir():
        return None
    for base in [root] + list(root.parents)[:12]:
        gitp = base / ".git"
        if gitp.is_dir() or gitp.is_file():
            return str(base)
    return None


def snippet_git_name_status_for_pack(pack_root: str, *, max_chars: int = 1500) -> str:
    """``git diff --name-status HEAD -- <relpath>`` when pack lives in a git repo."""
    pack_root = os.path.abspath(str(pack_root or "").strip())
    if not os.path.isdir(pack_root):
        return ""
    repo = _git_repo_root(pack_root)
    if not repo:
        return ""
    try:
        rel = os.path.relpath(pack_root, repo).replace("\\", "/")
    except ValueError:
        return ""
    if rel.startswith(".."):
        return ""
    try:
        pr = subprocess.run(
            ["git", "diff", "--name-status", "HEAD", "--", rel],
            cwd=repo,
            capture_output=True,
            text=True,
            timeout=22,
            encoding="utf-8",
            errors="replace",
        )
        out = (pr.stdout or "").strip()
        if not out and (pr.stderr or "").strip():
            return ""
        if not out:
            return ""
        hdr = f"(git: `{repo}` · path `{rel}`)\n"
        return (hdr + out)[:max_chars]
    except (OSError, subprocess.TimeoutExpired):
        return ""


def lockfile_sha256_hex(pack_root: str) -> str:
    """SHA-256 hex of ``forager_mods.lock.json`` if present, else empty."""
    p = Path(str(pack_root or "").strip()) / "forager_mods.lock.json"
    if not p.is_file():
        return ""
    try:
        import hashlib

        h = hashlib.sha256()
        with p.open("rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        return ""


def count_top_level_mod_jars(pack_root: str) -> int:
    """Count ``*.jar`` directly under ``mods/`` (quick sanity metric)."""
    m = Path(str(pack_root or "").strip()) / "mods"
    if not m.is_dir():
        return 0
    n = 0
    try:
        for name in os.listdir(m):
            if str(name).lower().endswith(".jar") and (m / name).is_file():
                n += 1
    except OSError:
        return 0
    return n


def snippet_jvm_hints_text(launcher: Any, *, max_chars: int = 1200) -> str:
    """Launcher default-memory aligned JVM copy hints (read-only)."""
    if launcher is None:
        return ""
    try:
        from ..diagnostics.jvm_hints import suggest_jvm_args_lines

        mem = int(launcher.config.get("default_memory") or 4096)
    except (TypeError, ValueError, AttributeError):
        mem = 4096
    lines = suggest_jvm_args_lines(default_memory_mb=mem)
    blob = "[JVM hints — Forager defaults, not auto-applied]\n" + "\n".join(lines)
    return blob[:max_chars]
