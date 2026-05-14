from __future__ import annotations

import json
import os
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple

from PIL import Image, ImageChops, ImageEnhance, ImageFilter, ImageOps

from .texture_forge import render_texture_asset, score_texture
from ..fs.safe_writer import write_text_utf8_nobom


STYLE_PRESETS: Dict[str, Dict[str, Any]] = {
    "Arcane Tech": {
        "palette": ["#44d7e8", "#7c3aed", "#0f172a", "#58c95f"],
        "motifs": ["glowing runes", "brass machine edges", "clean silhouettes"],
        "resolution": "32x32",
        "accessibility_rules": ["keep vanilla silhouettes", "high contrast accents"],
        "preferred_model_types": ["item_generated", "handheld", "cube_all"],
    },
    "Vanilla Plus": {
        "palette": ["#6b8f4e", "#8b6f47", "#c8b88a", "#334155"],
        "motifs": ["soft noise", "readable icons", "vanilla shape language"],
        "resolution": "16x16",
        "accessibility_rules": ["avoid noisy palettes", "preserve item silhouette"],
        "preferred_model_types": ["item_generated", "cube_all"],
    },
    "Dark RPG": {
        "palette": ["#111827", "#7f1d1d", "#b45309", "#a78bfa"],
        "motifs": ["dark metal", "aged leather", "mystic highlights"],
        "resolution": "32x32",
        "accessibility_rules": ["bright edges on dark items", "boss gear should pop"],
        "preferred_model_types": ["handheld", "entity_box", "cube_all"],
    },
}


def texture_forge_dir(pack_dir: str | Path) -> Path:
    path = Path(pack_dir) / ".forager" / "texture_forge"
    path.mkdir(parents=True, exist_ok=True)
    return path


def load_style_memory(pack_dir: str | Path) -> Dict[str, Any]:
    path = texture_forge_dir(pack_dir) / "style_memory.json"
    if not path.is_file():
        return {"active": "Arcane Tech", "profiles": dict(STYLE_PRESETS)}
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            data.setdefault("profiles", dict(STYLE_PRESETS))
            data.setdefault("active", next(iter(data["profiles"]), "Arcane Tech"))
            return data
    except (json.JSONDecodeError, OSError):
        pass
    return {"active": "Arcane Tech", "profiles": dict(STYLE_PRESETS)}


def save_style_profile(pack_dir: str | Path, name: str, profile: Dict[str, Any], *, active: bool = True) -> str:
    memory = load_style_memory(pack_dir)
    safe_name = str(name or "Custom Style").strip()[:80] or "Custom Style"
    memory.setdefault("profiles", {})[safe_name] = profile
    if active:
        memory["active"] = safe_name
    path = texture_forge_dir(pack_dir) / "style_memory.json"
    write_text_utf8_nobom(str(path), json.dumps(memory, indent=2, ensure_ascii=False))
    return str(path)


def active_style_profile(pack_dir: str | Path) -> Dict[str, Any]:
    memory = load_style_memory(pack_dir)
    profiles = memory.get("profiles") or {}
    return dict(profiles.get(memory.get("active")) or next(iter(profiles.values()), {}))


def build_queue_candidates(
    targets: Iterable[Dict[str, Any]],
    *,
    spec_builder,
    theme: Dict[str, Any],
    limit: int = 24,
) -> List[Dict[str, Any]]:
    queue: List[Dict[str, Any]] = []
    for idx, target in enumerate(list(targets)[:limit]):
        spec = spec_builder(target)
        forged = render_texture_asset(spec, theme, index=idx)
        queue.append(
            {
                "id": f"candidate_{idx}",
                "approved": forged.quality.get("score", 0) >= 55,
                "target": target,
                "spec": spec,
                "quality": forged.quality,
                "forge": forged.metadata,
            }
        )
    return queue


def save_queue_metadata(pack_dir: str | Path, queue: List[Dict[str, Any]], *, name: str = "last_queue") -> str:
    qdir = texture_forge_dir(pack_dir) / "queues"
    qdir.mkdir(parents=True, exist_ok=True)
    path = qdir / f"{name}.json"
    payload = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "count": len(queue),
        "approved": sum(1 for item in queue if item.get("approved")),
        "items": queue,
    }
    write_text_utf8_nobom(str(path), json.dumps(payload, indent=2, ensure_ascii=False))
    return str(path)


def apply_pixel_transform(image: Image.Image, transform: str) -> Image.Image:
    t = str(transform or "").lower()
    img = image.convert("RGBA")
    if t == "outline":
        return _outline(img)
    if t == "brighten":
        return ImageEnhance.Brightness(img).enhance(1.18)
    if t == "darken":
        return ImageEnhance.Brightness(img).enhance(0.82)
    if t == "contrast boost":
        return ImageEnhance.Contrast(img).enhance(1.35)
    if t == "transparent cleanup":
        return _cleanup_alpha(img)
    if t == "mirror":
        return ImageOps.mirror(img)
    if t == "rotate":
        return img.rotate(90, expand=False)
    if t == "sharpen":
        return img.filter(ImageFilter.SHARPEN)
    if t == "minecraft quantize":
        alpha = img.getchannel("A")
        quant = img.convert("RGB").quantize(colors=32).convert("RGBA")
        quant.putalpha(alpha)
        return quant
    if t == "upscale 2x":
        return img.resize((img.width * 2, img.height * 2), Image.Resampling.NEAREST)
    if t == "downscale 2x":
        return img.resize((max(1, img.width // 2), max(1, img.height // 2)), Image.Resampling.NEAREST)
    return img


def repair_texture(image: Image.Image) -> Tuple[Image.Image, Dict[str, Any]]:
    img = image.convert("RGBA")
    before = score_texture(img)
    repaired = apply_pixel_transform(img, "transparent cleanup")
    repaired = apply_pixel_transform(repaired, "contrast boost")
    repaired = apply_pixel_transform(repaired, "minecraft quantize")
    after = score_texture(repaired)
    return repaired, {"before": before, "after": after, "improved": after.get("score", 0) >= before.get("score", 0)}


def save_export_report(pack_dir: str | Path, report: Dict[str, Any], *, label: str = "last_apply") -> str:
    rdir = texture_forge_dir(pack_dir) / "reports"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / f"{label}.json"
    payload = {"saved_at": datetime.now(timezone.utc).isoformat(), **report}
    write_text_utf8_nobom(str(path), json.dumps(payload, indent=2, ensure_ascii=False))
    write_text_utf8_nobom(str(rdir / "latest.json"), json.dumps(payload, indent=2, ensure_ascii=False))
    return str(path)


def rollback_latest(pack_dir: str | Path) -> Dict[str, Any]:
    root = Path(pack_dir)
    latest = texture_forge_dir(root) / "reports" / "latest.json"
    result: Dict[str, Any] = {"restored": [], "warnings": []}
    if not latest.is_file():
        result["warnings"].append("No Texture Forge report found.")
        return result
    try:
        with open(latest, "r", encoding="utf-8") as fh:
            report = json.load(fh)
    except (json.JSONDecodeError, OSError) as exc:
        result["warnings"].append(f"Could not read rollback report: {exc}")
        return result
    for rel in report.get("backups") or []:
        backup = root / rel
        marker = Path(rel).parts
        if ".forager" not in marker or "backups" not in marker:
            continue
        try:
            idx = marker.index("backups")
            original_rel = Path(*marker[idx + 1 :])
        except (ValueError, TypeError):
            continue
        dest = root / original_rel
        if backup.is_file() and str(dest.resolve()).startswith(str(root.resolve())):
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(backup, dest)
            result["restored"].append(dest.relative_to(root).as_posix())
    if not result["restored"]:
        result["warnings"].append("No backup files were restored.")
    return result


def export_blockbench_sources(pack_dir: str | Path, export_path: str | Path) -> bool:
    root = Path(pack_dir)
    bb_dir = root / ".forager" / "blockbench"
    if not bb_dir.is_dir():
        return False
    out = Path(export_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in bb_dir.rglob("*.bbmodel"):
            zf.write(file, file.relative_to(bb_dir))
    return True


def validate_texture_forge_export(pack_dir: str | Path) -> Dict[str, Any]:
    root = Path(pack_dir)
    warnings: List[str] = []
    png_count = 0
    model_count = 0
    for png in (root / "assets").rglob("*.png") if (root / "assets").is_dir() else []:
        png_count += 1
        try:
            with Image.open(png) as img:
                if img.width not in {16, 32, 64, 128}:
                    warnings.append(f"{png.relative_to(root).as_posix()} has unusual width {img.width}")
        except OSError:
            warnings.append(f"{png.relative_to(root).as_posix()} is not readable")
    for model in (root / "assets").rglob("*.json") if (root / "assets").is_dir() else []:
        if "models" in model.parts:
            model_count += 1
    return {"ok": not warnings, "warnings": warnings, "png_count": png_count, "model_count": model_count}


def _outline(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    expanded = ImageChops.lighter(alpha.filter(ImageFilter.MaxFilter(3)), alpha)
    border = ImageChops.subtract(expanded, alpha)
    outline = Image.new("RGBA", image.size, (12, 18, 24, 255))
    outline.putalpha(border)
    return Image.alpha_composite(outline, image)


def _cleanup_alpha(image: Image.Image) -> Image.Image:
    img = image.copy()
    alpha = img.getchannel("A")
    alpha = alpha.point(lambda a: 0 if a < 36 else 255 if a > 220 else a)
    img.putalpha(alpha)
    return img
