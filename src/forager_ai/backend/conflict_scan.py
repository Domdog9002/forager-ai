"""
Conflict scan helpers for turning pack state into UI-ready findings.

This module keeps Streamlit rendering separate from resolver data preparation so
conflict detection can be tested without launching the dashboard.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .conflict_resolver import ConflictResolver, ConflictSeverity, ModConflict
from ..launcher.jar_mod_metadata import read_jar_mod_metadata
from ..launcher.mod_downloader import ModInfo


SEVERITY_ORDER = ("critical", "high", "medium", "low")
BLOCKING_SEVERITIES = {"critical"}
WARNING_SEVERITIES = {"high", "medium"}


def _first_string(entry: Dict[str, Any], keys: Iterable[str], default: str = "") -> str:
    for key in keys:
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if value is not None and key in {"id", "project_id", "version_id"}:
            text = str(value).strip()
            if text:
                return text
    return default


def _string_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, dict):
        normalized: List[str] = []
        for key in ("id", "mod_id", "slug", "project_id", "name"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                normalized.append(item.strip())
                break
        return normalized
    if isinstance(value, list):
        out: List[str] = []
        for item in value:
            out.extend(_string_list(item))
        return list(dict.fromkeys(out))
    return []


def _normalize_mod_id(raw: str, fallback: str) -> str:
    value = (raw or fallback or "unknown_mod").strip().lower()
    for old, new in ((" ", "_"), ("-", "_")):
        value = value.replace(old, new)
    return value or "unknown_mod"


def mod_info_from_manifest_entry(
    entry: Dict[str, Any],
    *,
    default_minecraft_version: str = "1.20.1",
    default_loader: str = "forge",
) -> Optional[ModInfo]:
    """Convert a manifest mod dictionary into resolver-ready ``ModInfo``."""
    if not isinstance(entry, dict):
        return None

    display_name = _first_string(
        entry,
        ("name", "display_name", "title", "file_stem", "file_name", "slug", "mod_id", "id"),
        "Unknown Mod",
    )
    mod_id = _normalize_mod_id(
        _first_string(entry, ("mod_id", "id", "slug", "project_id"), display_name),
        display_name,
    )
    minecraft_versions = _string_list(
        entry.get("minecraft_versions")
        or entry.get("game_versions")
        or entry.get("versions")
        or entry.get("minecraft_version")
    )
    if not minecraft_versions and default_minecraft_version:
        minecraft_versions = [default_minecraft_version]

    loaders = _string_list(entry.get("loaders") or entry.get("loader") or entry.get("loader_kind"))
    if not loaders and default_loader:
        loaders = [default_loader]

    categories = _string_list(entry.get("categories") or entry.get("tags") or entry.get("extra_tags"))
    dependencies = _string_list(entry.get("dependencies") or entry.get("requires") or entry.get("required_dependencies"))

    return ModInfo(
        id=mod_id,
        name=display_name,
        description=_first_string(entry, ("description", "summary", "body"), ""),
        author=_first_string(entry, ("author", "authors", "owner"), ""),
        source=_first_string(entry, ("source",), "manifest"),
        project_id=_first_string(entry, ("project_id", "id", "mod_id", "slug"), mod_id),
        version_id=_first_string(entry, ("version_id", "file_id"), "") or None,
        minecraft_versions=minecraft_versions,
        loaders=loaders,
        categories=categories,
        download_url=_first_string(entry, ("download_url", "url"), "") or None,
        file_name=_first_string(entry, ("file_name", "filename"), "") or None,
        file_size=entry.get("file_size") if isinstance(entry.get("file_size"), int) else None,
        sha1_hash=_first_string(entry, ("sha1_hash", "sha1", "hash"), "") or None,
        dependencies=dependencies,
        icon_url=_first_string(entry, ("icon_url", "icon"), "") or None,
        project_url=_first_string(entry, ("project_url", "homepage", "url"), "") or None,
        download_total=entry.get("download_total") if isinstance(entry.get("download_total"), int) else None,
        updated_at=_first_string(entry, ("updated_at", "date_modified"), "") or None,
        catalog_kind=_first_string(entry, ("catalog_kind",), "mods") or "mods",
    )


def mod_info_from_jar(jar_path: Path, *, default_minecraft_version: str, default_loader: str) -> ModInfo:
    """Read best-effort metadata from a local jar and return ``ModInfo``."""
    meta = read_jar_mod_metadata(str(jar_path))
    display_name = str(meta.get("display_name") or jar_path.stem).strip()
    lk = str(meta.get("loader_kind") or "").strip().lower()
    if lk in ("", "unknown"):
        lk = str(default_loader or "forge").strip().lower() or "forge"
    loader = lk
    mod_id = _normalize_mod_id(str(meta.get("mod_id") or jar_path.stem), jar_path.stem)
    categories = _string_list(meta.get("tags"))
    return ModInfo(
        id=mod_id,
        name=display_name or mod_id,
        description=str(meta.get("description") or "").strip(),
        author="",
        source="local_jar",
        project_id=mod_id,
        minecraft_versions=[default_minecraft_version] if default_minecraft_version else [],
        loaders=[loader] if loader else [],
        categories=categories,
        file_name=jar_path.name,
        file_size=jar_path.stat().st_size if jar_path.exists() else None,
        dependencies=[],
        catalog_kind="mods",
    )


def collect_pack_mods(manifest: Dict[str, Any], pack_root: str) -> List[ModInfo]:
    """Collect resolver-ready mods from the manifest, falling back to local jars."""
    default_minecraft_version = str(manifest.get("minecraft_version") or "1.20.1")
    default_loader = str(manifest.get("loader") or "forge")
    mods: List[ModInfo] = []
    seen: set[str] = set()

    for entry in manifest.get("mods") or []:
        if not isinstance(entry, dict):
            continue
        mod = mod_info_from_manifest_entry(
            entry,
            default_minecraft_version=default_minecraft_version,
            default_loader=default_loader,
        )
        if mod and mod.id not in seen:
            mods.append(mod)
            seen.add(mod.id)

    mods_dir = Path(pack_root) / "mods"
    if mods_dir.is_dir():
        for jar_path in sorted(mods_dir.glob("*.jar")):
            mod = mod_info_from_jar(
                jar_path,
                default_minecraft_version=default_minecraft_version,
                default_loader=default_loader,
            )
            if mod.id not in seen:
                mods.append(mod)
                seen.add(mod.id)

    return mods


def collect_pack_mods_with_candidate(
    manifest: Dict[str, Any],
    pack_root: str,
    candidate: ModInfo,
) -> List[ModInfo]:
    """Collect current pack mods and simulate adding a candidate mod."""
    mods = collect_pack_mods(manifest, pack_root)
    existing = {mod.id for mod in mods}
    if candidate.id not in existing:
        mods.append(candidate)
    return mods


def serialize_conflict(conflict: ModConflict, mod_lookup: Dict[str, ModInfo]) -> Dict[str, Any]:
    """Return a stable, UI-friendly conflict dictionary."""
    affected_labels = [
        mod_lookup[mod_id].name if mod_id in mod_lookup else mod_id
        for mod_id in conflict.affected_mods
    ]
    return {
        "id": conflict.id,
        "type": conflict.type.value,
        "severity": conflict.severity.value,
        "affected_mods": list(conflict.affected_mods),
        "affected_labels": affected_labels,
        "description": conflict.description,
        "suggested_resolution": conflict.suggested_resolution,
        "auto_resolvable": bool(conflict.auto_resolvable),
        "resolution_actions": list(conflict.resolution_actions or []),
    }


def summarize_conflicts(conflicts: List[ModConflict], mod_count: int) -> Dict[str, Any]:
    severity_counts = Counter(conflict.severity.value for conflict in conflicts)
    type_counts = Counter(conflict.type.value for conflict in conflicts)
    highest = "none"
    for severity in SEVERITY_ORDER:
        if severity_counts.get(severity, 0):
            highest = severity
            break
    return {
        "mods_scanned": mod_count,
        "total_conflicts": len(conflicts),
        "auto_resolvable": sum(1 for conflict in conflicts if conflict.auto_resolvable),
        "manual_required": sum(1 for conflict in conflicts if not conflict.auto_resolvable),
        "highest_severity": highest,
        "severity_counts": {severity: severity_counts.get(severity, 0) for severity in SEVERITY_ORDER},
        "type_counts": dict(sorted(type_counts.items())),
    }


def decide_preflight(summary: Dict[str, Any]) -> Dict[str, Any]:
    """Map scan severity summary to an install decision."""
    severity_counts = summary.get("severity_counts") or {}
    tc = int(summary.get("total_conflicts") or 0)
    if any(int(severity_counts.get(severity, 0) or 0) > 0 for severity in BLOCKING_SEVERITIES):
        decision = "block"
        message = "Critical compatibility risks detected. Review before installing."
    elif any(int(severity_counts.get(severity, 0) or 0) > 0 for severity in WARNING_SEVERITIES):
        decision = "warn"
        message = "Compatibility warnings detected. Install only after reviewing the findings."
    elif tc > 0 and not any(
        int(severity_counts.get(severity, 0) or 0) > 0 for severity in SEVERITY_ORDER
    ):
        # Defensive: conflicts were counted but per-severity buckets are empty/out of sync.
        highest = str(summary.get("highest_severity") or "").strip().lower()
        if highest in BLOCKING_SEVERITIES or highest == "error":
            decision = "block"
            message = "Critical compatibility risks detected. Review before installing."
        else:
            decision = "warn"
            message = "Compatibility findings detected. Install only after reviewing the findings."
    else:
        decision = "allow"
        message = "No blocking compatibility risks detected."
    return {"decision": decision, "message": message}


def build_conflict_council_artifact(
    *,
    pack_name: str,
    manifest: Dict[str, Any],
    summary: Dict[str, Any],
    conflicts: List[Dict[str, Any]],
    resolution_plan: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a JSON artifact suitable for the AI Council page."""
    return {
        "artifact_type": "forager_conflict_scan",
        "pack_name": pack_name,
        "minecraft_version": manifest.get("minecraft_version"),
        "loader": manifest.get("loader"),
        "summary": summary,
        "conflicts": conflicts,
        "resolution_plan": resolution_plan,
        "review_questions": [
            "Which findings are likely false positives?",
            "Which manual actions are safest for a Forge 1.20.1 pack?",
            "Which compatibility rules should be persisted for future scans?",
        ],
    }


def build_conflict_scan_report(
    *,
    resolver: ConflictResolver,
    manifest: Dict[str, Any],
    pack_root: str,
    pack_name: str,
    auto_resolve: bool = True,
    skip_conflict_ids: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Run the resolver and return all dashboard-facing conflict scan data."""
    mods = collect_pack_mods(manifest, pack_root)
    conflicts = resolver.analyze_mod_list(mods, pack_manifest=manifest)
    if skip_conflict_ids:
        banned = {str(x).strip() for x in skip_conflict_ids if str(x).strip()}
        if banned:
            conflicts = [c for c in conflicts if c.id not in banned]
    mod_lookup = {mod.id: mod for mod in mods}
    serialized = [serialize_conflict(conflict, mod_lookup) for conflict in conflicts]
    summary = summarize_conflicts(conflicts, len(mods))
    resolution_plan = resolver.resolve_conflicts(conflicts, auto_resolve=auto_resolve)
    council_artifact = build_conflict_council_artifact(
        pack_name=pack_name,
        manifest=manifest,
        summary=summary,
        conflicts=serialized,
        resolution_plan=resolution_plan,
    )
    return {
        "mods": [
            {
                "id": mod.id,
                "name": mod.name,
                "source": mod.source,
                "file_name": mod.file_name,
                "minecraft_versions": list(mod.minecraft_versions or []),
                "loaders": list(mod.loaders or []),
                "dependencies": list(mod.dependencies or []),
            }
            for mod in mods
        ],
        "conflicts": serialized,
        "summary": summary,
        "resolution_plan": resolution_plan,
        "council_artifact": council_artifact,
    }


def _install_preflight_gates(
    manifest: Dict[str, Any],
    pack_root: str,
    candidate: ModInfo,
) -> Dict[str, Any]:
    """Extra deterministic notes beyond resolver output (MC/loader labels, duplicates)."""
    notes: List[str] = []
    bump_warn = False
    mods_existing = collect_pack_mods(manifest, pack_root)
    by_id = {m.id for m in mods_existing}
    if candidate.id in by_id:
        notes.append("That project is already represented in this pack — avoid installing twice unless you intend to upgrade in place.")
        bump_warn = True

    mc_pack = str(manifest.get("minecraft_version") or "").strip()
    cand_mc = [str(x).strip() for x in (candidate.minecraft_versions or [])]
    if mc_pack and cand_mc and mc_pack not in cand_mc:
        notes.append(
            f"Catalog metadata may not list your pack Minecraft version ({mc_pack}); verify on the project page before installing."
        )
        bump_warn = True

    pack_ld = str(manifest.get("loader") or "").strip().lower()
    cand_ld = [str(x).strip().lower() for x in (candidate.loaders or [])]
    if pack_ld and cand_ld and pack_ld not in cand_ld:
        notes.append(f"Loader mismatch risk: pack is **{pack_ld}** but listing emphasizes {cand_ld}.")
        bump_warn = True

    return {"notes": notes, "bump_warn": bump_warn}


def build_install_preflight_report(
    *,
    resolver: ConflictResolver,
    manifest: Dict[str, Any],
    pack_root: str,
    pack_name: str,
    candidate: ModInfo,
) -> Dict[str, Any]:
    """Simulate adding a catalog item and return an install decision."""
    mods = collect_pack_mods_with_candidate(manifest, pack_root, candidate)
    conflicts = resolver.analyze_mod_list(mods, pack_manifest=manifest)
    mod_lookup = {mod.id: mod for mod in mods}
    serialized = [serialize_conflict(conflict, mod_lookup) for conflict in conflicts]
    summary = summarize_conflicts(conflicts, len(mods))
    decision = decide_preflight(summary)
    gates = _install_preflight_gates(manifest, pack_root, candidate)
    resolution_plan = resolver.resolve_conflicts(conflicts, auto_resolve=True)
    council_artifact = build_conflict_council_artifact(
        pack_name=pack_name,
        manifest=manifest,
        summary=summary,
        conflicts=serialized,
        resolution_plan=resolution_plan,
    )
    msg = decision["message"]
    dec = decision["decision"]
    gn = gates.get("notes") or []
    if gn:
        msg = f"{msg} Notes: " + " ".join(gn)
    if dec == "allow" and gates.get("bump_warn"):
        dec = "warn"
        if "warn" not in msg.lower():
            msg = msg + " — elevate to manual review."
    return {
        "candidate": {
            "id": candidate.id,
            "name": candidate.name,
            "source": candidate.source,
            "minecraft_versions": list(candidate.minecraft_versions or []),
            "loaders": list(candidate.loaders or []),
            "dependencies": list(candidate.dependencies or []),
        },
        "decision": dec,
        "message": msg,
        "preflight_notes": gn,
        "summary": summary,
        "conflicts": serialized,
        "resolution_plan": resolution_plan,
        "council_artifact": council_artifact,
    }
