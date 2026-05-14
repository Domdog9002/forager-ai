from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..fs.safe_writer import write_text_utf8_nobom


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def make_ai_artifact(
    *,
    artifact_type: str,
    pack_name: str,
    title: str,
    summary: str,
    payload: Dict[str, Any],
    source: str = "forager_ai",
) -> Dict[str, Any]:
    """Stable artifact shape for preview, saving, and Council handoff."""
    return {
        "artifact_type": artifact_type,
        "title": title,
        "pack_name": pack_name,
        "summary": summary,
        "source": source,
        "created_at": utc_now_iso(),
        "payload": payload,
    }


def save_ai_artifact(pack_root: str, artifact: Dict[str, Any], *, folder: str = ".forager/artifacts") -> str:
    artifact_type = str(artifact.get("artifact_type") or "artifact").strip().lower()
    safe_type = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in artifact_type)[:80]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    rel_dir = folder.replace("\\", "/").strip("/")
    path = os.path.join(pack_root, rel_dir, f"{stamp}_{safe_type}.json")
    write_text_utf8_nobom(path, json.dumps(artifact, indent=2, ensure_ascii=True))
    return path


def compat_proposals_from_conflicts(conflicts: List[Dict[str, Any]], *, limit: int = 12) -> List[Dict[str, Any]]:
    """Convert reviewed conflict scan findings into proposed compat rules."""
    proposals: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for conflict in conflicts:
        affected = [str(item).strip() for item in conflict.get("affected_mods", []) if str(item).strip()]
        if not affected:
            continue
        key = "|".join(sorted(affected)) + "|" + str(conflict.get("type") or "")
        if key in seen:
            continue
        seen.add(key)
        rule_name = f"{str(conflict.get('type') or 'compat').replace('_', ' ').title()}: {', '.join(affected)}"
        proposals.append(
            {
                "rule_name": rule_name,
                "affected_mods": affected,
                "description": (
                    f"{conflict.get('description', '')}\n\n"
                    f"Suggested resolution: {conflict.get('suggested_resolution', 'Review manually.')}"
                ).strip(),
                "source_conflict_id": conflict.get("id"),
                "severity": conflict.get("severity", "low"),
            }
        )
        if len(proposals) >= limit:
            break
    return proposals
