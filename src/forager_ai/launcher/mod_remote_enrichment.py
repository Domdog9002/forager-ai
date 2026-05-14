"""
Resolve mod icon URLs and summaries from Modrinth (public API) and CurseForge (API key).

Used as a fallback when jar-local metadata has no logo or thin description.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from urllib.parse import unquote

from .mod_downloader import ModDownloader, ModInfo


def _plain_from_md_chunk(md: str, limit: int = 900) -> str:
    if not md:
        return ""
    t = re.sub(r"```[\s\S]*?```", " ", md)
    t = re.sub(r"`([^`]+)`", r"\1", t)
    t = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", t)
    t = re.sub(r"#{1,6}\s*[^\n]+\n", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    if len(t) > limit:
        return t[: limit - 1] + "…"
    return t


def _slug_from_modrinth_url(url: Optional[str]) -> str:
    if not url or not isinstance(url, str):
        return ""
    m = re.search(r"modrinth\.com/mod/([^/?#]+)", url)
    if not m:
        return ""
    return unquote(m.group(1).strip()).lower()


def _slug_candidates(mod_id: str, file_stem: str) -> List[str]:
    seen: set = set()
    out: List[str] = []

    def add(s: str) -> None:
        s = (s or "").strip().lower()
        s = re.sub(r"[^a-z0-9._-]", "", s)
        if not s or s in seen:
            return
        seen.add(s)
        out.append(s)

    add(mod_id)
    mid = (mod_id or "").strip().lower()
    if "." in mid:
        add(mid.split(".")[-1])

    stem = file_stem or ""
    s = stem.lower().strip()
    s = re.sub(r"^\[[^\]]+\]\s*", "", s)
    s = re.sub(r"^\([^)]+\)\s*", "", s)
    for p in ("fabric-", "forge-", "neoforge-", "quilt-"):
        if s.startswith(p):
            s = s[len(p) :]
            break
    s = re.sub(r"[-_]v\d+[-_.].*$", "", s)
    s = re.sub(r"[-_](?:mc|forge|fabric)?[\d.]+.*$", "", s, flags=re.I)
    add(s.split("-")[0] if "-" in s else s)
    if "-" in s:
        add(s.replace(" ", ""))
    return out


def _pick_modrinth_hit(
    hits: List[ModInfo], mod_id: str, display_name: str, file_stem: str
) -> Optional[ModInfo]:
    if not hits:
        return None
    mid = (mod_id or "").strip().lower()
    dn = (display_name or "").strip().lower()
    stem = (file_stem or "").strip().lower()
    best: Optional[ModInfo] = None
    best_score = 4
    for i, h in enumerate(hits):
        slug = _slug_from_modrinth_url(h.project_url)
        name = (h.name or "").lower()
        score = 0
        if mid and slug == mid:
            score += 120
        if mid and mid in slug and slug != mid:
            score += 35
        if dn and name == dn:
            score += 90
        if dn and dn in name and name != dn:
            score += 30
        if stem and len(stem) > 2 and slug and stem in slug:
            score += 25
        if stem and len(stem) > 2 and name and stem in name:
            score += 15
        score -= i
        if score > best_score:
            best_score = score
            best = h
    return best


def _pick_curseforge_hit(
    hits: List[ModInfo], mod_id: str, display_name: str, file_stem: str
) -> Optional[ModInfo]:
    if not hits:
        return None
    mid = (mod_id or "").strip().lower()
    dn = (display_name or "").strip().lower()
    stem = (file_stem or "").strip().lower()
    best: Optional[ModInfo] = None
    best_score = 4
    for i, h in enumerate(hits):
        name = (h.name or "").lower()
        score = 0
        slug_guess = (h.project_url or "").rstrip("/").split("/")[-1].lower()
        if mid and slug_guess == mid:
            score += 110
        if mid and mid in slug_guess:
            score += 30
        if dn and name == dn:
            score += 85
        if dn and dn in name:
            score += 25
        if stem and len(stem) > 2 and stem in name:
            score += 18
        score -= i
        if score > best_score:
            best_score = score
            best = h
    return best


def _search_modrinth_loose(
    dl: ModDownloader,
    q: str,
    minecraft_version: Optional[str],
    loader: Optional[str],
    limit: int = 12,
) -> List[ModInfo]:
    q = (q or "").strip()
    if not q:
        return []
    hits = dl.search_modrinth(
        q, minecraft_version=minecraft_version, loader=loader, limit=limit
    )
    if hits or not loader:
        return hits
    return dl.search_modrinth(
        q, minecraft_version=minecraft_version, loader=None, limit=limit
    )


def _empty_remote() -> Dict[str, Any]:
    return {
        "remote_icon_url": None,
        "remote_summary": "",
        "remote_categories": [],
        "remote_project_url": None,
        "remote_source": None,
    }


def resolve_remote_mod_metadata(
    dl: ModDownloader,
    mod_id: str,
    display_name: str,
    file_stem: str,
    minecraft_version: Optional[str],
    loader: Optional[str],
) -> Dict[str, Any]:
    """
    Best-effort public/API lookup. Modrinth does not require an API key; CurseForge uses the
    downloader's configured key if present.
    """
    mid = (mod_id or "").strip()
    dn = (display_name or "").strip()
    stem = file_stem or ""
    if not mid and not dn and not stem:
        return _empty_remote()

    for slug in _slug_candidates(mid, stem):
        d = dl.get_modrinth_project_detail(slug)
        if not d:
            continue
        icon = d.get("icon_url")
        summary = (d.get("description") or "").strip()
        if not summary and d.get("body_markdown"):
            summary = _plain_from_md_chunk(str(d.get("body_markdown") or ""))
        if icon or summary or (d.get("categories") or []):
            cats = [str(c) for c in (d.get("categories") or []) if c]
            return {
                "remote_icon_url": icon,
                "remote_summary": summary or "",
                "remote_categories": cats,
                "remote_project_url": d.get("project_url"),
                "remote_source": "modrinth",
            }

    q = dn or mid or stem
    hits = _search_modrinth_loose(dl, q, minecraft_version, loader, limit=12)
    pick = _pick_modrinth_hit(hits, mid, dn, stem)
    if pick:
        detail = dl.get_modrinth_project_detail(pick.project_id)
        if detail:
            summary = (detail.get("description") or "").strip()
            if not summary and detail.get("body_markdown"):
                summary = _plain_from_md_chunk(str(detail.get("body_markdown") or ""))
            if not summary:
                summary = (pick.description or "").strip()
            cats = [str(c) for c in (detail.get("categories") or []) if c]
            if not cats and pick.categories:
                cats = list(pick.categories)
            return {
                "remote_icon_url": detail.get("icon_url") or pick.icon_url,
                "remote_summary": summary,
                "remote_categories": cats,
                "remote_project_url": detail.get("project_url") or pick.project_url,
                "remote_source": "modrinth",
            }
        return {
            "remote_icon_url": pick.icon_url,
            "remote_summary": (pick.description or "").strip(),
            "remote_categories": list(pick.categories or []),
            "remote_project_url": pick.project_url,
            "remote_source": "modrinth",
        }

    if dl.curseforge_configured():
        cf = dl.search_curseforge(
            q,
            minecraft_version=minecraft_version,
            loader=loader,
            limit=12,
        )
        cfp = _pick_curseforge_hit(cf, mid, dn, stem)
        if cfp and (cfp.icon_url or cfp.description):
            cats = list(cfp.categories or [])
            return {
                "remote_icon_url": cfp.icon_url,
                "remote_summary": (cfp.description or "").strip(),
                "remote_categories": cats,
                "remote_project_url": cfp.project_url,
                "remote_source": "curseforge",
            }

    return _empty_remote()


def safe_http_icon_url(url: Optional[str]) -> Optional[str]:
    if not url or not isinstance(url, str):
        return None
    u = url.strip()
    if u.startswith("https://"):
        return u
    if u.startswith("http://"):
        return u
    return None
