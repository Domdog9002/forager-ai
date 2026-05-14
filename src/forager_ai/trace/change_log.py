from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict


def _trace_path(pack_root: str) -> str:
    d = os.path.join(pack_root, ".forager")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, "change_trace.jsonl")


def append_change_trace(
    pack_root: str,
    *,
    feature_name: str,
    checkpoint_id: str | None,
    files_written: list[str],
    compat_written: list[str],
    actions_executed: int,
) -> None:
    line = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "feature_name": feature_name,
        "checkpoint_id": checkpoint_id,
        "files_written": files_written,
        "compat_rules": compat_written,
        "actions_executed": actions_executed,
    }
    path = _trace_path(pack_root)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(line, ensure_ascii=True) + "\n")


def read_recent_traces(pack_root: str, limit: int = 30) -> list[Dict[str, Any]]:
    path = _trace_path(pack_root)
    if not os.path.exists(path):
        return []
    rows: list[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows[-limit:]
