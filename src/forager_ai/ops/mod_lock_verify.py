"""
Compare on-disk ``mods/`` against a previously exported ``forager_mods.lock.json``.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .mods_folder_lockfile import build_game_root_mods_lock


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def verify_forager_mods_lock(game_root: str) -> Dict[str, Any]:
    """
    Read ``<game_root>/forager_mods.lock.json`` and compare SHA-256 + size to a fresh scan.

    Rows: ``missing_on_disk``, ``extra_on_disk``, ``hash_mismatch``, ``ok``.
    """
    root = Path(str(game_root or "").strip())
    lock_path = root / "forager_mods.lock.json"
    if not lock_path.is_file():
        return {
            "ok": False,
            "generated_at": _utc_iso(),
            "message": "No forager_mods.lock.json beside this game root.",
        }
    try:
        lock_obj = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"ok": False, "generated_at": _utc_iso(), "message": f"Could not read lock: {exc}"}

    jars_lock: List[Dict[str, Any]] = lock_obj.get("jars") if isinstance(lock_obj.get("jars"), list) else []
    by_rel = {str(j.get("rel")): j for j in jars_lock if isinstance(j, dict) and j.get("rel")}

    current = build_game_root_mods_lock(str(root))
    cur_list = current.get("jars") if isinstance(current.get("jars"), list) else []
    by_cur = {str(j.get("rel")): j for j in cur_list if isinstance(j, dict) and j.get("rel")}

    missing: List[str] = [r for r in by_rel if r not in by_cur]
    extra: List[str] = [r for r in by_cur if r not in by_rel]
    mismatch: List[Dict[str, Any]] = []
    ok: List[str] = []
    for rel, row in by_rel.items():
        c = by_cur.get(rel)
        if not c:
            continue
        if str(row.get("sha256") or "").lower() == str(c.get("sha256") or "").lower():
            ok.append(rel)
        else:
            mismatch.append(
                {
                    "rel": rel,
                    "sha256_lock": (str(row.get("sha256") or "")[:16] + "…") if row.get("sha256") else "",
                    "sha256_disk": (str(c.get("sha256") or "")[:16] + "…") if c.get("sha256") else "",
                }
            )

    return {
        "ok": True,
        "generated_at": _utc_iso(),
        "lock_path": str(lock_path),
        "lock_jar_rows": len(by_rel),
        "disk_jar_rows": len(by_cur),
        "missing_on_disk": sorted(missing),
        "extra_on_disk": sorted(extra),
        "hash_mismatch": mismatch,
        "hash_ok_count": len(ok),
    }
