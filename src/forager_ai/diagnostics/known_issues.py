from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


def _store_path() -> Path:
    base = Path.home() / ".forager_ai"
    base.mkdir(parents=True, exist_ok=True)
    return base / "known_issues.json"


def _defaults() -> List[Dict[str, Any]]:
    return [
        {
            "id": "optifine_rubidium",
            "patterns": ["embeddium", "optifine"],
            "require": "all",
            "hint": "OptiFine often conflicts with Embeddium/Sodium stacks; use Embeddium without OptiFine or switch render pipeline.",
            "severity": "high",
        },
        {
            "id": "optifine_iris",
            "patterns": ["iris", "optifine"],
            "require": "all",
            "hint": "Iris + OptiFine is usually unsupported; pick Iris **or** OptiFine for shaders.",
            "severity": "high",
        },
        {
            "id": "duplicate_mods",
            "patterns": ["found a duplicate mod", "duplicate mod"],
            "hint": "Remove duplicate jar versions of the same mod; keep only one matching version for your MC/loader.",
            "severity": "medium",
        },
    ]


def load_known_issues() -> List[Dict[str, Any]]:
    path = _store_path()
    if not path.exists():
        data = _defaults()
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=True)
        return data
    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        if isinstance(raw, list):
            return raw
    except (json.JSONDecodeError, OSError):
        pass
    return _defaults()


def match_known_issues(text: str) -> List[Dict[str, Any]]:
    if not (text or "").strip():
        return []
    blob = text.lower()
    hits: List[Dict[str, Any]] = []
    for entry in load_known_issues():
        pats = entry.get("patterns") or []
        if not isinstance(pats, list):
            continue
        norm = [p.strip().lower() for p in pats if isinstance(p, str) and p.strip()]
        if not norm:
            continue
        req = str(entry.get("require", "any")).lower()
        if req == "all":
            matched = all(p in blob for p in norm)
        else:
            matched = any(p in blob for p in norm)
        if matched:
            hits.append(entry)
    return hits


def add_known_issue(*, patterns: List[str], hint: str, severity: str = "medium") -> Dict[str, Any]:
    rows = load_known_issues()
    new_id = f"custom_{len(rows) + 1}"
    row = {"id": new_id, "patterns": patterns, "hint": hint, "severity": severity}
    rows.append(row)
    with open(_store_path(), "w", encoding="utf-8") as fh:
        json.dump(rows, fh, indent=2, ensure_ascii=True)
    return row


def build_known_issues_probe_text(
    *,
    pack_name: str,
    mods: List[Dict[str, Any]],
    conflicts: List[Dict[str, Any]],
    progression_findings: List[Any],
    max_chars: int = 1400,
) -> str:
    """Flatten pack signals for substring matching against the known-issues pattern DB."""
    parts: List[str] = []
    parts.append((pack_name or "").lower())
    parts.extend(["minecraft", "modpack", "forge", "fabric"])
    for m in mods[:80]:
        if not isinstance(m, dict):
            continue
        for key in ("id", "name", "file_name"):
            v = str(m.get(key) or "").strip().lower()
            if v:
                parts.append(v)
    for c in conflicts[:22]:
        if not isinstance(c, dict):
            continue
        for key in ("description", "type", "suggested_resolution"):
            parts.append(str(c.get(key) or "").lower())
        for mid in c.get("affected_mods") or []:
            parts.append(str(mid).lower())
        for lbl in c.get("affected_labels") or []:
            parts.append(str(lbl).lower())
    for pf in progression_findings[:14]:
        if isinstance(pf, dict):
            parts.append(str(pf.get("id") or "").lower())
            parts.append(str(pf.get("message") or "").lower())
    blob = " ".join(parts)
    blob = " ".join(blob.split())
    return blob[:max_chars] if blob else ""


def format_known_issue_hits(hits: List[Dict[str, Any]], *, max_chars: int = 1400) -> str:
    if not hits:
        return ""
    lines = ["[Known issues DB — heuristic pattern hits]"]
    for h in hits[:18]:
        if not isinstance(h, dict):
            continue
        hid = str(h.get("id") or "?")
        sev = str(h.get("severity") or "medium")
        hint = str(h.get("hint") or "").strip()
        lines.append(f"- `{hid}` ({sev}): {hint[:400]}")
    return "\n".join(lines).strip()[:max_chars]
