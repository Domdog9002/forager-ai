"""
Modrinth-based compat research helpers (read-only API, no auth required).
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

USER_AGENT = "ForagerAI/1.0 (+https://github.com/forager-ai) (compat research)"


def fetch_modrinth_project(slug_or_id: str, *, timeout_s: float = 25.0) -> Optional[Dict[str, Any]]:
    """GET /v2/project/{id}; returns None on 404."""
    slug = (slug_or_id or "").strip()
    if not slug:
        return None
    url = f"https://api.modrinth.com/v2/project/{quote(slug, safe='')}"
    try:
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=timeout_s)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        return None
    r.raise_for_status()
    data = r.json()
    return data if isinstance(data, dict) else None


def summarize_project_for_compat(p: Dict[str, Any]) -> str:
    """Short markdown-free summary for UI / AI context."""
    title = str(p.get("title") or p.get("slug") or "?")
    sid = str(p.get("slug") or "")
    desc = str(p.get("description") or "").strip()
    if len(desc) > 800:
        desc = desc[:800] + "…"
    cats = p.get("categories") or []
    cat_s = ", ".join(str(c) for c in cats[:12]) if isinstance(cats, list) else ""
    loaders = p.get("loaders") or []
    game_versions = p.get("game_versions") or []
    gv = ", ".join(str(v) for v in game_versions[:6]) if isinstance(game_versions, list) else ""
    ld = ", ".join(str(x) for x in loaders[:8]) if isinstance(loaders, list) else ""
    issues = str(p.get("issues_url") or "").strip()
    src = str(p.get("source_url") or "").strip()
    lines = [
        f"Project: {title} (`{sid}`)",
        f"Loaders: {ld or '—'} · MC versions (sample): {gv or '—'}",
        f"Categories: {cat_s or '—'}",
    ]
    if desc:
        lines.append("Description (trimmed):")
        lines.append(desc)
    if issues:
        lines.append(f"Issues: {issues}")
    if src:
        lines.append(f"Source: {src}")
    return "\n".join(lines)


def search_modrinth_projects(query: str, *, limit: int = 8, timeout_s: float = 25.0) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    try:
        r = requests.get(
            "https://api.modrinth.com/v2/search",
            params={"query": q, "limit": str(max(1, min(limit, 20)))},
            headers={"User-Agent": USER_AGENT},
            timeout=timeout_s,
        )
        r.raise_for_status()
        data = r.json()
    except requests.RequestException:
        return []
    hits = data.get("hits") if isinstance(data, dict) else None
    if not isinstance(hits, list):
        return []
    return [h for h in hits if isinstance(h, dict)]
