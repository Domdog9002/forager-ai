"""Resolve Minecraft version / loader from launcher sidecar JSON near a game root."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _parse_cf_loader(data: Dict[str, Any]) -> Tuple[str, str]:
    if bool(data.get("isVanilla")):
        return "vanilla", "vanilla"
    bml = data.get("baseModLoader")
    if not isinstance(bml, dict):
        return "unknown", "unknown"
    name = str(bml.get("name") or "")
    low = name.lower()
    if "neoforge" in low:
        return "neoforge", name
    if low.startswith("forge-"):
        return "forge", name
    if "fabric" in low:
        return "fabric", name
    if "quilt" in low:
        return "quilt", name
    return "unknown", name


def read_sidecar_launcher_versions(game_root: str) -> Dict[str, Any]:
    """
    Walk ``game_root`` and a few parents for CurseForge ``minecraftinstance.json``
    or Modrinth ``profile.json`` / ``modrinth.json``-style manifests.
    """
    out: Dict[str, Any] = {
        "minecraft_version": "",
        "loader": "",
        "loader_version": "",
        "source": "",
        "path": "",
    }
    try:
        p = Path(str(game_root or "").strip()).resolve()
    except OSError:
        return out

    candidates = [p]
    try:
        candidates.extend(list(p.parents)[:6])
    except (OSError, ValueError):
        pass

    for anc in candidates:
        cf = anc / "minecraftinstance.json"
        if cf.is_file():
            data = _read_json(cf)
            if not data:
                continue
            mc = str(data.get("gameVersion") or data.get("minecraftVersion") or "").strip()
            loader, lver = _parse_cf_loader(data)
            out.update(
                {
                    "minecraft_version": mc,
                    "loader": loader,
                    "loader_version": lver,
                    "source": "curseforge_json",
                    "path": str(cf),
                }
            )
            return out
        for name in ("profile.json", "modrinth.json"):
            mr = anc / name
            if not mr.is_file():
                continue
            data = _read_json(mr)
            if not data:
                continue
            mc = str(
                data.get("game_version")
                or data.get("gameVersion")
                or data.get("minecraft_version")
                or ""
            ).strip()
            loader = "unknown"
            lver = "unknown"
            modloaders = data.get("modloaders") or data.get("loaders") or data.get("loaderVersions")
            if isinstance(modloaders, list) and modloaders:
                first = modloaders[0]
                if isinstance(first, dict):
                    raw = first.get("type") or first.get("id") or first.get("loader")
                    loader = str(raw or "unknown").lower()
                    lver = str(first.get("version") or first.get("name") or "unknown")
                elif isinstance(first, str):
                    loader, _, rest = first.partition("-")
                    lver = rest or first
            out.update(
                {
                    "minecraft_version": mc,
                    "loader": loader,
                    "loader_version": lver,
                    "source": "modrinth_json",
                    "path": str(mr),
                }
            )
            return out

    return out
