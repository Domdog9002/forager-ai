"""JSON-backed queue of pending AI feature plans for the Approvals Inbox."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_VERSION = 1


def _store_path() -> Path:
    return Path.home() / ".forager_ai" / "approvals_inbox.json"


def _load_raw() -> Dict[str, Any]:
    p = _store_path()
    if not p.is_file():
        return {"version": _VERSION, "items": []}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"version": _VERSION, "items": []}
        data.setdefault("version", _VERSION)
        items = data.get("items") or []
        data["items"] = [i for i in items if isinstance(i, dict)]
        return data
    except (OSError, json.JSONDecodeError, TypeError):
        return {"version": _VERSION, "items": []}


def _save_raw(data: Dict[str, Any]) -> None:
    p = _store_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, ensure_ascii=True), encoding="utf-8")


def list_items(*, include_terminal: bool = False) -> List[Dict[str, Any]]:
    items = list(_load_raw().get("items") or [])
    if include_terminal:
        return items
    return [i for i in items if str(i.get("status") or "pending") == "pending"]


def pending_count() -> int:
    return len(list_items(include_terminal=False))


def upsert_pending(
    plan: Dict[str, Any],
    *,
    pack_root: str,
    source_nav: str,
    title: str,
    plan_fp: str,
) -> None:
    """Replace any existing pending row with the same pack + plan fingerprint."""
    data = _load_raw()
    items: List[Dict[str, Any]] = list(data.get("items") or [])
    pack_n = os.path.normpath(str(pack_root or ""))
    items = [
        i
        for i in items
        if not (
            str(i.get("status") or "") == "pending"
            and str(i.get("plan_fp") or "") == plan_fp
            and os.path.normpath(str(i.get("pack_root") or "")) == pack_n
        )
    ]
    items.append(
        {
            "id": str(uuid.uuid4()),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "pending",
            "source_nav": str(source_nav or "")[:80],
            "title": str(title or "Feature plan")[:500],
            "pack_root": pack_n,
            "plan_fp": str(plan_fp)[:80],
            "plan": plan,
        }
    )
    data["items"] = items
    _save_raw(data)


def set_status(item_id: str, status: str) -> bool:
    data = _load_raw()
    ok = False
    for i in data.get("items") or []:
        if str(i.get("id")) == str(item_id):
            i["status"] = str(status)
            i["updated_at"] = datetime.now(timezone.utc).isoformat()
            ok = True
            break
    if ok:
        _save_raw(data)
    return ok


def get_item(item_id: str) -> Optional[Dict[str, Any]]:
    for i in _load_raw().get("items") or []:
        if str(i.get("id")) == str(item_id):
            return i
    return None
