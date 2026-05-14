"""
Lightweight Blockbench / .bbmodel helpers (import for AI context, not a full editor).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Mapping


def summarize_bbmodel(data: Mapping[str, Any], *, max_elements: int = 12) -> str:
    """Return a short plain-text summary for LLM or UI (no binary embedding dumps)."""
    name = str(data.get("name") or "model")
    fmt = str((data.get("meta") or {}).get("format_version") or "?")
    res = data.get("resolution") or {}
    rw = res.get("width", "?")
    rh = res.get("height", "?")
    textures = data.get("textures") or []
    n_tex = len(textures) if isinstance(textures, list) else 0
    elements = data.get("elements") or []
    n_el = len(elements) if isinstance(elements, list) else 0
    anims = data.get("animations") or []
    n_anim = len(anims) if isinstance(anims, list) else 0
    lines = [
        f"Blockbench model `{name}` (format {fmt}, canvas {rw}x{rh}).",
        f"Textures: {n_tex} · Elements: {n_el} · Animations: {n_anim}.",
    ]
    if isinstance(elements, list):
        for i, el in enumerate(elements[:max_elements]):
            if not isinstance(el, dict):
                continue
            nm = el.get("name") or el.get("uuid") or f"el{i}"
            lines.append(f"  - element: {nm}")
        if n_el > max_elements:
            lines.append(f"  … {n_el - max_elements} more elements")
    return "\n".join(lines)


def summarize_bbmodel_path(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("bbmodel root must be a JSON object")
    return summarize_bbmodel(data)


def load_bbmodel_dict(path: str) -> Dict[str, Any]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("bbmodel root must be a JSON object")
    return data
