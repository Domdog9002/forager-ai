"""
Discover Minecraft instances managed by CurseForge and Modrinth App (Theseus).

Forager reads metadata from disk only (no launcher APIs). Install targets share the same
folder layout as a normal Java instance (mods/, resourcepacks/, … under ``game_root``).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple


@dataclass(frozen=True)
class ExternalInstanceInfo:
    source: str  # curseforge | modrinth
    stable_id: str
    display_name: str
    game_root: str
    minecraft_version: str
    loader: str
    loader_version: str
    last_played: Optional[str] = None


def default_curseforge_instances_root() -> Path:
    return Path.home() / "curseforge" / "minecraft" / "Instances"


def default_modrinth_profiles_root() -> Path:
    appdata = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "com.modrinth.theseus" / "profiles"


def reveal_path_in_file_manager(path: str) -> bool:
    """Open a directory (or a file's parent folder) in the OS file manager."""
    expanded = os.path.normpath(os.path.expandvars(os.path.expanduser(str(path).strip())))
    if not expanded:
        return False
    if os.path.isdir(expanded):
        target = expanded
    else:
        parent = os.path.dirname(expanded)
        if parent and os.path.isdir(parent):
            target = parent
        else:
            return False
    try:
        if os.name == "nt":
            try:
                os.startfile(target)  # type: ignore[attr-defined]
            except OSError:
                subprocess.Popen(["explorer", target])
        elif sys.platform == "darwin":
            subprocess.run(["open", target], check=False, timeout=30)
        else:
            subprocess.run(["xdg-open", target], check=False, timeout=30)
        return True
    except OSError:
        return False


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def _parse_curseforge_loader(base_mod_loader: Any, is_vanilla: bool) -> Tuple[str, str]:
    if is_vanilla:
        return "vanilla", "vanilla"
    if not isinstance(base_mod_loader, dict):
        return "unknown", "unknown"
    name = str(base_mod_loader.get("name") or "")
    low = name.lower()
    if "neoforge" in low:
        return "neoforge", name
    if low.startswith("forge-"):
        tail = name[6:] if name.lower().startswith("forge-") else name
        return "forge", tail
    if "fabric" in low:
        return "fabric", name
    if "quilt" in low:
        return "quilt", name
    return "unknown", name


def discover_curseforge_instances(instances_root: Optional[str] = None) -> List[ExternalInstanceInfo]:
    root = Path(instances_root).expanduser() if instances_root else default_curseforge_instances_root()
    if not root.is_dir():
        return []
    found: List[ExternalInstanceInfo] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        meta = child / "minecraftinstance.json"
        if not meta.is_file():
            continue
        data = _read_json(meta)
        if not data:
            continue
        display = str(data.get("name") or child.name)
        raw_install = data.get("installPath")
        if raw_install:
            game_root = Path(str(raw_install))
        else:
            game_root = child
        try:
            game_root = game_root.resolve()
        except OSError:
            game_root = Path(str(game_root))
        if not game_root.is_dir():
            continue
        mc_ver = str(data.get("gameVersion") or data.get("minecraftVersion") or "unknown")
        loader, loader_ver = _parse_curseforge_loader(data.get("baseModLoader"), bool(data.get("isVanilla")))
        last = data.get("lastPlayed") or data.get("last_played")
        last_s = str(last) if last not in (None, "") else None
        sid = f"cf:{child.name}"
        found.append(
            ExternalInstanceInfo(
                source="curseforge",
                stable_id=sid,
                display_name=display,
                game_root=str(game_root),
                minecraft_version=mc_ver,
                loader=loader,
                loader_version=loader_ver,
                last_played=last_s,
            )
        )
    return found


def _parse_modrinth_profile_json(data: Dict[str, Any], fallback_name: str, game_root: Path) -> ExternalInstanceInfo:
    name = str(data.get("name") or data.get("profile_name") or fallback_name)
    mc_ver = str(
        data.get("game_version")
        or data.get("gameVersion")
        or data.get("minecraft_version")
        or "unknown"
    )
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
    sid = f"mr:{fallback_name}"
    return ExternalInstanceInfo(
        source="modrinth",
        stable_id=sid,
        display_name=name,
        game_root=str(game_root),
        minecraft_version=mc_ver,
        loader=loader,
        loader_version=lver,
        last_played=None,
    )


def _curseforge_scan_instance_roots(extra_roots: Optional[Sequence[str]] = None) -> List[Path]:
    roots: List[Path] = []

    def _norm_key(pth: Path) -> str:
        try:
            return os.path.normcase(str(pth.resolve()))
        except OSError:
            return os.path.normcase(str(pth))

    keys: set[str] = set()
    for raw in (extra_roots or []):
        s = str(raw or "").strip()
        if not s:
            continue
        try:
            p = Path(os.path.expandvars(os.path.expanduser(s)))
        except Exception:
            continue
        if p.is_dir():
            k = _norm_key(p)
            if k not in keys:
                keys.add(k)
                roots.append(p)
    d = default_curseforge_instances_root()
    if d.is_dir():
        k = _norm_key(d)
        if k not in keys:
            keys.add(k)
            roots.insert(0, d)
    la = os.environ.get("LOCALAPPDATA")
    if la:
        cand = Path(la) / "curseforge" / "minecraft" / "Instances"
        if cand.is_dir():
            nk = _norm_key(cand)
            if nk not in keys:
                keys.add(nk)
                roots.append(cand)
    try:
        doc = Path.home() / "Documents" / "curseforge" / "minecraft" / "Instances"
        if doc.is_dir():
            nk = _norm_key(doc)
            if nk not in keys:
                keys.add(nk)
                roots.append(doc)
    except OSError:
        pass
    return roots


def curseforge_lookup_stable_id_by_game_root(
    game_root: str,
    extra_roots: Optional[Sequence[str]] = None,
) -> Optional[str]:
    """
    Return ``cf:<InstanceFolder>`` by matching ``game_root`` to CurseForge discovery.

    Older Forager rows can have ``linked_source=curseforge`` but no ``linked_external_id``;
    without this, we never load ``minecraftinstance.json`` from the Instances folder.
    """
    if not (game_root or "").strip():
        return None
    try:
        tgt = Path(os.path.normpath(os.path.expandvars(os.path.expanduser(str(game_root)))))
    except OSError:
        return None
    try:
        target_resolved = os.path.normcase(str(tgt.resolve()))
    except OSError:
        target_resolved = os.path.normcase(os.path.normpath(str(tgt)))
    target_plain = os.path.normcase(os.path.normpath(str(game_root).strip()))

    for scan_root in _curseforge_scan_instance_roots(extra_roots):
        try:
            exts = discover_curseforge_instances(str(scan_root))
        except OSError:
            continue
        for ext in exts:
            try:
                gr = Path(os.path.normpath(os.path.expandvars(os.path.expanduser(str(ext.game_root)))))
                gr_key = os.path.normcase(str(gr.resolve()))
            except OSError:
                gr_key = os.path.normcase(os.path.normpath(str(ext.game_root)))
            if gr_key == target_resolved or gr_key == target_plain:
                return ext.stable_id
    return None


def curseforge_minecraftinstance_by_linked_id(
    linked_external_id: str,
    extra_roots: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load ``minecraftinstance.json`` using the discovery stable id ``cf:<CurseInstanceFolderName>``.

    Path-based matching (``curseforge_metadata_for_game_root``) often fails on Windows when
    ``installPath`` and Forager's ``instance_path`` differ slightly; the Instance folder id is reliable.
    """
    sid = str(linked_external_id or "").strip()
    if not sid.startswith("cf:"):
        return None
    folder = sid[3:].strip()
    if not folder:
        return None
    for scan_root in _curseforge_scan_instance_roots(extra_roots):
        meta = scan_root / folder / "minecraftinstance.json"
        if meta.is_file():
            data = _read_json(meta)
            if data:
                return data
    return None


def curseforge_metadata_for_game_root(
    game_root: str,
    extra_roots: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """
    Load minecraftinstance.json for a CurseForge install folder.

    The JSON often lives under .../Instances/<Name>/ while installPath points at the same or
    another folder, so we scan the default CurseForge Instances tree and match resolved paths.
    """
    if not (game_root or "").strip():
        return None
    try:
        target = Path(os.path.normpath(os.path.expandvars(os.path.expanduser(str(game_root)))))
    except Exception:
        return None
    try:
        resolved_target = target.resolve()
    except OSError:
        resolved_target = target
    target_key = os.path.normcase(str(resolved_target))

    for scan_root in _curseforge_scan_instance_roots(extra_roots):
        if not scan_root.is_dir():
            continue
        for child in sorted(scan_root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            meta = child / "minecraftinstance.json"
            if not meta.is_file():
                continue
            data = _read_json(meta)
            if not data:
                continue
            raw_install = data.get("installPath")
            if raw_install:
                try:
                    gr = Path(str(raw_install)).expanduser()
                    gr_res = gr.resolve()
                except OSError:
                    gr_res = Path(str(raw_install))
            else:
                try:
                    gr_res = child.resolve()
                except OSError:
                    gr_res = child
            if os.path.normcase(str(gr_res)) == target_key:
                return data
            # Fallback: same path without resolve() (junctions / mixed normalisation).
            if raw_install:
                try:
                    gr_plain = Path(str(raw_install)).expanduser()
                    if os.path.normcase(os.path.normpath(str(gr_plain))) == os.path.normcase(
                        os.path.normpath(str(target))
                    ):
                        return data
                except OSError:
                    pass
    return None


def _modrinth_scan_profile_roots(extra_roots: Optional[Sequence[str]] = None) -> List[Path]:
    roots: List[Path] = []
    for raw in (extra_roots or []):
        s = str(raw or "").strip()
        if not s:
            continue
        try:
            p = Path(os.path.expandvars(os.path.expanduser(s)))
        except Exception:
            continue
        if p.is_dir():
            roots.append(p)
    d = default_modrinth_profiles_root()
    if d.is_dir() and d not in roots:
        roots.insert(0, d)
    return roots


def modrinth_profile_for_game_root(
    game_root: str,
    extra_roots: Optional[Sequence[str]] = None,
) -> Optional[Dict[str, Any]]:
    """Locate profile.json whose game folder matches this install path (Theseus / Modrinth app)."""
    if not (game_root or "").strip():
        return None
    try:
        target = Path(os.path.normpath(os.path.expandvars(os.path.expanduser(str(game_root)))))
    except Exception:
        return None
    try:
        resolved_target = target.resolve()
    except OSError:
        resolved_target = target
    target_key = os.path.normcase(str(resolved_target))

    for scan_root in _modrinth_scan_profile_roots(extra_roots):
        if not scan_root.is_dir():
            continue
        for child in sorted(scan_root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            pj = child / "profile.json"
            if not pj.is_file():
                continue
            data = _read_json(pj)
            if not data:
                continue
            path_raw = (
                data.get("path")
                or data.get("game_path")
                or data.get("gamePath")
                or data.get("dir")
                or data.get("game_dir")
            )
            if not path_raw:
                continue
            try:
                gp = Path(str(path_raw)).expanduser()
                g_res = gp.resolve()
            except OSError:
                g_res = Path(str(path_raw))
            if os.path.normcase(str(g_res)) == target_key:
                return data
    return None


def discover_modrinth_profiles(profiles_root: Optional[str] = None) -> List[ExternalInstanceInfo]:
    root = Path(profiles_root).expanduser() if profiles_root else default_modrinth_profiles_root()
    if not root.is_dir():
        return []
    found: List[ExternalInstanceInfo] = []
    for child in sorted(root.iterdir(), key=lambda p: p.name.lower()):
        if not child.is_dir():
            continue
        pj = child / "profile.json"
        try:
            resolved = child.resolve()
        except OSError:
            resolved = child
        if pj.is_file():
            data = _read_json(pj)
            if data:
                found.append(_parse_modrinth_profile_json(data, child.name, resolved))
                continue
        if (child / "mods").is_dir():
            found.append(
                ExternalInstanceInfo(
                    source="modrinth",
                    stable_id=f"mr:{child.name}",
                    display_name=child.name,
                    game_root=str(resolved),
                    minecraft_version="unknown",
                    loader="unknown",
                    loader_version="unknown",
                    last_played=None,
                )
            )
    return found


def discover_external_instances(config: Dict[str, Any]) -> List[ExternalInstanceInfo]:
    cf_root = (config.get("curseforge_instances_root") or "").strip()
    mr_root = (config.get("modrinth_profiles_root") or "").strip()
    return discover_curseforge_instances(cf_root or None) + discover_modrinth_profiles(mr_root or None)
