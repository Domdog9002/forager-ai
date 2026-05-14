"""Surface compat rules that touch installed mods."""

from __future__ import annotations

from typing import Any, Dict, List, Set

from .compat_registry import list_compat_rules


def _norm(s: str) -> str:
    t = (s or "").strip().lower()
    if ":" in t:
        t = t.split(":", 1)[-1].strip()
    return t


def compat_rules_touching_mod_ids(
    pack_root: str,
    installed_mod_ids: Set[str],
    *,
    max_rules: int = 40,
) -> List[Dict[str, Any]]:
    """Return rules whose ``affected_mods`` intersect ``installed_mod_ids`` (lowercased)."""
    want = {_norm(x) for x in installed_mod_ids if _norm(x)}
    if not want:
        return []
    out: List[Dict[str, Any]] = []
    for rule in list_compat_rules(pack_root):
        if not isinstance(rule, dict):
            continue
        affected = rule.get("affected_mods") or []
        if not isinstance(affected, list):
            continue
        touched = sorted({a for a in affected if _norm(str(a)) in want})
        if not touched:
            continue
        row = dict(rule)
        row["_matched_installed"] = touched
        out.append(row)
        if len(out) >= int(max_rules):
            break
    return out
