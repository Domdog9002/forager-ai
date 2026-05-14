from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..fs.safe_writer import write_text_utf8_nobom


COMPATS_DIRNAME = "compats"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sanitize_rule_name(name: str) -> str:
    safe = "".join(ch.lower() if ch.isalnum() else "_" for ch in name.strip())
    return "_".join([p for p in safe.split("_") if p]) or "compat_rule"


def ensure_compats_dir(pack_root: str) -> str:
    path = os.path.join(pack_root, COMPATS_DIRNAME)
    os.makedirs(path, exist_ok=True)
    return path


def add_compat_rule(
    pack_root: str,
    *,
    rule_name: str,
    affected_mods: List[str],
    description: str,
    source: str = "ai",
) -> Dict[str, Any]:
    compats_dir = ensure_compats_dir(pack_root)
    rule_id = _sanitize_rule_name(rule_name)
    path = os.path.join(compats_dir, f"{rule_id}.json")
    payload = {
        "rule_id": rule_id,
        "rule_name": rule_name,
        "affected_mods": affected_mods,
        "description": description,
        "source": source,
        "updated_at": _utc_now_iso(),
    }
    write_text_utf8_nobom(path, json.dumps(payload, indent=2, ensure_ascii=True))
    return payload


def list_compat_rules(pack_root: str) -> List[Dict[str, Any]]:
    compats_dir = ensure_compats_dir(pack_root)
    out: List[Dict[str, Any]] = []
    for filename in sorted(os.listdir(compats_dir)):
        if not filename.endswith(".json"):
            continue
        path = os.path.join(compats_dir, filename)
        try:
            with open(path, "r", encoding="utf-8") as f:
                out.append(json.load(f))
        except Exception:
            continue
    return out

