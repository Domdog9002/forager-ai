from __future__ import annotations

import os
from typing import Any, Dict, List


CONFIG_EXTENSIONS = (".json", ".toml", ".cfg", ".properties", ".yaml", ".yml")


def list_config_files(pack_root: str, *, limit: int = 120) -> List[Dict[str, Any]]:
    config_root = os.path.join(pack_root, "config")
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(config_root):
        return rows
    for base, _, files in os.walk(config_root):
        for name in sorted(files):
            if not name.lower().endswith(CONFIG_EXTENSIONS):
                continue
            full = os.path.join(base, name)
            rel = os.path.relpath(full, pack_root).replace("\\", "/")
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            rows.append({"path": rel, "size": size, "extension": os.path.splitext(name)[1].lower()})
            if len(rows) >= limit:
                return rows
    return rows


def summarize_config_targets(pack_root: str, request: str) -> Dict[str, Any]:
    files = list_config_files(pack_root)
    needle_words = [word.lower() for word in request.replace("_", " ").split() if len(word) >= 3]
    matches: List[Dict[str, Any]] = []
    for item in files:
        path_lower = item["path"].lower()
        score = sum(1 for word in needle_words if word in path_lower)
        if score:
            row = dict(item)
            row["score"] = score
            matches.append(row)
    matches.sort(key=lambda row: (-row["score"], row["path"]))
    return {
        "request": request,
        "total_config_files": len(files),
        "matches": matches[:20],
        "editable_extensions": list(CONFIG_EXTENSIONS),
    }


def draft_config_feature_plan(pack_root: str, request: str, target_path: str = "") -> Dict[str, Any]:
    summary = summarize_config_targets(pack_root, request)
    target = target_path.strip() or (summary["matches"][0]["path"] if summary["matches"] else "config/forager-ai-suggestions.txt")
    content = (
        "# Forager AI config assistant draft\n"
        f"# Request: {request.strip()}\n"
        "# Review this draft before applying. Replace with exact config keys after inspection.\n"
    )
    action_type = "edit_file" if target != "config/forager-ai-suggestions.txt" else "add_file"
    action: Dict[str, Any] = {"type": action_type, "path": target}
    if action_type == "edit_file":
        action["new_content"] = content
    else:
        action["content"] = content
    return {
        "feature_name": "config_assistant_draft",
        "actions": [action],
        "context": summary,
    }
