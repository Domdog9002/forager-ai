"""Persist user dismissals of resolver conflict ids under ``.forager/``."""

from __future__ import annotations

import json
import os
from typing import Set


def _dismissals_path(pack_root: str) -> str:
    return os.path.join(str(pack_root or "").strip(), ".forager", "scan_dismissals.json")


def load_dismissed_conflict_ids(pack_root: str) -> Set[str]:
    path = _dismissals_path(pack_root)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError, TypeError):
        return set()
    if isinstance(data, dict):
        raw = data.get("conflict_ids")
        if isinstance(raw, list):
            return {str(x).strip() for x in raw if str(x).strip()}
    if isinstance(data, list):
        return {str(x).strip() for x in data if str(x).strip()}
    return set()


def dismiss_conflict_id(pack_root: str, conflict_id: str) -> None:
    cid = str(conflict_id or "").strip()
    if not cid:
        return
    root = str(pack_root or "").strip()
    d = os.path.join(root, ".forager")
    os.makedirs(d, exist_ok=True)
    path = _dismissals_path(root)
    cur = load_dismissed_conflict_ids(root)
    cur.add(cid)
    payload = {"conflict_ids": sorted(cur)}
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)


def undismiss_conflict_id(pack_root: str, conflict_id: str) -> None:
    cid = str(conflict_id or "").strip()
    root = str(pack_root or "").strip()
    cur = load_dismissed_conflict_ids(root)
    cur.discard(cid)
    path = _dismissals_path(root)
    if not cur:
        try:
            os.remove(path)
        except OSError:
            pass
        return
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"conflict_ids": sorted(cur)}, fh, indent=2, ensure_ascii=True)


def dismissals_file_mtime(pack_root: str) -> float:
    path = _dismissals_path(pack_root)
    try:
        return float(os.path.getmtime(path))
    except OSError:
        return 0.0
