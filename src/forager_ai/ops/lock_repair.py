"""Suggest re-download actions from lock verify + install provenance (Modrinth MVP)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from ..launcher.install_provenance import read_install_provenance_tail
from ..launcher.mod_downloader import ModDownloader


def _basename(rel: str) -> str:
    return Path(str(rel or "").replace("\\", "/")).name.lower()


def _index_provenance(records: Sequence[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Last-write-wins index by lowercased file_name."""
    by_fn: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        if not isinstance(rec, dict):
            continue
        fn = str(rec.get("file_name") or "").strip().lower()
        if fn:
            by_fn[fn] = rec
    return by_fn


def build_lock_repair_suggestions(
    game_root: str,
    verify_report: Dict[str, Any],
    *,
    cache_dir: str,
    provenance_max_lines: int = 2500,
) -> List[Dict[str, Any]]:
    """
    For ``missing_on_disk`` / ``hash_mismatch`` lock rows, match recent provenance by jar basename.

    Each suggestion may include ``provenance`` with ``source``, ``project_id``, ``version_id`` for Modrinth replay.
    """
    if not isinstance(verify_report, dict) or not verify_report.get("ok"):
        return []
    prov = read_install_provenance_tail(cache_dir, max_lines=int(provenance_max_lines))
    by_fn = _index_provenance(prov)
    out: List[Dict[str, Any]] = []

    for rel in verify_report.get("missing_on_disk") or []:
        if not rel:
            continue
        bn = _basename(str(rel))
        rec = by_fn.get(bn)
        row: Dict[str, Any] = {"kind": "missing_on_disk", "rel": str(rel), "basename": bn, "provenance": rec}
        if rec and str(rec.get("source") or "").lower() == "modrinth":
            row["modrinth_version_url"] = (
                f"https://api.modrinth.com/v2/version/{rec.get('version_id')}" if rec.get("version_id") else ""
            )
            row["modrinth_project_url"] = (
                f"https://modrinth.com/mod/{rec.get('project_id')}" if rec.get("project_id") else ""
            )
        out.append(row)

    for hm in verify_report.get("hash_mismatch") or []:
        if not isinstance(hm, dict):
            continue
        rel = str(hm.get("rel") or "")
        if not rel:
            continue
        bn = _basename(rel)
        rec = by_fn.get(bn)
        row = {
            "kind": "hash_mismatch",
            "rel": rel,
            "basename": bn,
            "sha256_lock": hm.get("sha256_lock"),
            "sha256_disk": hm.get("sha256_disk"),
            "provenance": rec,
        }
        if rec and str(rec.get("source") or "").lower() == "modrinth":
            row["modrinth_version_url"] = (
                f"https://api.modrinth.com/v2/version/{rec.get('version_id')}" if rec.get("version_id") else ""
            )
        out.append(row)

    return out


def try_modrinth_redownload_for_rel(
    md: ModDownloader,
    *,
    game_root: str,
    suggestion: Dict[str, Any],
    catalog_kind: str = "mods",
) -> Optional[str]:
    """
    If suggestion has Modrinth provenance with ``version_id``, re-download primary file into ``game_root/mods``.

    Returns destination path or None.
    """
    rec = suggestion.get("provenance")
    if not isinstance(rec, dict):
        return None
    if str(rec.get("source") or "").lower() != "modrinth":
        return None
    vid = str(rec.get("version_id") or "").strip()
    if not vid:
        return None
    info = md.get_modrinth_version_by_id(vid, catalog_kind=catalog_kind)
    if not info or not info.download_url:
        return None
    dest_dir = os.path.join(str(game_root), "mods")
    return md.download_mod(info, dest_dir)
