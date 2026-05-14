"""Compare two ``forager_mods.lock``-style payloads (jar rows + mod ids)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set


def _jar_rows(obj: Any) -> List[Dict[str, Any]]:
    if not isinstance(obj, dict):
        return []
    jars = obj.get("jars")
    if not isinstance(jars, list):
        return []
    return [j for j in jars if isinstance(j, dict)]


def _by_rel(rows: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for j in rows:
        rel = str(j.get("rel") or "").replace("\\", "/")
        if rel:
            out[rel] = j
    return out


def _mod_ids(rows: List[Dict[str, Any]]) -> Set[str]:
    s: Set[str] = set()
    for j in rows:
        mid = str(j.get("mod_id") or "").strip().lower()
        if mid:
            s.add(mid)
    return s


def diff_lock_payloads(lock_a: Dict[str, Any], lock_b: Dict[str, Any]) -> Dict[str, Any]:
    """Return structural diff (rels, mod ids, hash mismatches for shared rels)."""
    ra = _jar_rows(lock_a)
    rb = _jar_rows(lock_b)
    ba, bb = _by_rel(ra), _by_rel(rb)
    rels_a, rels_b = set(ba), set(bb)
    only_a = sorted(rels_a - rels_b, key=str.lower)
    only_b = sorted(rels_b - rels_a, key=str.lower)
    mismatch: List[Dict[str, Any]] = []
    for rel in sorted(rels_a & rels_b, key=str.lower):
        ha = str(ba[rel].get("sha256") or "").lower()
        hb = str(bb[rel].get("sha256") or "").lower()
        if ha and hb and ha != hb:
            mismatch.append(
                {
                    "rel": rel,
                    "sha256_a": ha[:16] + "…",
                    "sha256_b": hb[:16] + "…",
                }
            )
    ids_a, ids_b = _mod_ids(ra), _mod_ids(rb)
    return {
        "jar_rows_a": len(ra),
        "jar_rows_b": len(rb),
        "only_rels_in_a": only_a,
        "only_rels_in_b": only_b,
        "shared_rel_hash_mismatch": mismatch,
        "mod_ids_only_in_a": sorted(ids_a - ids_b, key=str.lower),
        "mod_ids_only_in_b": sorted(ids_b - ids_a, key=str.lower),
        "mod_ids_intersection_count": len(ids_a & ids_b),
    }


def load_lock_json_from_path(path: str) -> Dict[str, Any]:
    p = Path(str(path or "").strip())
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}
