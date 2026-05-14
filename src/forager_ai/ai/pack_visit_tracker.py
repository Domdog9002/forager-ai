"""Track coarse file mtimes per pack root for 'what changed since last visit' summaries."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple

from .enhancement_store import _base


SNAP_PATH = _base() / "pack_visit_snapshots.json"

_TEXT_LIKE = {
    ".toml",
    ".cfg",
    ".properties",
    ".json",
    ".txt",
    ".md",
    ".zs",
    ".js",
}


def _norm_root(path: str) -> str:
    try:
        return str(Path(os.path.normpath(os.path.expanduser(path))).resolve())
    except OSError:
        return str(path or "").strip()


def _load() -> Dict[str, Any]:
    p = SNAP_PATH
    if not p.is_file():
        return {"packs": {}}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"packs": {}}
    except (OSError, json.JSONDecodeError):
        return {"packs": {}}


def _save(data: Dict[str, Any]) -> None:
    try:
        SNAP_PATH.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")
    except OSError:
        pass


def _walk_track_files(root: Path, *, max_files: int = 400) -> Dict[str, float]:
    """Relative path -> mtime for text-like configs under pack."""
    out: Dict[str, float] = {}
    if not root.is_dir():
        return out
    count = 0
    for dirpath, _dirnames, filenames in os.walk(root):
        # skip heavy dirs
        low = Path(dirpath).relative_to(root).as_posix().lower() if root != Path(dirpath) else ""
        if any(seg in low for seg in (".git", "node_modules", "build", "/mods/", "\\mods\\")):
            continue
        for fn in filenames:
            suf = Path(fn).suffix.lower()
            if suf not in _TEXT_LIKE and fn not in ("manifest.json", "modrinth.index.json"):
                continue
            fp = Path(dirpath) / fn
            if not fp.is_file():
                continue
            count += 1
            if count > max_files:
                return out
            try:
                rel = fp.relative_to(root).as_posix()
                out[rel] = fp.stat().st_mtime
            except OSError:
                continue
    return out


def compute_visit_delta(pack_root: str, pack_name: str, max_lines: int = 12) -> str:
    """Return a short human-readable summary of changed / new config files since last dashboard visit."""
    root = Path(_norm_root(pack_root))
    key = hashlib.sha1(str(root).encode("utf-8", errors="ignore")).hexdigest()[:16]
    current = _walk_track_files(root)
    data = _load()
    packs = data.setdefault("packs", {})
    prev_entry = packs.get(key) if isinstance(packs, dict) else None
    prev_files: Dict[str, float] = {}
    if isinstance(prev_entry, dict):
        prev_files = {str(k): float(v) for k, v in (prev_entry.get("files") or {}).items() if isinstance(k, str)}

    changed: List[str] = []
    new_f: List[str] = []
    for rel, mt in current.items():
        if rel not in prev_files:
            new_f.append(rel)
        elif abs(prev_files[rel] - mt) > 0.5:
            changed.append(rel)

    packs[key] = {
        "label": pack_name[:120],
        "root": str(root)[:500],
        "files": current,
    }
    _save(data)

    lines: List[str] = []
    if not prev_files:
        lines.append(f"First visit snapshot for `{pack_name}` — tracking config-like files for next time.")
    else:
        if new_f:
            lines.append("New tracked files: " + ", ".join(sorted(new_f)[:max_lines]))
        if changed:
            lines.append("Modified tracked files: " + ", ".join(sorted(changed)[:max_lines]))
        if not new_f and not changed:
            lines.append("No tracked config edits since your last visit to this pack in Forager.")
    return "\n".join(lines)[:2500]


def snapshot_refresh_only(pack_root: str, pack_name: str) -> None:
    """Update snapshot without comparing (for background refresh)."""
    compute_visit_delta(pack_root, pack_name, max_lines=0)
