"""Rank Modrinth (and structurally similar CurseForge) file rows when strict filters miss."""

from __future__ import annotations

from typing import List, Optional, Tuple

from ..dev.instance_matrix import parse_mc_version
from .mod_downloader import ModInfo


def _dist_mc(want: Tuple[int, int, int], got: Tuple[int, int, int]) -> int:
    return abs(want[0] - got[0]) * 10_000 + abs(want[1] - got[1]) * 100 + abs(want[2] - got[2])


def score_modrinth_file_row(mod: ModInfo, want_mc: str, want_loader: Optional[str]) -> int:
    """Lower is better."""
    want_t = parse_mc_version(want_mc) or (1, 20, 1)
    best = 1_000_000
    for gv in mod.minecraft_versions or []:
        t = parse_mc_version(str(gv))
        if t:
            best = min(best, _dist_mc(want_t, t))
    if best >= 1_000_000:
        best = 50_000
    lo = (want_loader or "").strip().lower()
    mlo = [str(x).strip().lower() for x in (mod.loaders or []) if str(x).strip()]
    if lo and lo != "vanilla" and mlo and lo not in mlo:
        best += 8_000
    return int(best)


def rank_modrinth_versions(
    versions: List[ModInfo],
    *,
    want_mc: str,
    want_loader: Optional[str],
) -> List[ModInfo]:
    """Stable-sort ``versions`` by MC/loader fit, then file size."""
    if not versions:
        return []
    scored = sorted(
        versions,
        key=lambda m: (
            score_modrinth_file_row(m, want_mc, want_loader),
            -(int(m.file_size or 0)),
            str(m.file_name or ""),
        ),
    )
    return scored


def format_solver_hint_lines(
    ranked: List[ModInfo],
    want_mc: str,
    want_loader: Optional[str],
    *,
    limit: int = 4,
) -> List[str]:
    """Short human lines for UI (no HTML)."""
    lines: List[str] = []
    for m in ranked[: max(1, int(limit))]:
        gvs = ", ".join(str(x) for x in (m.minecraft_versions or [])[:4])
        if len(m.minecraft_versions or []) > 4:
            gvs += ", …"
        lds = ", ".join(str(x) for x in (m.loaders or [])[:4])
        sc = score_modrinth_file_row(m, want_mc, want_loader)
        lines.append(
            f"score **{sc}** — `{m.file_name}` — MC: {gvs or '—'} — loaders: {lds or '—'}"
        )
    return lines
