from __future__ import annotations

import os
from typing import Any, Dict, List, Tuple


def _safe_walk_size_bytes(root: str) -> Tuple[int, int]:
    total = 0
    count = 0
    if not os.path.isdir(root):
        return total, count
    for base, _, files in os.walk(root):
        for name in files:
            path = os.path.join(base, name)
            try:
                total += os.path.getsize(path)
                count += 1
            except OSError:
                continue
    return total, count


def _bytes_to_mb(value: int) -> float:
    return round(value / (1024 * 1024), 2)


def profile_pack(pack_root: str) -> Dict[str, Any]:
    paths = {
        "mods": os.path.join(pack_root, "mods"),
        "config": os.path.join(pack_root, "config"),
        "kubejs": os.path.join(pack_root, "kubejs"),
        "scripts": os.path.join(pack_root, "scripts"),
        "resourcepacks": os.path.join(pack_root, "resourcepacks"),
        "shaderpacks": os.path.join(pack_root, "shaderpacks"),
    }

    section_stats: Dict[str, Dict[str, Any]] = {}
    total_bytes = 0
    total_files = 0
    for section, path in paths.items():
        size_bytes, files_count = _safe_walk_size_bytes(path)
        section_stats[section] = {
            "path": path,
            "exists": os.path.isdir(path),
            "files_count": files_count,
            "size_bytes": size_bytes,
            "size_mb": _bytes_to_mb(size_bytes),
        }
        total_bytes += size_bytes
        total_files += files_count

    hot_mods: List[Dict[str, Any]] = []
    mods_dir = paths["mods"]
    if os.path.isdir(mods_dir):
        for filename in os.listdir(mods_dir):
            if not filename.lower().endswith(".jar"):
                continue
            full = os.path.join(mods_dir, filename)
            try:
                size = os.path.getsize(full)
            except OSError:
                continue
            hot_mods.append({"file": filename, "size_mb": _bytes_to_mb(size), "size_bytes": size})
    hot_mods.sort(key=lambda x: x["size_bytes"], reverse=True)

    findings: List[Dict[str, str]] = []
    if section_stats["mods"]["size_mb"] > 1200:
        findings.append(
            {
                "severity": "high",
                "message": "Large mods footprint detected (>1.2 GB). Consider trimming heavy content mods.",
            }
        )
    if section_stats["resourcepacks"]["size_mb"] > 700:
        findings.append(
            {
                "severity": "medium",
                "message": "Resource packs are heavy (>700 MB). This can increase stutter and startup time.",
            }
        )
    if section_stats["shaderpacks"]["files_count"] > 5:
        findings.append(
            {
                "severity": "medium",
                "message": "Multiple shaderpacks detected. Keep only active presets in pack for cleaner distribution.",
            }
        )

    return {
        "summary": {
            "total_files": total_files,
            "total_size_mb": _bytes_to_mb(total_bytes),
        },
        "sections": section_stats,
        "largest_mod_jars": hot_mods[:15],
        "findings": findings,
    }

