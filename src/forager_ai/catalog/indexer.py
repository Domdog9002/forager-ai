from __future__ import annotations

import hashlib
import json
import os
import re
import zipfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from .taxonomy import enrich_catalog


def _forager_dir(pack_root: str) -> str:
    d = os.path.join(pack_root, ".forager")
    os.makedirs(d, exist_ok=True)
    return d


def _jar_mod_id(filename: str) -> str:
    base = filename.replace(".jar", "").replace(".disabled", "").lower()
    base = base.split("+")[0]
    first = base.split("-")[0].strip("._")
    slug = re.sub(r"[^a-z0-9_]+", "_", first).strip("_")
    return (slug or "unknown")[:64]


def _scan_datapack_namespace(ns_path: str, namespace: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []

    def add(kind: str, rel_parts: List[str]) -> None:
        target = os.path.join(ns_path, *rel_parts)
        if not os.path.isdir(target):
            return
        for fn in os.listdir(target):
            if not fn.endswith(".json"):
                continue
            rid = fn[: -len(".json")]
            full_id = f"{namespace}:{rid}"
            rows.append(
                {
                    "id": full_id,
                    "type": kind,
                    "mod_id": namespace,
                    "source": "datapack",
                }
            )

    add("item", ["items"])
    add("mob", ["entity_type"])
    add("structure", ["worldgen", "structure"])
    add("structure_set", ["worldgen", "structure_set"])
    return rows


def _atlas_images_dir(pack_root: str) -> str:
    path = os.path.join(_forager_dir(pack_root), "atlas_images")
    os.makedirs(path, exist_ok=True)
    return path


def _safe_zip_image_name(name: str) -> bool:
    low = name.lower()
    return low.endswith((".png", ".jpg", ".jpeg", ".webp")) and not low.startswith("__macosx/")


def _extract_logo_path_from_json(raw: bytes) -> str:
    try:
        data = json.loads(raw.decode("utf-8", errors="replace"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if isinstance(data, dict):
        icon = data.get("icon") or data.get("logoFile") or data.get("logo_file")
        if isinstance(icon, str):
            return icon.strip().lstrip("/")
    return ""


def _extract_logo_path_from_toml(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace")
    match = re.search(r"(?im)^\s*logoFile\s*=\s*[\"']([^\"']+)[\"']", text)
    return match.group(1).strip().lstrip("/") if match else ""


def extract_jar_preview_image(pack_root: str, jar_path: str, mod_id: str) -> str:
    """Extract a small best-effort preview from a jar for the atlas cache."""
    try:
        with zipfile.ZipFile(jar_path) as zf:
            names = zf.namelist()
            priority: List[str] = []
            direct = [
                "pack.png",
                "icon.png",
                "logo.png",
                f"assets/{mod_id}/icon.png",
                f"assets/{mod_id}/logo.png",
            ]
            priority.extend([name for name in direct if name in names])
            for meta_name in ("fabric.mod.json", "META-INF/mods.toml", "quilt.mod.json"):
                if meta_name not in names:
                    continue
                raw = zf.read(meta_name)
                logo = _extract_logo_path_from_toml(raw) if meta_name.endswith(".toml") else _extract_logo_path_from_json(raw)
                if logo and logo in names:
                    priority.append(logo)
            texture_candidates = [
                name for name in names
                if _safe_zip_image_name(name)
                and "/textures/" in name.lower()
                and any(part in name.lower() for part in ("/item/", "/block/", "/entity/"))
            ]
            priority.extend(texture_candidates[:24])
            priority.extend([name for name in names if _safe_zip_image_name(name) and Path(name).name.lower() in {"pack.png", "icon.png", "logo.png"}])
            seen: set[str] = set()
            for name in priority:
                if name in seen or name not in names or not _safe_zip_image_name(name):
                    continue
                seen.add(name)
                data = zf.read(name)
                if not data or len(data) > 1_500_000:
                    continue
                suffix = Path(name).suffix.lower() or ".png"
                digest = hashlib.sha256(f"{jar_path}:{name}".encode("utf-8")).hexdigest()[:20]
                out = os.path.join(_atlas_images_dir(pack_root), f"jar_{mod_id}_{digest}{suffix}")
                if not os.path.exists(out):
                    with open(out, "wb") as fh:
                        fh.write(data)
                return out
    except (OSError, zipfile.BadZipFile, KeyError):
        return ""
    return ""


def _scan_mods_jars(pack_root: str, mods_dir: str) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(mods_dir):
        return rows
    for fn in os.listdir(mods_dir):
        if not fn.lower().endswith(".jar"):
            continue
        mid = _jar_mod_id(fn)
        jar_path = os.path.join(mods_dir, fn)
        image_path = extract_jar_preview_image(pack_root, jar_path, mid)
        rows.append(
            {
                "id": f"_modjar:{mid}",
                "type": "mod_jar",
                "mod_id": mid,
                "source": "mods_folder",
                "file": fn,
                "image_path": image_path,
            }
        )
    return rows


def build_pack_content_index(pack_root: str) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    data_root = os.path.join(pack_root, "data")
    if os.path.isdir(data_root):
        for namespace in sorted(os.listdir(data_root)):
            ns_path = os.path.join(data_root, namespace)
            if not os.path.isdir(ns_path) or namespace.startswith("."):
                continue
            entries.extend(_scan_datapack_namespace(ns_path, namespace))

    entries.extend(_scan_mods_jars(pack_root, os.path.join(pack_root, "mods")))
    entries = enrich_catalog(entries)

    raw = json.dumps(entries, sort_keys=True, ensure_ascii=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()[:24]

    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack_root": os.path.abspath(pack_root),
        "index_hash": digest,
        "counts": dict(Counter(e.get("type", "?") for e in entries)),
        "entries": entries,
    }
    return index


def save_index(pack_root: str, index: Dict[str, Any]) -> str:
    path = os.path.join(_forager_dir(pack_root), "content_index.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(index, fh, indent=2, ensure_ascii=True)
    return path


def load_index(pack_root: str) -> Dict[str, Any] | None:
    path = os.path.join(_forager_dir(pack_root), "content_index.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None


def summarize_for_council(index: Dict[str, Any], *, max_sample: int = 120) -> Dict[str, Any]:
    entries = index.get("entries") or []
    by_mod = Counter((e.get("mod_id") or "?") for e in entries)
    by_tier = Counter((e.get("progression_tier") or "?") for e in entries)
    tag_counts: Counter[str] = Counter()
    for e in entries:
        for t in e.get("taxonomy_tags") or []:
            tag_counts[t] += 1
    bosses = [e for e in entries if "role:boss" in (e.get("taxonomy_tags") or [])][:40]
    legendary = [e for e in entries if "weapon:legendary" in (e.get("taxonomy_tags") or [])][:40]
    sample = entries[:max_sample]
    return {
        "index_meta": {
            "generated_at": index.get("generated_at"),
            "index_hash": index.get("index_hash"),
            "total_entries": len(entries),
            "counts": index.get("counts"),
        },
        "top_mods": dict(by_mod.most_common(24)),
        "progression_tiers": dict(by_tier),
        "top_tags": dict(tag_counts.most_common(32)),
        "sample_bosses": bosses,
        "sample_legendary_items": legendary,
        "entry_samples": sample,
        "council_instructions": (
            "Validate taxonomy tags and progression tiers for a modpack content atlas. "
            "Flag misclassified items/mobs/structures, missing boss tags, broken progression jumps, "
            "and theme mismatches (fantasy vs sci-fi). Suggest tag/filter improvements."
        ),
    }


def save_atlas_council_report(pack_root: str, report: Dict[str, Any], *, summary: Dict[str, Any]) -> str:
    path = os.path.join(_forager_dir(pack_root), "content_atlas_council.json")
    out = {
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "index_hash": summary.get("index_meta", {}).get("index_hash"),
        "council_report": report,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=True)
    return path


def load_atlas_council_report(pack_root: str) -> Dict[str, Any] | None:
    path = os.path.join(_forager_dir(pack_root), "content_atlas_council.json")
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (json.JSONDecodeError, OSError):
        return None
