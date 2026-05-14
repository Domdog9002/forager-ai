"""Compare saved catalog pins to newest Modrinth / CurseForge files (manual refresh from UI)."""

from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING

if TYPE_CHECKING:
    from ..launcher.mod_downloader import ModDownloader


def _norm_id(v: Any) -> str:
    return str(v or "").strip()


def modrinth_pin_drift_status(*, pinned_version_id: str, newest_first_version_ids: List[str]) -> str:
    """Pure helper for tests: Modrinth `/version` list is newest-first in our client."""
    if not newest_first_version_ids:
        return "no_versions"
    head = newest_first_version_ids[0]
    if not pinned_version_id:
        return "no_pin"
    return "pinned_is_latest" if head == pinned_version_id else "newer_available"


def summarize_modrinth_pin_drift(
    downloader: "ModDownloader",
    pins: List[Dict[str, Any]],
    *,
    catalog_kind: str = "mods",
    max_pins: int = 40,
) -> List[Dict[str, Any]]:
    """Uses Modrinth listing (newest first). Caches by project id to avoid duplicate HTTP calls."""
    rows: List[Dict[str, Any]] = []
    cache: Dict[str, List[Any]] = {}
    n = 0
    cap = max(1, int(max_pins))
    for pin in pins:
        if n >= cap:
            break
        if not isinstance(pin, dict):
            continue
        if _norm_id(pin.get("source")).lower() != "modrinth":
            continue
        n += 1
        pid = _norm_id(pin.get("project_id"))
        pvid = _norm_id(pin.get("version_id"))
        if not pid:
            rows.append(
                {
                    "source": "modrinth",
                    "target_key": pin.get("target_key"),
                    "project_id": "",
                    "pinned_version_id": pvid,
                    "newest_version_id": "",
                    "newest_file": "",
                    "status": "bad_pin",
                    "channel": pin.get("channel"),
                }
            )
            continue
        if pid not in cache:
            cache[pid] = downloader.get_modrinth_versions(
                pid,
                None,
                None,
                filter_loader=False,
                catalog_kind=catalog_kind,
            )
        vs = cache[pid]
        ids = [str(getattr(m, "version_id", None) or getattr(m, "id", "") or "") for m in vs]
        st = modrinth_pin_drift_status(pinned_version_id=pvid, newest_first_version_ids=ids)
        newest = vs[0] if vs else None
        rows.append(
            {
                "source": "modrinth",
                "target_key": pin.get("target_key"),
                "project_id": pid,
                "pinned_version_id": pvid,
                "newest_version_id": _norm_id(getattr(newest, "version_id", None) if newest else ""),
                "newest_file": _norm_id(getattr(newest, "file_name", None) if newest else ""),
                "status": st if pvid else "no_pin",
                "channel": pin.get("channel"),
            }
        )
    return rows


def summarize_curseforge_pin_drift(
    downloader: "ModDownloader",
    pins: List[Dict[str, Any]],
    *,
    max_pins: int = 40,
) -> List[Dict[str, Any]]:
    """Requires CurseForge API key. Newest file from unfiltered listing vs pinned file id."""
    rows: List[Dict[str, Any]] = []
    cache: Dict[str, List[Dict[str, Any]]] = {}
    n = 0
    cap = max(1, int(max_pins))
    for pin in pins:
        if n >= cap:
            break
        if not isinstance(pin, dict):
            continue
        if _norm_id(pin.get("source")).lower() != "curseforge":
            continue
        n += 1
        pid = _norm_id(pin.get("project_id"))
        pfid = _norm_id(pin.get("version_id"))
        if not pid:
            rows.append(
                {
                    "source": "curseforge",
                    "target_key": pin.get("target_key"),
                    "project_id": "",
                    "pinned_file_id": pfid,
                    "newest_file_id": "",
                    "newest_file": "",
                    "status": "bad_pin",
                    "channel": pin.get("channel"),
                }
            )
            continue
        if pid not in cache:
            cache[pid] = downloader.list_curseforge_mod_files(
                pid,
                None,
                None,
                limit=50,
                use_loader=False,
            )
        files = cache[pid]
        if not files:
            rows.append(
                {
                    "source": "curseforge",
                    "target_key": pin.get("target_key"),
                    "project_id": pid,
                    "pinned_file_id": pfid,
                    "newest_file_id": "",
                    "newest_file": "",
                    "status": "no_key_or_no_files",
                    "channel": pin.get("channel"),
                }
            )
            continue
        top = files[0]
        nid = _norm_id(top.get("id"))
        fname = _norm_id(top.get("fileName"))
        st = "pinned_is_latest" if pfid and nid == pfid else ("newer_available" if pfid else "no_pin")
        rows.append(
            {
                "source": "curseforge",
                "target_key": pin.get("target_key"),
                "project_id": pid,
                "pinned_file_id": pfid,
                "newest_file_id": nid,
                "newest_file": fname,
                "status": st,
                "channel": pin.get("channel"),
            }
        )
    return rows
