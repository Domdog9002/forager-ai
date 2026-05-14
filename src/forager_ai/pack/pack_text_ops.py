"""Scoped text read/write for configs, KubeJS, CraftTweaker scripts, and datapacks — with backups."""

from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Sequence, Tuple

from ..fs.safe_writer import ensure_allowed_extension, resolve_under_root, write_text_utf8_nobom

_EDITABLE_TOP = ("config/", "kubejs/", "scripts/", "datapacks/")


def assert_editable_rel(rel_path: str) -> None:
    n = rel_path.replace("\\", "/").lstrip("/").lower()
    ok = any(n == p.rstrip("/") or n.startswith(p) for p in _EDITABLE_TOP)
    if not ok:
        raise ValueError(f"Path must start with one of {[p.rstrip('/') for p in _EDITABLE_TOP]}: {rel_path!r}")

_DEFAULT_TEXT_EXT = (
    ".json",
    ".toml",
    ".cfg",
    ".properties",
    ".txt",
    ".md",
    ".mcmeta",
    ".js",
    ".ts",
    ".zs",
    ".zs.backup",
)


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def list_pack_text_files(
    pack_root: str,
    *,
    max_files: int = 800,
    allowed_extensions: Sequence[str] = _DEFAULT_TEXT_EXT,
) -> List[str]:
    """Return posix-relative paths under allowed top folders, sorted."""
    root = os.path.realpath(str(pack_root or "").strip())
    if not root or not os.path.isdir(root):
        return []
    allow = {e.lower() for e in allowed_extensions}
    out: List[str] = []
    tops = tuple(p.rstrip("/") for p in _EDITABLE_TOP)
    for top in tops:
        base = os.path.join(root, top)
        if not os.path.isdir(base):
            continue
        for dirpath, _, names in os.walk(base):
            for fn in sorted(names):
                ext = os.path.splitext(fn)[1].lower()
                if ext not in allow:
                    continue
                fp = os.path.join(dirpath, fn)
                try:
                    rel = os.path.relpath(fp, root).replace("\\", "/")
                except ValueError:
                    continue
                if rel.startswith("../"):
                    continue
                out.append(rel)
                if len(out) >= int(max_files):
                    return sorted(out)
    return sorted(out)


def read_pack_text_file(pack_root: str, rel_path: str, *, max_bytes: int = 1_500_000) -> str:
    assert_editable_rel(rel_path)
    safe = resolve_under_root(pack_root, rel_path)
    with open(safe.resolved_path, "r", encoding="utf-8", errors="replace") as f:
        return f.read(int(max_bytes))


def backup_and_write_pack_text(
    pack_root: str,
    rel_path: str,
    content: str,
    *,
    allowed_extensions: Iterable[str] = _DEFAULT_TEXT_EXT,
) -> Tuple[str, str]:
    """
    Copy existing file into ``<root>/backups/forager_text_<UTC>/`` then UTF-8 write (no BOM).

    Returns ``(backup_dir, rel_path_norm)``.
    """
    assert_editable_rel(rel_path)
    ensure_allowed_extension(rel_path, allowed_extensions)
    safe = resolve_under_root(pack_root, rel_path)
    bp = os.path.join(pack_root, "backups", f"forager_text_{_utc_stamp()}")
    os.makedirs(bp, exist_ok=True)
    if os.path.isfile(safe.resolved_path):
        dest = os.path.join(bp, os.path.basename(safe.resolved_path))
        shutil.copy2(safe.resolved_path, dest)
    meta = os.path.join(bp, "forager_backup_meta.json")
    with open(meta, "w", encoding="utf-8") as f:
        json.dump({"rel_path": safe.rel_path, "pack_root": os.path.realpath(pack_root)}, f, indent=2, ensure_ascii=True)
    write_text_utf8_nobom(safe.resolved_path, content)
    return bp, safe.rel_path


def build_pack_profile_from_lock(
    lock_payload: dict, *, name: str = "profile", roles: Optional[List[str]] = None
) -> dict:
    """Minimal export: mod ids + optional **roles** (e.g. client-min, server, dev-tools)."""
    jars = lock_payload.get("jars") if isinstance(lock_payload.get("jars"), list) else []
    ids = sorted(
        {
            str(j.get("mod_id") or "").strip().lower()
            for j in jars
            if isinstance(j, dict) and str(j.get("mod_id") or "").strip()
        }
    )
    rlist: List[str] = []
    if isinstance(roles, list):
        rlist = [str(x).strip()[:40] for x in roles if str(x).strip()][:12]
    return {
        "schema": "forager_pack_profile_v1",
        "name": (name or "profile").strip()[:120],
        "roles": rlist,
        "mod_ids": ids,
        "source_jar_rows": len(jars),
    }
