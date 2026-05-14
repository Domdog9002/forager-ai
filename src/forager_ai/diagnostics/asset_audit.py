"""
Disk-side audit of a game root ``mods/`` tree (sizes, heavy jars, duplicate basenames).
"""

from __future__ import annotations

import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _logical_basename(rel: str) -> str:
    name = Path(rel.replace("\\", "/")).name
    low = name.lower()
    if low.endswith(".jar.disabled"):
        return name[: -len(".disabled")]
    return name


def build_mods_asset_audit(game_root: str, *, max_files: int = 2000) -> Dict[str, Any]:
    """
    Walk ``mods/**/*.jar`` and ``*.jar.disabled`` (same shape as the lockfile scanner).

    Returns largest jars, duplicate logical basenames, totals.
    """
    root = Path(str(game_root or "").strip())
    mods = root / "mods"
    rows: List[Dict[str, Any]] = []
    if not root.is_dir() or not mods.is_dir():
        return {
            "generated_at": _utc_iso(),
            "game_root_basename": root.name if root.is_dir() else "",
            "jar_count": 0,
            "total_bytes": 0,
            "largest": [],
            "duplicate_logical_names": [],
            "truncated": False,
        }

    by_logical: Dict[str, List[str]] = defaultdict(list)
    truncated = False
    n = 0
    for base, _, names in os.walk(str(mods)):
        for fn in sorted(names):
            fl = fn.lower()
            if fl.endswith(".jar.disabled"):
                pass
            elif not fl.endswith(".jar"):
                continue
            fp = Path(base) / fn
            try:
                rel = Path(os.path.relpath(str(fp), str(root))).as_posix()
                sz = int(fp.stat().st_size)
            except OSError:
                continue
            rows.append({"rel": rel, "size_bytes": sz, "logical": _logical_basename(rel)})
            by_logical[_logical_basename(rel)].append(rel)
            n += 1
            if n >= int(max_files):
                truncated = True
                break
        if truncated:
            break

    rows.sort(key=lambda r: int(r.get("size_bytes") or 0), reverse=True)
    total = sum(int(r["size_bytes"]) for r in rows)
    dups = [{"logical": k, "paths": v} for k, v in sorted(by_logical.items()) if len(v) > 1]

    return {
        "generated_at": _utc_iso(),
        "game_root_basename": root.name,
        "jar_count": len(rows),
        "total_bytes": total,
        "largest": rows[:25],
        "duplicate_logical_names": dups[:40],
        "truncated": truncated,
    }


def format_asset_audit_for_context(rep: Dict[str, Any], *, max_chars: int = 1600) -> str:
    """Compact text for AI prompts and crash tickets."""
    if not rep or not int(rep.get("jar_count") or 0):
        return ""
    lines = [
        "[Mods asset audit]",
        f"Jars counted (may be capped): {rep.get('jar_count')}",
        f"Total bytes (sampled tree): {rep.get('total_bytes')}",
    ]
    if rep.get("truncated"):
        lines.append("(walk truncated at max_files cap)")
    dups = rep.get("duplicate_logical_names") or []
    if isinstance(dups, list) and dups:
        lines.append("Duplicate logical jar names:")
        for d in dups[:10]:
            if not isinstance(d, dict):
                continue
            lg = str(d.get("logical") or "")
            paths = d.get("paths") or []
            if isinstance(paths, list) and paths:
                lines.append(f"- `{lg}` → {len(paths)} path(s), e.g. `{paths[0]}`")
    largest = rep.get("largest") or []
    if isinstance(largest, list) and largest:
        lines.append("Largest jars:")
        for row in largest[:8]:
            if not isinstance(row, dict):
                continue
            rel = str(row.get("rel") or "")
            sz = int(row.get("size_bytes") or 0)
            lines.append(f"- `{rel}` — {sz} bytes")
    text = "\n".join(lines).strip()
    return text[:max_chars] if text else ""
