"""Format mods / surface compares for Hub AI context (Batch 6 · diff-aware Hub)."""

from __future__ import annotations

from typing import Any, Dict, List


def format_hub_reference_diff_narrative(
    *,
    mods_cmp: Dict[str, Any],
    surface_cmp: Dict[str, Any],
    label_active: str,
    label_reference: str,
    max_chars: int = 4800,
) -> str:
    """Human-readable deltas for inference (capped). **Active** root is authoritative context; reference is baseline."""
    lines: List[str] = [
        f"## Pack pair diff (mods + shallow surface folders)",
        f"**Active (this thread):** {label_active.strip()[:240]}",
        f"**Reference:** {label_reference.strip()[:240]}",
        "_Use this block for merge-risk, parity, regression — not as the live manifest.",
        "",
    ]

    lines.append("### Mods folder (logical jar keys)")
    oa = mods_cmp.get("only_in_a") or []
    ob = mods_cmp.get("only_in_b") or []
    ch = mods_cmp.get("same_logical_jar_different_hash") or []
    lines.append(f"- Only on **active** (not reference): **{len(oa)}** jars (showing up to 28)")
    for row in oa[:28]:
        if isinstance(row, dict):
            lk = str(row.get("logical_key") or "")
            lines.append(f"  - `{lk}` — rel `{str(row.get('rel') or '')[:120]}`")
    lines.append(f"- Only on **reference** (missing on active unless intentional): **{len(ob)}** (up to 28)")
    for row in ob[:28]:
        if isinstance(row, dict):
            lk = str(row.get("logical_key") or "")
            lines.append(f"  - `{lk}` — rel `{str(row.get('rel') or '')[:120]}`")
    lines.append(f"- Same basename, **different file hash**: **{len(ch)}** (up to 18)")
    for row in ch[:18]:
        if isinstance(row, dict):
            lk = str(row.get("logical_key") or "")
            lines.append(f"  - `{lk}` — hash A `{row.get('sha256_a','')}` vs B `{row.get('sha256_b','')}`")
    cols = mods_cmp.get("basename_collisions") or []
    if cols:
        lines.append(f"- **Path collisions** (same logical key, different rel): **{len(cols)}** (show first 10)")
        for row in cols[:10]:
            if isinstance(row, dict):
                lines.append(f"  - `{row.get('logical_key')}` A `{row.get('rel_a')}` · B `{row.get('rel_b')}`")
    if mods_cmp.get("truncated_a") or mods_cmp.get("truncated_b"):
        lines.append("- **Note:** one or both mods scans were truncated at the file cap.")

    lines.extend(["", "### Shallow folders (top-level files only)", ""])

    secs = surface_cmp.get("sections") or {}
    if isinstance(secs, dict):
        for sub in ("kubejs", "scripts", "config", "datapacks", "resourcepacks", "shaderpacks"):
            if sub not in secs:
                continue
            block = secs[sub]
            if not isinstance(block, dict):
                continue
            oa_n = len(block.get("only_in_a") or [])
            ob_n = len(block.get("only_in_b") or [])
            if oa_n + ob_n == 0:
                continue
            lines.append(f"**{sub}/** — only on active: **{oa_n}** · only on reference: **{ob_n}** (cap 14 each)")
            for nm in list(block.get("only_in_a") or [])[:14]:
                lines.append(f"  - active-only file: `{nm}`")
            for nm in list(block.get("only_in_b") or [])[:14]:
                lines.append(f"  - ref-only file (check parity): `{nm}`")

    if surface_cmp.get("note"):
        lines.extend(["", f"_Surface note:_ {surface_cmp['note']}"])

    blob = "\n".join(lines).strip()
    if len(blob) > max_chars:
        return blob[: max_chars - 48] + "\n… (reference pair diff truncated — reduce pack size or raise cap)."
    return blob
