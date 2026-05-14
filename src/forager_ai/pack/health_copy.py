"""Plain-language copy helpers for Pack Health (testable without Streamlit)."""
from __future__ import annotations


def humanize_conflict_type(type_str: str) -> str:
    key = str(type_str or "").strip().lower()
    return {
        "duplicate_content": "Duplicate mod",
        "incompatible_versions": "Wrong version",
        "missing_dependency": "Missing requirement",
        "circular_dependency": "Circular requirement",
        "resource_conflict": "Resource overlap",
        "api_conflict": "API clash",
        "performance_impact": "Performance concern",
        "known_incompatibility": "Known bad pairing",
    }.get(key, key.replace("_", " ").strip().title() or "Issue")


def pack_health_graph_node_cap(mods_n: int) -> int:
    n = int(mods_n)
    if n >= 300:
        return 72
    if n >= 150:
        return 100
    return 140
