"""
Vanilla-style particle JSON + placeholder texture for Java resource packs (1.20.x style).
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path
from typing import List, Tuple

from PIL import Image, ImageDraw

_NS_RE = re.compile(r"^[a-z0-9_]+$")
_ID_RE = re.compile(r"^[a-z0-9_]+$")


def _slug(s: str, *, fallback: str, pattern: re.Pattern[str]) -> str:
    raw = (s or "").strip().lower().replace("-", "_")
    if not pattern.match(raw):
        return fallback
    return raw


def build_particle_json(*, namespace: str, texture_path: str) -> str:
    """``texture_path`` is relative under textures/, e.g. ``particle/sparkle`` (no .png)."""
    ns = _slug(namespace, fallback="forager_ai", pattern=_NS_RE)
    tp = texture_path.replace("\\", "/").strip().strip("/")
    if not tp:
        tp = "particle/forager_stub"
    rid = f"{ns}:{tp}"
    doc = {"textures": [rid]}
    return json.dumps(doc, indent=2, ensure_ascii=True) + "\n"


def _placeholder_png() -> bytes:
    img = Image.new("RGBA", (16, 16), (200, 230, 255, 220))
    dr = ImageDraw.Draw(img)
    dr.ellipse((2, 2, 13, 13), fill=(120, 200, 255, 255))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_vanilla_particle_stub(
    pack_root: str,
    *,
    namespace: str,
    particle_id: str,
    texture_subpath: str = "particle/forager_stub",
) -> Tuple[List[str], str]:
    """
    Write ``assets/<ns>/particles/<id>.json`` and ``assets/<ns>/textures/<texture_subpath>.png``.

    Returns (relative paths written, short message).
    """
    ns = _slug(namespace, fallback="forager_ai", pattern=_NS_RE)
    pid = _slug(particle_id, fallback="forager_particle", pattern=_ID_RE)
    tp = texture_subpath.replace("\\", "/").strip().strip("/") or "particle/forager_stub"
    if Path(tp).suffix.lower() == ".png":
        tp = str(Path(tp).with_suffix(""))

    root = Path(pack_root)
    p_json = root / "assets" / ns / "particles" / f"{pid}.json"
    p_png = root / "assets" / ns / "textures" / f"{tp}.png"
    p_json.parent.mkdir(parents=True, exist_ok=True)
    p_png.parent.mkdir(parents=True, exist_ok=True)

    body = build_particle_json(namespace=ns, texture_path=tp)
    p_json.write_text(body, encoding="utf-8", newline="\n")
    p_png.write_bytes(_placeholder_png())

    rel_json = str(p_json.relative_to(root)).replace("\\", "/")
    rel_png = str(p_png.relative_to(root)).replace("\\", "/")
    return [rel_json, rel_png], f"Particle `{ns}:{pid}` + texture `{ns}:{tp}`"
