"""
Reproducible snapshot of a Minecraft instance (or pack) ``mods/`` tree.

Used for exports, diffs, and future repair flows. Best-effort metadata via
``read_jar_mod_metadata``; hashes are SHA-256 of on-disk bytes.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..launcher.jar_mod_metadata import read_jar_mod_metadata
from .advanced_toolkit import sha256_file

_SCHEMA = 1
_DEFAULT_CAP = 520


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _logical_jar_key(rel_posix: str) -> str:
    """Basename with ``.jar.disabled`` normalized to ``.jar`` for coarse diff pairing."""
    name = Path(rel_posix.replace("\\", "/")).name
    low = name.lower()
    if low.endswith(".jar.disabled"):
        return name[: -len(".disabled")]
    return name


def build_game_root_mods_lock(game_root: str, *, max_files: int = _DEFAULT_CAP) -> Dict[str, Any]:
    """
    Scan ``<game_root>/mods`` recursively for ``*.jar`` and ``*.jar.disabled``.

    Returns a JSON-serializable dict (does not write to disk).
    """
    root = Path(str(game_root or "").strip())
    mods_dir = root / "mods"
    jars: List[Dict[str, Any]] = []
    note = ""
    if not root.is_dir():
        return {
            "schema_version": _SCHEMA,
            "kind": "forager_mods_lock",
            "generated_at": _utc_iso(),
            "game_root_basename": "",
            "mods_dir_present": False,
            "jar_limit": int(max_files),
            "truncated": False,
            "jars": [],
            "note": "Game root is not a directory.",
        }
    if not mods_dir.is_dir():
        return {
            "schema_version": _SCHEMA,
            "kind": "forager_mods_lock",
            "generated_at": _utc_iso(),
            "game_root_basename": root.name,
            "mods_dir_present": False,
            "jar_limit": int(max_files),
            "truncated": False,
            "jars": [],
            "note": "No mods/ folder under this root.",
        }

    truncated = False
    n = 0
    for base, _, names in os.walk(str(mods_dir)):
        for fn in sorted(names):
            fl = fn.lower()
            if fl.endswith(".jar.disabled"):
                pass
            elif not fl.endswith(".jar"):
                continue
            fp = Path(base) / fn
            try:
                rel = Path(os.path.relpath(str(fp), str(root))).as_posix()
            except ValueError:
                rel = fn
            try:
                st = fp.stat()
                size_b = int(st.st_size)
                mtime = float(st.st_mtime)
            except OSError:
                continue
            try:
                digest = sha256_file(str(fp))
            except OSError:
                digest = ""
            meta = read_jar_mod_metadata(str(fp))
            mid = str(meta.get("mod_id") or "").strip()
            if ":" in mid:
                mid = mid.split(":", 1)[-1].strip()
            ver = str(meta.get("version") or "").strip()
            jars.append(
                {
                    "rel": rel,
                    "logical_key": _logical_jar_key(rel),
                    "sha256": digest,
                    "size_bytes": size_b,
                    "mtime": mtime,
                    "mod_id": mid.lower() if mid else "",
                    "jar_version": ver[:120] if ver else "",
                    "enabled": not fl.endswith(".jar.disabled"),
                }
            )
            n += 1
            if n >= int(max_files):
                truncated = True
                note = f"Scan capped at {max_files} jar entries."
                break
        if truncated:
            break

    jars.sort(key=lambda r: str(r.get("rel") or "").lower())
    return {
        "schema_version": _SCHEMA,
        "kind": "forager_mods_lock",
        "generated_at": _utc_iso(),
        "game_root_basename": root.name,
        "mods_dir_present": True,
        "jar_limit": int(max_files),
        "truncated": truncated,
        "jars": jars,
        "note": note,
    }


def write_game_root_mods_lock(
    game_root: str, *, max_files: int = _DEFAULT_CAP, write_attestation: bool = False
) -> str:
    """Write ``forager_mods.lock.json`` next to ``game_root`` (UTF-8, no BOM). Returns path."""
    root = Path(str(game_root or "").strip())
    payload = build_game_root_mods_lock(str(root), max_files=max_files)
    out = root / "forager_mods.lock.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=True)
    if write_attestation:
        from .lock_attestation import write_lock_attestation_sidecar

        write_lock_attestation_sidecar(str(out))
    return str(out)


def compare_mods_roots(game_root_a: str, game_root_b: str, *, max_files: int = _DEFAULT_CAP) -> Dict[str, Any]:
    """
    Compare two game roots' ``mods/`` trees by **logical jar basename**
    (``foo.jar.disabled`` pairs with ``foo.jar``).

    Same basename in different subfolders can collide — rare; see ``collisions`` when rel paths disagree.
    """
    pa = build_game_root_mods_lock(game_root_a, max_files=max_files)
    pb = build_game_root_mods_lock(game_root_b, max_files=max_files)
    by_key_a = _index_by_logical_key(pa.get("jars") or [])
    by_key_b = _index_by_logical_key(pb.get("jars") or [])

    keys_a = set(by_key_a)
    keys_b = set(by_key_b)
    only_a = sorted(keys_a - keys_b, key=str.lower)
    only_b = sorted(keys_b - keys_a, key=str.lower)
    changed: List[Dict[str, Any]] = []
    collisions: List[Dict[str, Any]] = []
    for k in sorted(keys_a & keys_b, key=str.lower):
        ea = by_key_a[k]
        eb = by_key_b[k]
        if str(ea.get("rel")) != str(eb.get("rel")):
            collisions.append({"logical_key": k, "rel_a": ea.get("rel"), "rel_b": eb.get("rel")})
        ha = str(ea.get("sha256") or "")
        hb = str(eb.get("sha256") or "")
        if ha and hb and ha != hb:
            changed.append(
                {
                    "logical_key": k,
                    "rel_a": ea.get("rel"),
                    "rel_b": eb.get("rel"),
                    "sha256_a": ha[:16] + "…",
                    "sha256_b": hb[:16] + "…",
                    "mod_id_a": ea.get("mod_id"),
                    "mod_id_b": eb.get("mod_id"),
                }
            )

    return {
        "generated_at": _utc_iso(),
        "root_a_basename": (Path(str(game_root_a).strip()).name if game_root_a else ""),
        "root_b_basename": (Path(str(game_root_b).strip()).name if game_root_b else ""),
        "truncated_a": bool(pa.get("truncated")),
        "truncated_b": bool(pb.get("truncated")),
        "only_in_a": [{"logical_key": k, "rel": by_key_a[k].get("rel")} for k in only_a],
        "only_in_b": [{"logical_key": k, "rel": by_key_b[k].get("rel")} for k in only_b],
        "same_logical_jar_different_hash": changed,
        "basename_collisions": collisions,
    }


def _index_by_logical_key(jars: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    for row in jars:
        if not isinstance(row, dict):
            continue
        lk = str(row.get("logical_key") or "").strip()
        if not lk:
            continue
        if lk in out:
            # Keep first; flag handled in compare via rel mismatch
            continue
        out[lk] = row
    return out


_SURFACE_SUBDIRS = (
    "resourcepacks",
    "shaderpacks",
    "config",
    "datapacks",
    "kubejs",
    "scripts",
)


def _shallow_filenames(game_root: str, rel: str, *, max_names: int = 4000) -> List[str]:
    """Direct children that are files under ``<game_root>/<rel>`` (no recursion)."""
    d = Path(str(game_root or "").strip()) / rel.replace("\\", "/").strip("/")
    if not d.is_dir():
        return []
    out: List[str] = []
    try:
        for p in sorted(d.iterdir()):
            if p.is_file():
                out.append(p.name)
                if len(out) >= int(max_names):
                    break
    except OSError:
        return []
    return out


def compare_surface_folders(game_root_a: str, game_root_b: str, *, max_names: int = 4000) -> Dict[str, Any]:
    """
    Shallow compare of common instance/pack folders (top-level files only per folder).

    Pairs with ``compare_mods_roots`` for a broader **surface** diff without walking
    entire ``config/`` trees.
    """
    sections: Dict[str, Any] = {}
    for sub in _SURFACE_SUBDIRS:
        a = set(_shallow_filenames(game_root_a, sub, max_names=max_names))
        b = set(_shallow_filenames(game_root_b, sub, max_names=max_names))
        sections[sub] = {
            "only_in_a": sorted(a - b, key=str.lower),
            "only_in_b": sorted(b - a, key=str.lower),
            "in_both_count": len(a & b),
        }
    return {
        "generated_at": _utc_iso(),
        "root_a_basename": Path(str(game_root_a).strip()).name if game_root_a else "",
        "root_b_basename": Path(str(game_root_b).strip()).name if game_root_b else "",
        "sections": sections,
        "note": "Top-level files only per folder; nested config/scripts differences are not expanded.",
    }


_CONFIG_TEXT_EXT = (
    ".json",
    ".toml",
    ".cfg",
    ".properties",
    ".txt",
    ".md",
    ".mcmeta",
    ".yml",
    ".yaml",
)


def _walk_limited_text_files(root: Path, *, max_files: int) -> List[str]:
    out: List[str] = []
    if not root.is_dir():
        return out
    for dirpath, _, names in os.walk(str(root)):
        for fn in sorted(names):
            ext = Path(fn).suffix.lower()
            if ext not in {e.lower() for e in _CONFIG_TEXT_EXT}:
                continue
            fp = Path(dirpath) / fn
            try:
                rel = fp.relative_to(root).as_posix()
            except ValueError:
                continue
            out.append(rel)
            if len(out) >= int(max_files):
                return out
    return out


def compare_config_deep_limited(
    game_root_a: str,
    game_root_b: str,
    *,
    subdir: str = "config",
    max_files_per_side: int = 400,
    max_bytes_each: int = 256_000,
) -> Dict[str, Any]:
    """
    Recursive compare of text-ish files under one subdirectory (default ``config/``).

    Pairs with ``compare_surface_folders`` for a **deeper** (but capped) config diff.
    """
    sub = str(subdir or "config").replace("\\", "/").strip("/")
    ra = Path(str(game_root_a or "").strip()) / sub
    rb = Path(str(game_root_b or "").strip()) / sub
    rels_a = set(_walk_limited_text_files(ra, max_files=max_files_per_side))
    rels_b = set(_walk_limited_text_files(rb, max_files=max_files_per_side))
    only_a = sorted(rels_a - rels_b, key=str.lower)
    only_b = sorted(rels_b - rels_a, key=str.lower)
    changed: List[Dict[str, Any]] = []
    truncated_reads = False
    for rel in sorted(rels_a & rels_b, key=str.lower):
        fa = ra / rel
        fb = rb / rel
        try:
            if fa.stat().st_size > int(max_bytes_each) or fb.stat().st_size > int(max_bytes_each):
                truncated_reads = True
                continue
            ha = sha256_file(str(fa))
            hb = sha256_file(str(fb))
        except OSError:
            continue
        if ha != hb:
            changed.append(
                {
                    "rel": f"{sub}/{rel}",
                    "sha256_a": ha[:12] + "…",
                    "sha256_b": hb[:12] + "…",
                }
            )
    return {
        "generated_at": _utc_iso(),
        "subdir": sub,
        "root_a_basename": Path(str(game_root_a).strip()).name if game_root_a else "",
        "root_b_basename": Path(str(game_root_b).strip()).name if game_root_b else "",
        "only_rels_in_a": [f"{sub}/{x}" for x in only_a],
        "only_rels_in_b": [f"{sub}/{x}" for x in only_b],
        "same_rel_different_hash": changed,
        "truncated_skipped_large_files": truncated_reads,
        "note": f"Text-like extensions only; max {max_files_per_side} files scanned per root under `{sub}/`.",
    }
