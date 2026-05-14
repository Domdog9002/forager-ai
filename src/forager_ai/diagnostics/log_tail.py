"""Read tail of Minecraft ``latest.log`` from common instance layouts."""

from __future__ import annotations

import os
from pathlib import Path
from typing import List


def _read_tail_text(path: Path, max_chars: int) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if len(raw) > max_chars * 4:
        raw = raw[-max_chars * 4 :]
    try:
        text = raw.decode("utf-8", errors="replace")
    except UnicodeDecodeError:
        text = raw.decode("latin-1", errors="replace")
    if len(text) > max_chars:
        return text[-max_chars:]
    return text


def find_latest_log_paths(game_root: str) -> List[str]:
    """Return existing log paths to try (newest preference order)."""
    root = Path(str(game_root or "").strip())
    cands = [
        root / "logs" / "latest.log",
        root / ".minecraft" / "logs" / "latest.log",
        root / "logs" / "debug.log",
    ]
    out: List[str] = []
    for p in cands:
        if p.is_file():
            out.append(str(p))
    return out


def tail_latest_log(game_root: str, *, max_chars: int = 120_000) -> str:
    """Return tail of the first found ``latest.log`` / ``debug.log``, or empty string."""
    for p in find_latest_log_paths(game_root):
        t = _read_tail_text(Path(p), max_chars)
        if t.strip():
            return t
    return ""
