"""Parse common server / pack manifests into mod identifiers for parity tools."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple


def _norm(s: str) -> str:
    t = (s or "").strip().lower()
    if ":" in t:
        t = t.split(":", 1)[-1].strip()
    return t


def extract_from_manifest_json(raw: str) -> Tuple[Set[str], Set[str], str]:
    """
    Returns ``(mod_like_ids, curse_numeric_project_ids, note)``.

    Supports:
    - Forge ``minecraftModpackManifest`` ``files`` with ``projectID`` (numeric)
    - Plain ``mod_ids`` / ``mods`` string arrays (same as server_parity)
    - Modrinth pack index ``files`` with ``path`` under ``mods/*.jar`` → jar stem heuristics
    """
    mod_ids: Set[str] = set()
    cf_projects: Set[str] = set()
    notes: List[str] = []
    raw = (raw or "").strip()
    if not raw:
        return mod_ids, cf_projects, "Empty input."

    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return set(), set(), f"Invalid JSON: {exc}"

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, (int, float)):
                cf_projects.add(str(int(item)))
            elif isinstance(item, str):
                mod_ids.add(_norm(item))
        return mod_ids, cf_projects, "Parsed top-level JSON array."

    if not isinstance(obj, dict):
        return set(), set(), "JSON root must be object or array."

    mcm = obj.get("minecraft") if isinstance(obj.get("minecraft"), dict) else {}
    files = obj.get("files")
    if isinstance(files, list) and files and isinstance(files[0], dict) and "projectID" in files[0]:
        for row in files:
            if not isinstance(row, dict):
                continue
            pid = row.get("projectID")
            if pid is not None:
                cf_projects.add(str(int(pid)) if isinstance(pid, (int, float)) else str(pid).strip())
        notes.append("Forge-style manifest files[] with projectID.")
    elif isinstance(files, list) and obj.get("formatVersion") is not None:
        stems: Set[str] = set()
        for row in files:
            if not isinstance(row, dict):
                continue
            path = str(row.get("path") or "").replace("\\", "/")
            low = path.lower()
            if "mods/" in low or low.startswith("mods/"):
                stem = Path(path).stem.lower()
                if stem:
                    stems.add(stem.replace(" ", "_"))
        mod_ids |= stems
        notes.append("Modrinth-like index: jar stems from mods/ paths.")

    for key in ("mod_ids", "mods", "requiredMods"):
        block = obj.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, str):
                    mod_ids.add(_norm(item))
                elif isinstance(item, dict):
                    mid = item.get("mod_id") or item.get("modId") or item.get("slug") or item.get("id")
                    if mid:
                        mod_ids.add(_norm(str(mid)))
            notes.append(f"Also used `{key}` list.")

    note = " ".join(notes) if notes else "No recognized manifest sections."
    return mod_ids, cf_projects, note
