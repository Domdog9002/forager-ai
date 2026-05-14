from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from ..fs.safe_writer import write_text_utf8_nobom


MANIFEST_FILENAME = "pack.manifest.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_default_manifest(
    pack_id: str,
    *,
    minecraft_version: str = "1.20.1",
    loader: str = "forge",
) -> Dict[str, Any]:
    return {
        "manifest_version": 1,
        "pack_id": pack_id,
        "minecraft_version": minecraft_version,
        "loader": loader,
        "mods": [],
        "configs": [],
        "assets": [],
        "compats": [],
        "generated_scripts": [],
        "history": [],
        "created_at": _utc_now_iso(),
        "updated_at": _utc_now_iso(),
    }


def manifest_path(pack_root: str) -> str:
    return f"{pack_root.rstrip('/\\')}/{MANIFEST_FILENAME}"


def load_pack_manifest(pack_root: str) -> Dict[str, Any]:
    path = manifest_path(pack_root)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"Pack manifest missing at {path!r}. Create a pack first or run manifest initialization."
        )


def save_pack_manifest(pack_root: str, manifest: Dict[str, Any]) -> None:
    path = manifest_path(pack_root)
    manifest = dict(manifest)
    manifest["updated_at"] = _utc_now_iso()
    write_text_utf8_nobom(path, json.dumps(manifest, indent=2, ensure_ascii=True))


def record_feature_applied(
    pack_root: str,
    *,
    feature_name: str,
    actions_count: int,
    changes: Dict[str, Any],
) -> None:
    manifest = load_pack_manifest(pack_root)
    manifest.setdefault("history", [])
    manifest["history"].append(
        {
            "timestamp": _utc_now_iso(),
            "event": "feature_applied",
            "feature_name": feature_name,
            "actions_count": actions_count,
            "changes": changes,
        }
    )
    save_pack_manifest(pack_root, manifest)


def register_compat_in_manifest(
    pack_root: str,
    *,
    rule_id: str,
    rule_name: str,
    affected_mods: list[str],
    description: str,
) -> None:
    manifest = load_pack_manifest(pack_root)
    manifest.setdefault("compats", [])

    existing_idx = None
    for idx, entry in enumerate(manifest["compats"]):
        if isinstance(entry, dict) and entry.get("rule_id") == rule_id:
            existing_idx = idx
            break

    payload = {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "affected_mods": affected_mods,
        "description": description,
        "updated_at": _utc_now_iso(),
    }
    if existing_idx is None:
        manifest["compats"].append(payload)
    else:
        manifest["compats"][existing_idx] = payload
    save_pack_manifest(pack_root, manifest)


def init_pack_manifest(
    pack_root: str,
    *,
    pack_id: Optional[str] = None,
    minecraft_version: str = "1.20.1",
    loader: str = "forge",
) -> Dict[str, Any]:
    path = manifest_path(pack_root)
    if os.path.exists(path):
        # Keep existing history; this helper is idempotent.
        return load_pack_manifest(pack_root)

    if pack_id is None:
        pack_id = pack_root.rstrip("/\\").split("\\")[-1].split("/")[-1]

    manifest = create_default_manifest(
        pack_id,
        minecraft_version=minecraft_version,
        loader=loader,
    )
    save_pack_manifest(pack_root, manifest)
    return manifest

