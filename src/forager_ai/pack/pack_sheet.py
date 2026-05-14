"""Markdown pack sheet from a game root (mods lock snapshot)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List

from ..ops.mods_folder_lockfile import build_game_root_mods_lock


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_pack_sheet_markdown(
    game_root: str,
    *,
    title: str,
    lock_payload: Dict[str, Any] | None = None,
) -> str:
    """Return UTF-8 markdown text for sharing (Discord/wiki)."""
    payload = lock_payload if isinstance(lock_payload, dict) else build_game_root_mods_lock(game_root)
    jars: List[Dict[str, Any]] = payload.get("jars") if isinstance(payload.get("jars"), list) else []
    lines = [
        f"# {title}",
        "",
        f"_Generated {_utc_iso()} · game folder `{payload.get('game_root_basename') or ''}`_",
        "",
        f"**Mod jars:** {len(jars)}",
        "",
        "| File | mod id | version | size (bytes) | enabled |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for row in sorted(jars, key=lambda r: str(r.get("rel") or "").lower())[:600]:
        rel = str(row.get("rel") or "").replace("|", "\\|")
        mid = str(row.get("mod_id") or "").replace("|", "\\|")
        ver = str(row.get("jar_version") or "").replace("|", "\\|")
        sz = int(row.get("size_bytes") or 0)
        en = "yes" if row.get("enabled", True) else "no"
        lines.append(f"| `{rel}` | `{mid}` | {ver} | {sz} | {en} |")
    if len(jars) > 600:
        lines.append("")
        lines.append(f"_… {len(jars) - 600} more rows omitted for size._")
    return "\n".join(lines) + "\n"
