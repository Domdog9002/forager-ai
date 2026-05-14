"""Local-only reminder / cadence checklist stored beside launcher config."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _path(launcher_dir: str | Path) -> Path:
    return Path(str(launcher_dir)) / "task_reminders.json"


def load_reminders(launcher_dir: str | Path) -> Dict[str, Any]:
    p = _path(launcher_dir)
    if not p.is_file():
        return {"items": []}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"items": []}
    if not isinstance(raw, dict):
        return {"items": []}
    items = raw.get("items")
    if not isinstance(items, list):
        raw["items"] = []
    return raw


def save_reminders(launcher_dir: str | Path, data: Dict[str, Any]) -> None:
    p = _path(launcher_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    items = data.get("items")
    if not isinstance(items, list):
        data = {"items": []}
    with open(p, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=True)


def overdue_items(data: Dict[str, Any], *, now: datetime | None = None) -> List[Dict[str, Any]]:
    """Items where ``last_done_iso`` is older than ``cadence_days`` (or never done)."""
    now = now or datetime.now(timezone.utc)
    out: List[Dict[str, Any]] = []
    items = data.get("items") if isinstance(data.get("items"), list) else []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()
        if not title:
            continue
        try:
            cadence = max(1, int(it.get("cadence_days") or 7))
        except (TypeError, ValueError):
            cadence = 7
        last = str(it.get("last_done_iso") or "").strip()
        if not last:
            out.append({**it, "_due": True, "_reason": "never marked done"})
            continue
        try:
            parsed = datetime.fromisoformat(last.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            out.append({**it, "_due": True, "_reason": "invalid last_done_iso"})
            continue
        delta_days = (now - parsed.astimezone(timezone.utc)).total_seconds() / 86400.0
        if delta_days >= float(cadence):
            out.append({**it, "_due": True, "_reason": f"{int(delta_days)}d since last done (cadence {cadence}d)"})
    return out


def mark_reminder_done_at_index(launcher_dir: str | Path, index: int) -> bool:
    """Set ``last_done_iso`` to current UTC for the reminder at ``index`` in ``items``."""
    data = load_reminders(launcher_dir)
    items = data.get("items")
    if not isinstance(items, list):
        return False
    if index < 0 or index >= len(items):
        return False
    row = items[index]
    if not isinstance(row, dict):
        return False
    row["last_done_iso"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_reminders(launcher_dir, data)
    return True


def append_reminder(launcher_dir: str | Path, title: str, cadence_days: int = 7) -> None:
    """Append a new checklist row (not marked done)."""
    t = (title or "").strip()
    if not t:
        return
    data = load_reminders(launcher_dir)
    items = data.get("items")
    if not isinstance(items, list):
        items = []
    try:
        cad = max(1, min(int(cadence_days), 3660))
    except (TypeError, ValueError):
        cad = 7
    items.append({"title": t[:400], "cadence_days": cad, "last_done_iso": ""})
    data["items"] = items
    save_reminders(launcher_dir, data)
