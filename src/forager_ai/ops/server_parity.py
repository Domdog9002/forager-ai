"""Compare local mod ids against a pasted server manifest or mod-id list."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .mods_folder_lockfile import build_game_root_mods_lock


def _norm_mod_id(s: str) -> str:
    t = (s or "").strip().lower()
    if ":" in t:
        t = t.split(":", 1)[-1].strip()
    return t


def parse_server_modlist_blob(text: str) -> Set[str]:
    """Split on newlines and commas; strip ``#`` comments; accept bare ids or ``mods/foo.jar`` stems."""
    out: Set[str] = set()
    if not text:
        return out
    chunk = text.replace("\r\n", "\n").replace(",", "\n")
    for line in chunk.split("\n"):
        s = line.split("#", 1)[0].strip()
        if not s:
            continue
        if s.lower().endswith(".jar"):
            s = Path(s).stem
        mid = _norm_mod_id(s)
        if mid:
            out.add(mid)
    return out


def parse_server_manifest_json(raw: str) -> Tuple[Set[str], str]:
    """
    Best-effort parse of a small JSON manifest (Forge ``mods.toml`` export, custom list, or lock-like).

    Returns ``(ids, note)``.
    """
    note = ""
    ids: Set[str] = set()
    raw = (raw or "").strip()
    if not raw:
        return ids, "Empty JSON."
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError as exc:
        return set(), f"Invalid JSON: {exc}"

    if isinstance(obj, list):
        for item in obj:
            if isinstance(item, str):
                ids.update(parse_server_modlist_blob(item))
            elif isinstance(item, dict):
                mid = item.get("mod_id") or item.get("modId") or item.get("id") or item.get("slug")
                if mid:
                    ids.add(_norm_mod_id(str(mid)))
        note = "Parsed JSON array."
        return ids, note

    if not isinstance(obj, dict):
        return set(), "JSON root must be object or array."

    for key in ("mod_ids", "mods", "requiredMods", "jars"):
        block = obj.get(key)
        if isinstance(block, list):
            for item in block:
                if isinstance(item, str):
                    ids.update(parse_server_modlist_blob(item))
                elif isinstance(item, dict):
                    mid = item.get("mod_id") or item.get("modId") or item.get("id") or item.get("slug")
                    rel = item.get("rel") or item.get("file")
                    if mid:
                        ids.add(_norm_mod_id(str(mid)))
                    elif rel:
                        ids.update(parse_server_modlist_blob(str(rel)))
            note = f"Used `{key}` array."
            return ids, note

    return set(), "No known `mod_ids`, `mods`, `requiredMods`, or `jars` field found in JSON object."


def client_mod_ids_from_game_root(game_root: str) -> Tuple[Set[str], str]:
    """Prefer ``forager_mods.lock.json`` mod_id rows; else live ``mods/`` scan."""
    root = Path(str(game_root or "").strip())
    lock_path = root / "forager_mods.lock.json"
    if lock_path.is_file():
        try:
            data = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            data = {}
        jars = data.get("jars") if isinstance(data.get("jars"), list) else []
        ids: Set[str] = set()
        for j in jars:
            if isinstance(j, dict):
                mid = _norm_mod_id(str(j.get("mod_id") or ""))
                if mid:
                    ids.add(mid)
        return ids, "forager_mods.lock.json"

    snap = build_game_root_mods_lock(str(root))
    jars = snap.get("jars") if isinstance(snap.get("jars"), list) else []
    ids = {
        _norm_mod_id(str(j.get("mod_id") or ""))
        for j in jars
        if isinstance(j, dict) and _norm_mod_id(str(j.get("mod_id") or ""))
    }
    return ids, "live mods/ scan"


def compare_server_parity(
    game_root: str,
    *,
    server_text: str = "",
    server_json: str = "",
    manifest_json: str = "",
) -> Dict[str, Any]:
    """Return ``only_on_server``, ``only_on_client``, ``intersection``, and notes."""
    server_ids = parse_server_modlist_blob(server_text)
    jnote = ""
    if (server_json or "").strip():
        jids, jnote = parse_server_manifest_json(server_json)
        server_ids |= jids

    mf_note = ""
    curse_ids: List[str] = []
    if (manifest_json or "").strip():
        from .server_manifest import extract_from_manifest_json

        mids, cfids, mf_note = extract_from_manifest_json(manifest_json)
        server_ids |= mids
        curse_ids = sorted(cfids, key=str.lower)

    client_ids, client_source = client_mod_ids_from_game_root(game_root)
    only_server = sorted(server_ids - client_ids)
    only_client = sorted(client_ids - server_ids)
    common = sorted(client_ids & server_ids)
    warnings: List[str] = []
    if not server_ids and not curse_ids:
        warnings.append("Server list is empty — paste mod ids, JSON, or a pack/server manifest.")
    if not client_ids:
        warnings.append("No client mod ids resolved (empty lock metadata or missing mods/).")
    if jnote and (server_json or "").strip():
        warnings.append(jnote)
    if mf_note and (manifest_json or "").strip():
        warnings.append(mf_note)

    return {
        "game_root": str(game_root).strip(),
        "client_id_source": client_source,
        "client_mod_id_count": len(client_ids),
        "server_mod_id_count": len(server_ids),
        "server_curseforge_project_ids": curse_ids,
        "intersection_count": len(common),
        "only_on_server": only_server,
        "only_on_client": only_client,
        "intersection_sample": common[:80],
        "warnings": warnings,
    }
