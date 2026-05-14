"""Preview and apply Pack Health auto-fix actions (jar disable, etc.)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence


@dataclass
class ApplyAutoResult:
    ok: bool
    message: str
    changed: List[str] = field(default_factory=list)


def _norm_mod_id(value: Any) -> str:
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _mod_label(mod_id: str, mods_by_id: Mapping[str, Dict[str, Any]]) -> str:
    row = mods_by_id.get(mod_id) or mods_by_id.get(_norm_mod_id(mod_id)) or {}
    name = str(row.get("name") or "").strip()
    return name or mod_id


def effective_auto_action(
    item: Mapping[str, Any],
    override: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    base = dict(item.get("action") or {})
    if override:
        merged = dict(override)
        base.update(merged)
    return base


def rebuild_remove_duplicates_action(
    *,
    keep_mod: str,
    affected_mods: Sequence[str],
) -> Dict[str, Any]:
    keep = _norm_mod_id(keep_mod)
    affected = [_norm_mod_id(m) for m in affected_mods if str(m).strip()]
    remove = [m for m in affected if m and m != keep]
    return {
        "action": "remove_duplicates",
        "keep_mod": keep,
        "remove_mods": remove,
    }


def is_action_applicable(action: Mapping[str, Any]) -> bool:
    return str(action.get("action") or "").strip() == "remove_duplicates"


def summarize_auto_action(
    action: Mapping[str, Any],
    *,
    mods_by_id: Mapping[str, Dict[str, Any]],
    conflict: Optional[Mapping[str, Any]] = None,
) -> str:
    kind = str(action.get("action") or "").strip()
    if kind == "remove_duplicates":
        keep = _mod_label(str(action.get("keep_mod") or ""), mods_by_id)
        remove_ids = [str(m) for m in (action.get("remove_mods") or []) if str(m).strip()]
        if not remove_ids:
            return f"Keep {keep} (no mods marked to disable)."
        remove_names = ", ".join(_mod_label(mid, mods_by_id) for mid in remove_ids)
        return f"Keep {keep} · disable {remove_names}"
    if kind == "install_dependency":
        dep = _mod_label(str(action.get("dependency_id") or ""), mods_by_id)
        req = _mod_label(str(action.get("required_by") or ""), mods_by_id)
        return f"Install {dep} for {req}"
    if conflict:
        sug = str(conflict.get("suggested_resolution") or "").strip()
        if sug:
            return sug
    return kind.replace("_", " ").strip().title() or "Review this auto-fix"


def _jar_row_matches_mod(row: Mapping[str, Any], mod_id: str, mods_by_id: Mapping[str, Dict[str, Any]]) -> bool:
    mid = _norm_mod_id(mod_id)
    mod_row = mods_by_id.get(mid) or {}
    file_name = str(mod_row.get("file_name") or "").strip().lower()
    jar_name = str(row.get("name") or "").strip().lower()
    rel = str(row.get("rel") or "").replace("\\", "/").lower()
    stem = jar_name
    if stem.endswith(".jar.disabled"):
        stem = stem[: -len(".disabled")]
    if stem.endswith(".jar"):
        stem = stem[: -len(".jar")]
    stem_norm = _norm_mod_id(stem)
    if file_name and (jar_name == file_name or rel.endswith(file_name)):
        return True
    if stem_norm == mid:
        return True
    return mid in stem_norm or stem_norm in mid


def find_jar_row_for_mod(
    mod_id: str,
    jar_rows: Sequence[Mapping[str, Any]],
    mods_by_id: Mapping[str, Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    for row in jar_rows:
        if _jar_row_matches_mod(row, mod_id, mods_by_id):
            return dict(row)
    return None


def _disable_jar_row(row: Mapping[str, Any]) -> tuple[bool, str, Optional[str]]:
    p = Path(str(row.get("path") or ""))
    if not p.is_file():
        return False, "File not found.", None
    s = str(p)
    low = s.lower()
    if row.get("disabled"):
        return True, "Already disabled.", row.get("rel")
    if not low.endswith(".jar"):
        return False, "Expected a `.jar` file.", None
    dst = Path(s + ".disabled")
    if dst.exists():
        return False, f"Blocked: `{dst.name}` already exists.", None
    try:
        os.replace(str(p), str(dst))
        rel = str(row.get("rel") or os.path.relpath(str(dst), start=os.path.dirname(os.path.dirname(str(p)))))
        return True, "Disabled.", rel.replace("\\", "/")
    except OSError as exc:
        return False, str(exc), None


def apply_auto_action(
    pack_root: str,
    action: Mapping[str, Any],
    *,
    mods_by_id: Mapping[str, Dict[str, Any]],
    jar_rows: Sequence[Mapping[str, Any]],
) -> ApplyAutoResult:
    _ = pack_root  # reserved for future checkpointing
    kind = str(action.get("action") or "").strip()
    if kind != "remove_duplicates":
        return ApplyAutoResult(
            ok=False,
            message="This auto-fix type cannot be applied from Pack Health yet.",
        )
    remove_ids = [str(m) for m in (action.get("remove_mods") or []) if str(m).strip()]
    if not remove_ids:
        return ApplyAutoResult(ok=False, message="Nothing to disable for this fix.")
    changed: List[str] = []
    errors: List[str] = []
    for mod_id in remove_ids:
        row = find_jar_row_for_mod(mod_id, jar_rows, mods_by_id)
        if not row:
            errors.append(f"No jar found for `{mod_id}`.")
            continue
        ok, msg, rel = _disable_jar_row(row)
        if ok and rel:
            changed.append(rel)
        elif not ok:
            errors.append(f"{_mod_label(mod_id, mods_by_id)}: {msg}")
    if changed and not errors:
        return ApplyAutoResult(
            ok=True,
            message=f"Disabled {len(changed)} mod(s). Re-enable from My Packs if needed.",
            changed=changed,
        )
    if changed:
        return ApplyAutoResult(
            ok=True,
            message=f"Partially applied ({len(changed)} disabled). Issues: {'; '.join(errors)}",
            changed=changed,
        )
    return ApplyAutoResult(ok=False, message="; ".join(errors) or "Could not apply auto-fix.")
