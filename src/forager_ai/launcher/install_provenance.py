"""
Append-only log of catalog installs (Modrinth / CurseForge) for audit and support.

Each successful ``download_mod`` write adds one JSON line with source, ids,
filename, path, expected SHA-1 (when known), and computed SHA-256 of bytes on disk.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

_LOG_NAME = "install_provenance.jsonl"
_MAX_TAIL_BYTES = 512_000


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def sha1_file(path: str) -> str:
    h = hashlib.sha1()  # noqa: S324 — intentional for Minecraft ecosystem parity
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def build_provenance_record(mod_info: Any, dest_path: str, *, note: str = "") -> Dict[str, Any]:
    """Build a serializable row after a file exists at ``dest_path``."""
    try:
        sz = int(os.path.getsize(dest_path))
    except OSError:
        sz = 0
    sha256_hex = ""
    sha1_got = ""
    try:
        sha256_hex = sha256_file(dest_path)
        sha1_got = sha1_file(dest_path)
    except OSError:
        pass
    exp = str(getattr(mod_info, "sha1_hash", None) or "").strip().lower()
    return {
        "ts": _utc_iso(),
        "source": str(getattr(mod_info, "source", "") or ""),
        "project_id": str(getattr(mod_info, "project_id", "") or ""),
        "version_id": str(getattr(mod_info, "version_id", "") or getattr(mod_info, "id", "") or ""),
        "catalog_kind": str(getattr(mod_info, "catalog_kind", "") or ""),
        "name": str(getattr(mod_info, "name", "") or "")[:200],
        "file_name": str(getattr(mod_info, "file_name", "") or ""),
        "path": os.path.normpath(str(dest_path)),
        "size_bytes": sz,
        "sha1_expected": exp,
        "sha1_computed": sha1_got.lower() if sha1_got else "",
        "sha256": sha256_hex.lower() if sha256_hex else "",
        "note": (note or "")[:500],
    }


def append_install_provenance(cache_dir: str | Path, record: Dict[str, Any]) -> str:
    """Append one JSON object as a line; returns path to the log file."""
    root = Path(str(cache_dir))
    root.mkdir(parents=True, exist_ok=True)
    log_path = root / _LOG_NAME
    line = json.dumps(record, ensure_ascii=True, separators=(",", ":")) + "\n"
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(line)
    return str(log_path)


def read_install_provenance_tail(cache_dir: str | Path, *, max_lines: int = 40) -> List[Dict[str, Any]]:
    """Return up to ``max_lines`` most recent records (best-effort)."""
    log_path = Path(str(cache_dir)) / _LOG_NAME
    if not log_path.is_file():
        return []
    try:
        raw = log_path.read_bytes()
        if len(raw) > _MAX_TAIL_BYTES:
            raw = raw[-_MAX_TAIL_BYTES:]
            cut = raw.find(b"\n")
            if cut >= 0:
                raw = raw[cut + 1 :]
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return []
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    tail = lines[-max_lines:]
    out: List[Dict[str, Any]] = []
    for ln in tail:
        try:
            out.append(json.loads(ln))
        except json.JSONDecodeError:
            continue
    return out
