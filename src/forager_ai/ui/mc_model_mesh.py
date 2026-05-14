"""Build a lightweight triangle mesh from Minecraft Java block/item model JSON.

Supports common cases used by Forager-generated packs: ``item/generated``-style
(optional) and models with ``elements`` (axis-aligned boxes). Per-face
``rotation`` (0/90/180/270) rotates UV corners. Unknown shapes return ``None``
so callers can fall back to a textured cube.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _permute_uv_four(
    ta: Tuple[float, float],
    tb: Tuple[float, float],
    tc: Tuple[float, float],
    td: Tuple[float, float],
    rotation_deg: int,
) -> Tuple[Tuple[float, float], Tuple[float, float], Tuple[float, float], Tuple[float, float]]:
    """Rotate corner UV assignment in 90° steps (Minecraft face ``rotation``)."""
    corners = [ta, tb, tc, td]
    steps = (int(rotation_deg) // 90) % 4
    for _ in range(steps):
        corners = [corners[3], corners[0], corners[1], corners[2]]
    return corners[0], corners[1], corners[2], corners[3]


def _num_list(val: Any, n: int) -> Optional[List[float]]:
    if not isinstance(val, list) or len(val) != n:
        return None
    out: List[float] = []
    for x in val:
        try:
            out.append(float(x))
        except (TypeError, ValueError):
            return None
    return out


def _face_plane(
    face: str,
    frm: List[float],
    to: List[float],
) -> Optional[List[Tuple[float, float, float]]]:
    """Four corners (CCW from outside) for one face of an axis-aligned box in unit-block space."""
    x0, y0, z0 = frm[0] / 16.0 - 0.5, frm[1] / 16.0 - 0.5, frm[2] / 16.0 - 0.5
    x1, y1, z1 = to[0] / 16.0 - 0.5, to[1] / 16.0 - 0.5, to[2] / 16.0 - 0.5
    xa, xb = (x0, x1) if x0 <= x1 else (x1, x0)
    ya, yb = (y0, y1) if y0 <= y1 else (y1, y0)
    za, zb = (z0, z1) if z0 <= z1 else (z1, z0)
    f = face.lower()
    if f == "north":
        z = za
        return [(xb, ya, z), (xa, ya, z), (xa, yb, z), (xb, yb, z)]
    if f == "south":
        z = zb
        return [(xa, ya, z), (xb, ya, z), (xb, yb, z), (xa, yb, z)]
    if f == "west":
        x = xa
        return [(x, ya, zb), (x, ya, za), (x, yb, za), (x, yb, zb)]
    if f == "east":
        x = xb
        return [(x, ya, za), (x, ya, zb), (x, yb, zb), (x, yb, za)]
    if f == "down":
        y = ya
        return [(xa, y, zb), (xb, y, zb), (xb, y, za), (xa, y, za)]
    if f == "up":
        y = yb
        return [(xa, y, za), (xb, y, za), (xb, y, zb), (xa, y, zb)]
    return None


def mesh_from_java_model(
    model: Dict[str, Any],
    *,
    texture_width: int = 16,
    texture_height: int = 16,
) -> Optional[Dict[str, Any]]:
    """
    Return dict with keys: positions (float32 list), uvs (float32 list), indices (int list).

    Uses the first texture reference found on any face; caller should bind the matching image.
    """
    tw = max(1, int(texture_width))
    th = max(1, int(texture_height))
    elems = model.get("elements")
    if not isinstance(elems, list) or not elems:
        return None
    positions: List[float] = []
    uvs: List[float] = []
    indices: List[int] = []
    base_v = 0
    for el in elems:
        if not isinstance(el, dict):
            continue
        frm = _num_list(el.get("from"), 3)
        to = _num_list(el.get("to"), 3)
        if not frm or not to:
            continue
        faces = el.get("faces")
        if not isinstance(faces, dict):
            continue
        for fname, fdef in faces.items():
            if not isinstance(fdef, dict):
                continue
            corners = _face_plane(str(fname), frm, to)
            if not corners:
                continue
            uv = _num_list(fdef.get("uv"), 4)
            if not uv:
                continue
            try:
                rot = int(fdef.get("rotation") or 0) % 360
            except (TypeError, ValueError):
                rot = 0
            u0, v0, u1, v1 = uv[0] / tw, uv[1] / th, uv[2] / tw, uv[3] / th
            # Minecraft UV origin top-left; flip V for WebGL 0..1 bottom-left convention
            def uv_pair(u: float, v: float) -> Tuple[float, float]:
                return (u, 1.0 - v)

            ta = uv_pair(u0, v0)
            tb = uv_pair(u1, v0)
            tc = uv_pair(u1, v1)
            td = uv_pair(u0, v1)
            ta, tb, tc, td = _permute_uv_four(ta, tb, tc, td, rot)
            for cx, cy, cz in corners:
                positions.extend([cx, cy, cz])
            uvs.extend([ta[0], ta[1], tb[0], tb[1], tc[0], tc[1], td[0], td[1]])
            indices.extend([base_v, base_v + 1, base_v + 2, base_v, base_v + 2, base_v + 3])
            base_v += 4
    if len(indices) < 3:
        return None
    return {
        "positions": positions,
        "uvs": uvs,
        "indices": indices,
        "vertex_count": base_v,
    }


def infer_model_preview_kind(model: Dict[str, Any]) -> str:
    parent = str(model.get("parent") or "")
    low = parent.lower()
    if "item/generated" in low or "item/handheld" in low:
        return "item_plane"
    if isinstance(model.get("elements"), list) and model["elements"]:
        return "elements"
    return "unknown"


def load_model_json(path: str | Path) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.is_file():
        return None
    try:
        raw = p.read_text(encoding="utf-8")
    except OSError:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def resolve_texture_path_from_model(
    model: Dict[str, Any],
    *,
    pack_root: Path,
    preferred_key: str = "#all",
) -> Optional[Path]:
    """Resolve a single ``assets/...png`` from ``textures`` map (best-effort)."""
    texmap = model.get("textures")
    if not isinstance(texmap, dict) or not texmap:
        return None
    candidates: List[str] = []
    pk = preferred_key if preferred_key in texmap else None
    if pk:
        candidates.append(str(texmap.get(pk) or ""))
    for v in texmap.values():
        s = str(v or "").strip()
        if s and s not in candidates:
            candidates.append(s)
    for ref in candidates:
        if not ref or ref.startswith("#"):
            continue
        if ":" in ref:
            ns, _, rest = ref.partition(":")
        else:
            ns, rest = "minecraft", ref
        rest = rest.replace("\\", "/").strip("/")
        rel = Path("assets") / ns / "textures" / f"{rest}.png"
        cand = pack_root / rel
        if cand.is_file():
            return cand
        # try stripping .png duplication
        if rest.endswith(".png"):
            cand2 = pack_root / "assets" / ns / "textures" / rest
            if cand2.is_file():
                return cand2
    return None


def texture_dimensions_from_png(path: Path) -> Tuple[int, int]:
    try:
        from PIL import Image

        with Image.open(path) as im:
            return int(im.width), int(im.height)
    except Exception:
        return 16, 16
