from __future__ import annotations

import base64
import hashlib
import io
import random
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageChops, ImageDraw, ImageEnhance


Color = Tuple[int, int, int, int]


@dataclass
class TextureForgeResult:
    image: Image.Image
    metadata: Dict[str, Any]
    quality: Dict[str, Any]


def normalize_resolution(value: Any, default: int = 16) -> int:
    if isinstance(value, str):
        match = re.search(r"\d+", value)
        raw = int(match.group(0)) if match else default
    else:
        try:
            raw = int(value)
        except (TypeError, ValueError):
            raw = default
    allowed = [16, 32, 64, 128]
    return min(allowed, key=lambda n: abs(n - raw))


def image_to_data_uri(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    data = base64.b64encode(buf.getvalue()).decode("ascii")
    return f"data:image/png;base64,{data}"


def extract_reference_style(image_path: str, *, max_colors: int = 6) -> Dict[str, Any]:
    with Image.open(image_path) as img:
        rgba = img.convert("RGBA")
    return extract_reference_style_from_image(rgba, max_colors=max_colors)


def extract_reference_style_from_image(image: Image.Image, *, max_colors: int = 6) -> Dict[str, Any]:
    rgba = image.convert("RGBA")
    colors: List[Tuple[int, int, int]] = []
    raw = rgba.tobytes()
    alpha_bounds = rgba.getchannel("A").getbbox()
    for idx in range(0, len(raw), 4):
        r, g, b, a = raw[idx], raw[idx + 1], raw[idx + 2], raw[idx + 3]
        if a > 24:
            colors.append((r, g, b))
    if not colors:
        palette = ["#7f7f7f"]
    else:
        tiny = Image.new("RGB", (len(colors), 1))
        tiny.putdata(colors)
        quant = tiny.quantize(colors=max(1, min(max_colors, len(set(colors)))))
        palette = []
        for _count, color in quant.convert("RGB").getcolors(maxcolors=10_000) or []:
            palette.append(_rgba_to_hex((color[0], color[1], color[2], 255)))
        if not palette:
            unique = sorted(set(colors))[:max_colors]
            palette = [_rgba_to_hex((r, g, b, 255)) for r, g, b in unique]
    return {
        "palette": palette[:max_colors],
        "bounds": list(alpha_bounds) if alpha_bounds else None,
        "has_transparency": any(a < 250 for a in rgba.getchannel("A").tobytes()),
        "size": [rgba.width, rgba.height],
    }


def texture_kind(spec: Dict[str, Any]) -> str:
    explicit = str(spec.get("asset_kind") or spec.get("kind") or "").strip().lower()
    if explicit:
        return explicit.replace(" ", "_")
    path = str(spec.get("path") or spec.get("texture_path") or "").lower()
    material = str(spec.get("material") or "").lower()
    if "gui" in path:
        return "gui"
    if "particle" in path:
        return "particle"
    if "armor" in path:
        return "armor"
    if "entity" in path or "mob" in path:
        return "entity"
    if "ore" in path or "ore" in material:
        return "ore"
    if path.startswith("item/") or "/item/" in path:
        return "item"
    return "block"


def render_texture_asset(spec: Dict[str, Any], theme: Optional[Dict[str, Any]] = None, *, index: int = 0) -> TextureForgeResult:
    theme = theme or {}
    theme = _theme_with_reference(theme, spec)
    size = normalize_resolution(spec.get("resolution") or theme.get("resolution") or 16)
    kind = texture_kind(spec)
    seed = _seed_for(spec, theme, index)
    rng = random.Random(seed)
    palette = _palette(theme, spec)
    base = palette[index % len(palette)]

    if kind in {"item", "tool", "weapon", "armor_icon"}:
        image = _item_texture(size, base, palette, rng, spec)
    elif kind in {"ore", "block_ore"}:
        image = _ore_texture(size, base, palette, rng, spec)
    elif kind in {"gui", "ui", "panel"}:
        image = _gui_texture(size, base, palette, rng, spec)
    elif kind in {"entity", "mob", "armor", "entity_sheet"}:
        image = _entity_sheet(size, base, palette, rng, spec)
    elif kind in {"particle", "effect"}:
        image = _particle_texture(size, base, palette, rng, spec)
    elif kind in {"uv", "model_uv", "3d", "model_texture"}:
        image = _uv_texture(size, base, palette, rng, spec)
    else:
        image = _block_texture(size, base, palette, rng, spec)

    image = _apply_reference_mask(image, spec)
    image = _apply_minecraft_finish(image, rng, spec)
    quality = score_texture(image, kind=kind)
    return TextureForgeResult(
        image=image,
        metadata={
            "engine": "texture_forge_local",
            "kind": kind,
            "resolution": size,
            "seed": seed,
            "palette": [_rgba_to_hex(c) for c in palette],
            "mode": "procedural_pixel_art",
            "reference_used": bool(spec.get("reference_image_path") or spec.get("reference_palette")),
        },
        quality=quality,
    )


def render_animation_strip(
    spec: Dict[str, Any],
    theme: Optional[Dict[str, Any]] = None,
    *,
    frames: int = 4,
    index: int = 0,
) -> TextureForgeResult:
    frames = max(2, min(int(frames or 4), 64))
    base = render_texture_asset(spec, theme, index=index)
    w, h = base.image.size
    strip = Image.new("RGBA", (w, h * frames), (0, 0, 0, 0))
    for frame in range(frames):
        img = base.image.copy()
        factor = 0.86 + (frame / max(1, frames - 1)) * 0.28
        img = ImageEnhance.Brightness(img).enhance(factor)
        overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        if frame % 2 == 0:
            draw.point([(frame % w, y) for y in range(0, h, 2)], fill=(255, 255, 255, 50))
        img = Image.alpha_composite(img, overlay)
        strip.paste(img, (0, frame * h))
    quality = score_texture(strip, kind="animation")
    metadata = dict(base.metadata)
    metadata.update({"kind": "animation", "frames": frames})
    return TextureForgeResult(image=strip, metadata=metadata, quality=quality)


def score_texture(image: Image.Image, *, kind: str = "texture") -> Dict[str, Any]:
    rgba = image.convert("RGBA")
    w, h = rgba.size
    warnings: List[str] = []
    if w not in {16, 32, 64, 128}:
        warnings.append("width is not a common Minecraft texture size")
    if kind != "animation" and w != h:
        warnings.append("texture is not square")
    if kind == "animation" and h % w != 0:
        warnings.append("animation strip height is not divisible by width")

    opaque_pixels = []
    raw = rgba.tobytes()
    for idx in range(0, len(raw), 4):
        r, g, b, a = raw[idx], raw[idx + 1], raw[idx + 2], raw[idx + 3]
        if a > 12:
            opaque_pixels.append((r, g, b))
    if not opaque_pixels:
        warnings.append("texture is fully transparent")
        return {"score": 20, "warnings": warnings, "contrast": 0, "palette_size": 0}

    luminance = [int(0.2126 * r + 0.7152 * g + 0.0722 * b) for r, g, b in opaque_pixels]
    contrast = max(luminance) - min(luminance)
    palette_size = len(set(opaque_pixels))
    if contrast < 28:
        warnings.append("low contrast; texture may be hard to read in-game")
    if palette_size > max(24, w * h // 2):
        warnings.append("very noisy palette for Minecraft-style pixel art")
    if palette_size < 3 and kind not in {"gui", "particle"}:
        warnings.append("too few visible colors")

    score = 100
    score -= len(warnings) * 14
    if contrast < 28:
        score -= 12
    if 4 <= palette_size <= 48:
        score += 4
    return {
        "score": max(0, min(100, score)),
        "warnings": warnings,
        "contrast": contrast,
        "palette_size": palette_size,
        "dimensions": [w, h],
    }


def model_json_for_spec(spec: Dict[str, Any], *, namespace: str, rel: str) -> Dict[str, Any]:
    parent = str(spec.get("parent") or "").strip()
    model_type = str(spec.get("model_type") or spec.get("asset_kind") or "").lower()
    texture_ref = str(spec.get("texture_layer0") or f"{namespace}:textures/{rel}").replace(".png", "")
    if not parent:
        if "handheld" in model_type or "tool" in model_type or "weapon" in model_type:
            parent = "minecraft:item/handheld"
        elif "cross" in model_type or "plant" in model_type:
            parent = "minecraft:block/cross"
        elif "item" in rel or model_type in {"item", "armor_icon"}:
            parent = "minecraft:item/generated"
        else:
            parent = "minecraft:block/cube_all"
    if ":" not in parent:
        parent = f"minecraft:{parent}"
    if "item/generated" in parent or "item/handheld" in parent:
        return {"parent": parent, "textures": {"layer0": texture_ref}}
    if "cross" in parent:
        return {"parent": parent, "textures": {"cross": texture_ref}}
    if "cube_all" in parent:
        return {"parent": parent, "textures": {"all": texture_ref}}
    return {"parent": parent, "textures": {"all": texture_ref, "particle": texture_ref}}


def _seed_for(spec: Dict[str, Any], theme: Dict[str, Any], index: int) -> int:
    blob = repr(
        {
            "spec": spec,
            "theme": theme.get("title") or theme.get("keywords") or theme.get("palette"),
            "index": index,
        }
    ).encode("utf-8", errors="ignore")
    return int(hashlib.sha256(blob).hexdigest()[:12], 16)


def _theme_with_reference(theme: Dict[str, Any], spec: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(theme or {})
    ref_palette = spec.get("reference_palette")
    if isinstance(ref_palette, list) and ref_palette:
        merged["palette"] = [str(x) for x in ref_palette if isinstance(x, str)]
        return merged
    ref_path = spec.get("reference_image_path")
    if isinstance(ref_path, str) and ref_path.strip():
        try:
            style = extract_reference_style(ref_path)
            merged["palette"] = style.get("palette") or merged.get("palette")
            spec.setdefault("reference_style", style)
        except OSError:
            pass
    return merged


def _palette(theme: Dict[str, Any], spec: Dict[str, Any]) -> List[Color]:
    raw = []
    if isinstance(theme.get("palette"), list):
        raw.extend(theme.get("palette") or [])
    if spec.get("color_hint"):
        raw.insert(0, spec.get("color_hint"))
    colors = [_hex_to_rgba(str(item)) for item in raw if isinstance(item, str)]
    colors = [c for c in colors if c is not None]
    if not colors:
        colors = [(92, 129, 96, 255), (64, 79, 92, 255), (154, 126, 73, 255), (116, 70, 142, 255)]
    while len(colors) < 4:
        colors.append(_shift_color(colors[-1], 24))
    return colors[:8]


def _apply_reference_mask(image: Image.Image, spec: Dict[str, Any]) -> Image.Image:
    ref_path = spec.get("reference_image_path")
    if not isinstance(ref_path, str) or not ref_path.strip():
        return image
    try:
        with Image.open(ref_path) as ref:
            alpha = ref.convert("RGBA").getchannel("A").resize(image.size, Image.Resampling.NEAREST)
    except OSError:
        return image
    if alpha.getbbox() is None:
        return image
    out = image.convert("RGBA")
    # Preserve rough silhouette without copying the original art.
    softened = ImageEnhance.Contrast(alpha).enhance(1.5)
    out.putalpha(softened)
    return out


def _hex_to_rgba(value: str) -> Optional[Color]:
    h = value.strip().lstrip("#")
    if len(h) != 6 or any(c not in "0123456789abcdefABCDEF" for c in h):
        return None
    return (int(h[:2], 16), int(h[2:4], 16), int(h[4:6], 16), 255)


def _rgba_to_hex(color: Color) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _shift_color(color: Color, amount: int) -> Color:
    return (
        max(0, min(255, color[0] + amount)),
        max(0, min(255, color[1] + amount)),
        max(0, min(255, color[2] + amount)),
        color[3],
    )


def _mix(a: Color, b: Color, t: float) -> Color:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
        int(a[3] + (b[3] - a[3]) * t),
    )


def _block_texture(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGBA", (size, size), base)
    px = img.load()
    dark = _shift_color(base, -34)
    light = _shift_color(base, 28)
    for y in range(size):
        for x in range(size):
            noise = rng.randint(-22, 22)
            c = _shift_color(base, noise)
            if (x + y + rng.randint(0, 7)) % 9 == 0:
                c = _mix(c, light, 0.42)
            if (x * 3 + y) % 11 == 0:
                c = _mix(c, dark, 0.36)
            px[x, y] = c
    draw = ImageDraw.Draw(img)
    if "brick" in str(spec.get("material") or spec.get("shape_language") or "").lower():
        for y in range(size // 4, size, size // 4):
            draw.line((0, y, size, y), fill=dark)
        for row, y in enumerate(range(0, size, size // 4)):
            offset = 0 if row % 2 else size // 4
            for x in range(offset, size, size // 2):
                draw.line((x, y, x, min(size, y + size // 4)), fill=dark)
    return img


def _ore_texture(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = _block_texture(size, _shift_color(base, -22), palette, rng, spec)
    draw = ImageDraw.Draw(img)
    ore = palette[(len(palette) - 1) % len(palette)]
    bright = _shift_color(ore, 42)
    for _ in range(max(5, size // 2)):
        x = rng.randrange(1, size - 2)
        y = rng.randrange(1, size - 2)
        draw.rectangle((x, y, x + rng.randrange(1, 3), y + rng.randrange(1, 3)), fill=ore)
        draw.point((min(size - 1, x + 1), y), fill=bright)
    return img


def _item_texture(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _shift_color(base, -48)
    light = _shift_color(base, 48)
    kind_text = f"{spec.get('path', '')} {spec.get('material', '')} {spec.get('shape_language', '')}".lower()
    if "sword" in kind_text or "tool" in kind_text or "weapon" in kind_text:
        draw.line((size // 3, size - 3, size - 3, size // 3), fill=dark, width=max(1, size // 8))
        draw.line((size // 3 + 1, size - 4, size - 4, size // 3), fill=light, width=max(1, size // 12))
        draw.rectangle((size // 5, size - 5, size // 2, size - 3), fill=palette[1])
    else:
        points = [(size // 2, 2), (size - 3, size // 3), (size - 5, size - 4), (size // 3, size - 2), (3, size // 2)]
        draw.polygon(points, fill=base)
        draw.line(points + [points[0]], fill=dark, width=1)
        draw.point((size // 2, size // 3), fill=light)
    return img


def _gui_texture(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    dark = _shift_color(base, -38)
    light = _shift_color(base, 32)
    draw.rounded_rectangle((1, 1, size - 2, size - 2), radius=max(2, size // 8), fill=base, outline=dark)
    draw.line((2, 2, size - 3, 2), fill=light)
    for x in range(4, size - 4, max(4, size // 4)):
        draw.line((x, 4, x, size - 5), fill=_mix(base, dark, 0.35))
    return img


def _entity_sheet(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    sheet = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(sheet)
    dark = _shift_color(base, -42)
    light = _shift_color(base, 36)
    cells = [(1, 1, size // 2 - 1, size // 2 - 1), (size // 2 + 1, 1, size - 2, size // 2 - 1), (1, size // 2 + 1, size - 2, size - 2)]
    for idx, rect in enumerate(cells):
        c = _mix(base, palette[idx % len(palette)], 0.32)
        draw.rectangle(rect, fill=c, outline=dark)
        draw.line((rect[0] + 1, rect[1] + 1, rect[2] - 1, rect[1] + 1), fill=light)
    return sheet


def _particle_texture(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    center = size // 2
    for r in range(center, 0, -1):
        alpha = int(210 * (r / center))
        c = _shift_color(base, (center - r) * 8)
        draw.ellipse((center - r, center - r, center + r, center + r), fill=(c[0], c[1], c[2], alpha))
    return img


def _uv_texture(size: int, base: Color, palette: List[Color], rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = Image.new("RGBA", (size, size), _shift_color(base, -20))
    draw = ImageDraw.Draw(img)
    dark = _shift_color(base, -55)
    light = _shift_color(base, 42)
    half = size // 2
    rects = [(0, 0, half - 1, half - 1), (half, 0, size - 1, half - 1), (0, half, half - 1, size - 1), (half, half, size - 1, size - 1)]
    for idx, rect in enumerate(rects):
        c = _mix(base, palette[idx % len(palette)], 0.25)
        draw.rectangle(rect, fill=c, outline=dark)
        draw.line((rect[0] + 1, rect[1] + 1, rect[2] - 1, rect[1] + 1), fill=light)
    return img


def _apply_minecraft_finish(image: Image.Image, rng: random.Random, spec: Dict[str, Any]) -> Image.Image:
    img = image.convert("RGBA")
    if bool(spec.get("emissive_hint")):
        overlay = Image.new("RGBA", img.size, (255, 255, 180, 0))
        draw = ImageDraw.Draw(overlay)
        for _ in range(max(2, img.size[0] // 8)):
            x = rng.randrange(0, img.size[0])
            y = rng.randrange(0, img.size[1])
            draw.point((x, y), fill=(255, 255, 180, 130))
        img = Image.alpha_composite(img, overlay)
    # Quantize colors slightly while preserving alpha for a more Minecraft-like finish.
    rgb = img.convert("RGB").quantize(colors=32).convert("RGBA")
    alpha = img.getchannel("A")
    rgb.putalpha(alpha)
    return rgb
