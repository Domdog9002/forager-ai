"""Classify recent Minecraft log tails into coarse launch-risk signals (tail-only, heuristic)."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

from .log_tail import find_latest_log_paths, tail_latest_log

_SEVERITY_ORDER = ("critical", "high", "medium", "low")

# (overall_bucket, pattern_id, compiled regex)
_PATTERNS: List[Tuple[str, str, re.Pattern[str]]] = [
    ("critical", "class_not_found", re.compile(r"ClassNotFoundException|NoClassDefFoundError", re.I)),
    ("critical", "mixin_apply_fail", re.compile(r"Mixin apply failed|Mixin transformation of .* failed", re.I)),
    ("high", "mixin_trace", re.compile(r"org\.spongepowered\.asm\.mixin|MixinError", re.I)),
    ("high", "datapack_fail", re.compile(r"Failed to load data pack|Errors in currently loaded data packs", re.I)),
    ("medium", "mod_dep_fail", re.compile(r"Mod .* requires|requires .* between|Incompatible mods found", re.I)),
    ("medium", "missing_mod", re.compile(r"MissingModsException|Mod .* is missing|needs .* version", re.I)),
    ("low", "warn_generic", re.compile(r"\[WARN\].*mod|\bWARN\b.*(loader|fabric|forge)", re.I)),
]


def analyze_launch_log_tail(game_root: str, *, max_chars: int = 80_000) -> Dict[str, Any]:
    """
    Read a bounded tail from latest.log / debug.log and surface pattern hits.

    This is **not** a substitute for a full log review; severity is conservative.
    """
    root = str(game_root or "").strip()
    paths = find_latest_log_paths(root)
    log_path = paths[0] if paths else ""
    text = tail_latest_log(root, max_chars=max_chars) if root else ""
    hits: List[Dict[str, Any]] = []
    if not text.strip():
        return {
            "log_path": log_path,
            "tail_chars": 0,
            "hits": [],
            "overall_severity": "none",
            "note": "No readable log tail — launch signals unavailable.",
        }

    seen_spans: set[Tuple[int, int]] = set()
    for bucket, pid, rx in _PATTERNS:
        for m in rx.finditer(text):
            span = (m.start(), m.end())
            if span in seen_spans:
                continue
            seen_spans.add(span)
            start = max(0, m.start() - 40)
            end = min(len(text), m.end() + 120)
            snippet = " ".join(text[start:end].split())
            if len(snippet) > 220:
                snippet = snippet[:217] + "…"
            hits.append({"severity": bucket, "pattern_id": pid, "snippet": snippet})
            if len(hits) >= 24:
                break
        if len(hits) >= 24:
            break

    overall = "none"
    for sev in _SEVERITY_ORDER:
        if any(h.get("severity") == sev for h in hits):
            overall = sev
            break

    return {
        "log_path": log_path,
        "tail_chars": len(text),
        "hits": hits,
        "overall_severity": overall,
        "note": "Signals are from the newest log tail only; verify full latest.log when debugging.",
    }
