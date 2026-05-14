"""
Heuristic loader hints from an on-disk instance folder (best-effort).
"""

from __future__ import annotations

from pathlib import Path
from typing import List


def heuristic_loader_markers(game_root: str) -> List[str]:
    """Return human-readable markers found under ``game_root`` (may be empty)."""
    root = Path(str(game_root or "").strip())
    if not root.is_dir():
        return []
    markers: List[str] = []
    if (root / ".fabric").is_dir():
        markers.append(".fabric/ (Fabric loader cache)")
    if (root / "mods").is_dir():
        for p in sorted((root / "mods").glob("*.jar"))[:48]:
            pn = p.name.lower()
            if any(x in pn for x in ("fabric", "forge", "neoforge", "quilt")):
                markers.append(f"mods/*.jar — inspect `{p.name}` for loader family")
                break
    if (root / "versions").is_dir():
        markers.append("versions/ (vanilla or launcher layout)")
    return markers[:8]
