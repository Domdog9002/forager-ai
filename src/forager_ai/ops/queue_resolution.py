"""Lightweight Modrinth install-queue summary (project metadata + strict file match count)."""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

from ..launcher.mod_downloader import ModInfo
from ..launcher.version_hints import rank_modrinth_versions

if TYPE_CHECKING:
    from ..launcher.launcher_core import LauncherCore
    from ..launcher.mod_downloader import ModDownloader



def summarize_modrinth_install_queue(
    downloader: "ModDownloader",
    queue_rows: List[Dict[str, Any]],
    *,
    minecraft_version: str,
    loader: str,
    catalog_kind: str = "mods",
    max_items: int = 14,
) -> List[Dict[str, Any]]:
    """One row per queue entry: title, strict version hits, optional relaxed preview (no install)."""
    out: List[Dict[str, Any]] = []
    cap = max(1, int(max_items))
    mc = (minecraft_version or "").strip() or None
    lo = (loader or "").strip().lower() or None
    if lo == "vanilla":
        lo = "forge"
    n = 0
    for row in queue_rows:
        if n >= cap:
            break
        if not isinstance(row, dict):
            continue
        if str(row.get("source", "modrinth")).lower() != "modrinth":
            continue
        pid = str(row.get("project_id") or "").strip()
        if not pid:
            continue
        n += 1
        detail = downloader.get_modrinth_project_detail(pid)
        title = str((detail or {}).get("title") or pid)
        purl = str((detail or {}).get("project_url") or "").strip()
        strict = downloader.get_modrinth_versions(
            pid,
            minecraft_version=mc,
            loader=lo,
            filter_loader=True,
            catalog_kind=catalog_kind,
        )
        relaxed = False
        preview = strict[:3] if strict else []
        if not strict:
            loose = downloader.get_modrinth_versions(
                pid,
                None,
                None,
                filter_loader=False,
                catalog_kind=catalog_kind,
            )
            relaxed = bool(loose)
            preview = loose[:3]
        out.append(
            {
                "project_id": pid,
                "title": title[:120],
                "project_url": purl[:300],
                "strict_matches": len(strict),
                "used_relaxed_preview": relaxed,
                "preview_files": ", ".join(str(getattr(m, "file_name", "") or "") for m in preview if m)[:200],
            }
        )
    return out


def catalog_pin_version_id(
    config: Dict[str, Any], target_key: str, source: str, project_id: str
) -> Optional[str]:
    """Match dashboard pin lookup: target_key + source + project_id → version_id."""
    for p in config.get("catalog_pins") or []:
        if not isinstance(p, dict):
            continue
        if str(p.get("target_key")) != target_key:
            continue
        if str(p.get("source", "")).lower() != str(source).lower():
            continue
        if str(p.get("project_id", "")).strip() != str(project_id).strip():
            continue
        vid = str(p.get("version_id") or "").strip()
        return vid or None
    return None


def pick_modrinth_install_candidate(
    downloader: Any,
    project_id: str,
    *,
    minecraft_version: Optional[str],
    loader: Optional[str],
    catalog_kind: str = "mods",
    pinned_version_id: Optional[str] = None,
    allow_relaxed_fallback: bool = True,
) -> Tuple[Optional[ModInfo], str, bool]:
    """
    Resolve a single Modrinth file for install (mirrors Browse Modpacks row install).

    Returns (chosen, error_or_empty, used_relaxed_fallback).
    """
    pid = str(project_id or "").strip()
    if not pid:
        return None, "empty_project_id", False
    ck = (catalog_kind or "mods").strip().lower()
    mr_fl = ck in ("mods", "modpack")
    mc = (minecraft_version or "").strip() or None
    lo = (loader or "").strip().lower() or None
    if lo == "vanilla":
        lo = "forge"
    versions_strict = downloader.get_modrinth_versions(
        pid,
        minecraft_version=mc,
        loader=lo,
        filter_loader=mr_fl,
        catalog_kind=ck,
    )
    versions = list(versions_strict)
    used_relaxed = False
    if not versions and allow_relaxed_fallback:
        versions = downloader.get_modrinth_versions(
            pid,
            None,
            None,
            filter_loader=False,
            catalog_kind=ck,
        )[:80]
        used_relaxed = bool(versions)
    if not versions:
        return None, "no_modrinth_file", False
    ranked = rank_modrinth_versions(
        versions,
        want_mc=str(mc or ""),
        want_loader=lo,
    )
    chosen = ranked[0]
    if pinned_version_id:
        pin = str(pinned_version_id).strip()
        hit = next(
            (v for v in ranked if str(v.version_id) == pin or str(v.id) == pin),
            None,
        )
        if hit:
            chosen = hit
    return chosen, "", used_relaxed


def run_modrinth_install_queue(
    launcher: "LauncherCore",
    queue_rows: List[Dict[str, Any]],
    *,
    packs_dir: str,
    minecraft_version: str,
    loader: str,
    catalog_kind: str,
    target_key: str,
    install_target_is_instance: bool,
    instance_name: Optional[str],
    pack_name: Optional[str],
    external_game_root: Optional[str],
    install_dependencies: bool,
    allow_preflight_warn: bool,
    allow_relaxed_fallback: bool,
    max_items: int = 14,
) -> List[Dict[str, Any]]:
    """
    Install Modrinth projects from the session queue in order.

    Skips preflight **block** always; skips **warn** unless allow_preflight_warn.
    """
    downloader = launcher.mod_downloader
    ck = (catalog_kind or "mods").strip().lower()
    deps = bool(install_dependencies) and ck == "mods"
    cap = max(1, int(max_items))
    out: List[Dict[str, Any]] = []
    n = 0
    for row in queue_rows:
        if n >= cap:
            break
        if not isinstance(row, dict):
            continue
        if str(row.get("source", "modrinth")).lower() != "modrinth":
            continue
        pid = str(row.get("project_id") or "").strip()
        if not pid:
            continue
        n += 1
        detail = downloader.get_modrinth_project_detail(pid)
        title = str((detail or {}).get("title") or pid)[:160]
        pvid = catalog_pin_version_id(launcher.config, target_key, "modrinth", pid)
        chosen, err, relaxed = pick_modrinth_install_candidate(
            downloader,
            pid,
            minecraft_version=minecraft_version,
            loader=loader,
            catalog_kind=catalog_kind,
            pinned_version_id=pvid,
            allow_relaxed_fallback=allow_relaxed_fallback,
        )
        base: Dict[str, Any] = {
            "project_id": pid,
            "title": title,
            "used_relaxed_fallback": relaxed,
        }
        if err:
            out.append({**base, "status": "skipped_no_file", "detail": err})
            continue

        pf_decision = "allow"
        if ck == "mods" and not external_game_root:
            if install_target_is_instance and instance_name:
                pf = launcher.preflight_instance_install(instance_name, chosen)
                pf_decision = str(pf.get("decision") or "allow")
            elif pack_name:
                root = os.path.join(str(packs_dir), str(pack_name))
                pf = launcher.preflight_catalog_install(root, chosen, pack_name=str(pack_name))
                pf_decision = str(pf.get("decision") or "allow")
            else:
                out.append({**base, "status": "skipped_no_preflight_target", "detail": "no_instance_or_pack"})
                continue

            if pf_decision == "block":
                out.append({**base, "status": "skipped_preflight_block", "detail": "preflight_block"})
                continue
            if pf_decision == "warn" and not allow_preflight_warn:
                out.append({**base, "status": "skipped_preflight_warn", "detail": "preflight_warn"})
                continue

        ok = False
        if external_game_root:
            ok = launcher.install_catalog_into_pack(
                external_game_root,
                chosen,
                catalog_kind=ck,
                install_dependencies=deps,
            )
        elif install_target_is_instance and instance_name:
            ok = launcher.install_catalog_item(
                instance_name,
                chosen,
                catalog_kind=ck,
                install_dependencies=deps,
            )
        elif pack_name:
            root = os.path.join(str(packs_dir), str(pack_name))
            ok = launcher.install_catalog_into_pack(
                root,
                chosen,
                catalog_kind=ck,
                install_dependencies=deps,
            )
        else:
            out.append({**base, "status": "failed", "detail": "no_install_target"})
            continue

        if ok:
            out.append(
                {
                    **base,
                    "status": "installed",
                    "detail": str(chosen.file_name or chosen.name or ""),
                }
            )
        else:
            out.append({**base, "status": "install_failed", "detail": "download_or_write_failed"})
    return out
