"""Load static config playbooks (safe toggles + doc links)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _data_path() -> Path:
    return Path(__file__).resolve().parent / "data" / "config_playbooks.json"


def load_config_playbooks() -> List[Dict[str, Any]]:
    p = _data_path()
    if not p.is_file():
        return []
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = raw.get("playbooks") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        return []
    return [x for x in items if isinstance(x, dict)]
