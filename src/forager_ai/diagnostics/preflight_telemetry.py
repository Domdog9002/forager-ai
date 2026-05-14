"""Opt-in local queue for anonymized preflight summaries (no network)."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _queue_dir(pack_root: str) -> str:
    return os.path.join(str(pack_root or "").strip(), ".forager", "telemetry_queue")


def maybe_enqueue_preflight_snapshot(
    *,
    pack_root: str,
    enabled: bool,
    report: Dict[str, Any],
    include_paths: bool = False,
) -> Optional[str]:
    """
    Append one JSON line with coarse hashes only (unless ``include_paths``).

    Returns file path written, or None when disabled / empty.
    """
    if not enabled or not str(pack_root or "").strip():
        return None
    root = str(pack_root).strip()
    d = _queue_dir(root)
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        return None

    sf = report.get("scan_fidelity") if isinstance(report.get("scan_fidelity"), dict) else {}
    hs = report.get("health_score") if isinstance(report.get("health_score"), dict) else {}
    cs = (report.get("conflict_scan") or {}).get("summary") if isinstance(report.get("conflict_scan"), dict) else {}
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "confidence": str(sf.get("confidence") or ""),
        "health_verdict": str(hs.get("verdict") or ""),
        "health_score": hs.get("score"),
        "total_conflicts": int((cs or {}).get("total_conflicts") or 0) if isinstance(cs, dict) else 0,
        "launch_severity": str((report.get("launch_log_signals") or {}).get("overall_severity") or ""),
        "root_hash": hashlib.sha256(root.encode("utf-8", errors="ignore")).hexdigest()[:16],
    }
    if include_paths:
        row["pack_root"] = root

    path = os.path.join(d, "events.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=True) + "\n")
    except OSError:
        return None
    return path
