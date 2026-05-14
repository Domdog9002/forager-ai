"""
Minimal Minecraft Java Edition model JSON (for items / generated parent).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Tuple


def write_item_generated_model(
    pack_root: str,
    *,
    namespace: str,
    model_id: str,
    texture_path: str,
) -> Tuple[str, str]:
    """
    Write ``assets/<ns>/models/item/<model_id>.json`` with parent ``item/generated``.

    ``texture_path`` is layer0 reference without namespace, e.g. ``item/foo``.
    Returns (relative path, json body).
    """
    ns = namespace.strip().lower().replace("-", "_") or "minecraft"
    mid = model_id.strip().lower().replace("-", "_") or "custom"
    tp = texture_path.replace("\\", "/").strip().strip("/")
    if ":" not in tp:
        tp = f"{ns}:{tp}"
    body = {
        "parent": "minecraft:item/generated",
        "textures": {"layer0": tp},
    }
    text = json.dumps(body, indent=2, ensure_ascii=True) + "\n"
    root = Path(pack_root)
    out = root / "assets" / ns / "models" / "item" / f"{mid}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    rel = str(out.relative_to(root)).replace("\\", "/")
    return rel, text
