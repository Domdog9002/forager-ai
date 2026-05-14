"""Resolve Minecraft Java model JSON ``parent`` chains for in-app UV preview.

Step 1 of the preview roadmap: merge inherited ``textures`` / ``elements`` from
pack files on disk, with small built-ins for common vanilla parents when the
pack does not ship the parent JSON.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from forager_ai.ui.mc_model_mesh import load_model_json


def _split_model_ref(ref: str) -> Tuple[str, str]:
    ref = (ref or "").strip().replace("\\", "/")
    if not ref or ref.startswith("#"):
        return "minecraft", ""
    if ":" in ref:
        ns, _, rest = ref.partition(":")
        return ns.strip().lower(), rest.strip().lstrip("/")
    return "minecraft", ref.strip().lstrip("/")


# Minimal axis-aligned unit cube (16³): every face uses ``#all`` so ``cube_all`` children only set ``textures.all``.
_BUILTIN_BLOCK_CUBE: Dict[str, Any] = {
    "textures": {"all": "minecraft:block/white_concrete"},
    "elements": [
        {
            "from": [0, 0, 0],
            "to": [16, 16, 16],
            "faces": {
                "down": {"uv": [0, 0, 16, 16], "texture": "#all"},
                "up": {"uv": [0, 0, 16, 16], "texture": "#all"},
                "north": {"uv": [0, 0, 16, 16], "texture": "#all"},
                "south": {"uv": [0, 0, 16, 16], "texture": "#all"},
                "east": {"uv": [0, 0, 16, 16], "texture": "#all"},
                "west": {"uv": [0, 0, 16, 16], "texture": "#all"},
            },
        }
    ],
}

# ``cube_all`` in vanilla only overrides ``all``; parent ``cube`` supplies geometry via built-in above.
_BUILTIN_CUBE_ALL: Dict[str, Any] = {"parent": "minecraft:block/cube", "textures": {}}

_CUBE_TEXTURE_FACE_KEYS = frozenset({"down", "up", "north", "south", "east", "west", "particle"})


def _builtin_for_ref(ns: str, path: str) -> Optional[Dict[str, Any]]:
    key = f"{ns}:{path}".lower().replace("\\", "/")
    if key in {"minecraft:block/cube", "block/cube"}:
        return json.loads(json.dumps(_BUILTIN_BLOCK_CUBE))
    if key in {"minecraft:block/cube_all", "block/cube_all"}:
        return json.loads(json.dumps(_BUILTIN_CUBE_ALL))
    return None


def _load_model_ref(ref: str, pack_root: Path) -> Optional[Dict[str, Any]]:
    ns, path = _split_model_ref(ref)
    if not path:
        return None
    rel = pack_root / "assets" / ns / "models" / f"{path}.json"
    if rel.is_file():
        return load_model_json(rel)
    return _builtin_for_ref(ns, path)


def _merge_model_layer(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """``override`` (child slice) wins on overlapping keys; ``elements`` prefer override when non-empty."""
    out: Dict[str, Any] = dict(base)
    bt = base.get("textures")
    ot = override.get("textures")
    if isinstance(bt, dict) or isinstance(ot, dict):
        merged: Dict[str, Any] = dict(bt or {})
        if isinstance(ot, dict) and "all" in ot:
            # Inherited per-face slots came from a parent's ``all`` fan-out; child's ``all`` replaces them.
            for fk in _CUBE_TEXTURE_FACE_KEYS:
                merged.pop(fk, None)
        if isinstance(ot, dict):
            merged.update(ot)
        out["textures"] = merged
    ov_el = override.get("elements")
    if isinstance(ov_el, list) and ov_el:
        out["elements"] = ov_el
    elif isinstance(base.get("elements"), list) and base.get("elements"):
        out["elements"] = base["elements"]
    for k, v in override.items():
        if k in ("textures", "elements"):
            continue
        out[k] = v
    return out


def _expand_all_texture_slot(model: Dict[str, Any]) -> Dict[str, Any]:
    """If only ``textures.all`` is set, fan out to per-face keys used by ``block/cube``."""
    tex = model.get("textures")
    if not isinstance(tex, dict) or "all" not in tex:
        return model
    val = tex.get("all")
    out = dict(model)
    nt = {k: v for k, v in tex.items() if k != "all"}
    for face_key in ("down", "up", "north", "south", "east", "west", "particle"):
        nt.setdefault(face_key, val)
    out["textures"] = nt
    return out


def resolve_model_for_preview(raw: Dict[str, Any], pack_root: Path, *, _depth: int = 0) -> Dict[str, Any]:
    """
    Flatten ``parent`` inheritance up to ``_depth`` 32.

    Pack-relative parents are loaded from ``assets/<ns>/models/<path>.json``.
    Built-ins: ``minecraft:block/cube`` and ``minecraft:block/cube_all`` (approximate).
    """
    if _depth > 32:
        return {k: v for k, v in raw.items() if k != "parent"}
    parent_ref = str(raw.get("parent") or "").strip()
    local = {k: v for k, v in raw.items() if k != "parent"}
    if not parent_ref:
        return _expand_all_texture_slot(dict(local))
    parent_raw = _load_model_ref(parent_ref, pack_root)
    if not parent_raw:
        return _expand_all_texture_slot(dict(local))
    base = resolve_model_for_preview(parent_raw, pack_root, _depth=_depth + 1)
    merged = _merge_model_layer(base, local)
    return _expand_all_texture_slot(merged)
