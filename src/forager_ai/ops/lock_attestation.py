"""Sidecar metadata for ``forager_mods.lock.json`` (checksum + timestamp)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def lock_file_sha256_hex(lock_path: str | Path) -> str:
    p = Path(str(lock_path))
    data = p.read_bytes()
    return hashlib.sha256(data).hexdigest()


def write_lock_attestation_sidecar(lock_path: str | Path) -> str:
    """
    Write ``forager_mods.lock.meta.json`` beside the lock with sha256 of the lock bytes.

    Returns path to the meta file.
    """
    lp = Path(str(lock_path))
    digest = lock_file_sha256_hex(lp)
    meta: Dict[str, Any] = {
        "kind": "forager_mods_lock_attestation",
        "lock_file": lp.name,
        "sha256": digest,
        "attested_at": _utc_iso(),
    }
    out = lp.with_name("forager_mods.lock.meta.json")
    out.write_text(json.dumps(meta, indent=2, ensure_ascii=True), encoding="utf-8")
    return str(out)
