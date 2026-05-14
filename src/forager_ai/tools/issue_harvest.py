"""Resolve Modrinth / CurseForge project URLs to metadata and issue-tracker links."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from .compat_research import fetch_modrinth_project, summarize_project_for_compat

_RE_MR = re.compile(r"modrinth\.com/(?:mod|project)/([^/?#]+)", re.I)
_RE_CF_SLUG = re.compile(r"curseforge\.com/minecraft/mc-mods/([^/?#]+)", re.I)
_RE_CF_NUM = re.compile(r"curseforge\.com/(?:minecraft/)?mc-mods/(\d{3,})", re.I)


def harvest_project_url(
    url: str,
    *,
    mod_downloader: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Return structured hints for a Modrinth or CurseForge project URL.

    ``mod_downloader`` is optional; without it (or without a Curse key), CurseForge slug URLs
    return a note instead of full metadata.
    """
    u = (url or "").strip()
    out: Dict[str, Any] = {"url": u, "source": None, "ok": False}
    if not u:
        out["message"] = "Empty URL."
        return out

    m_mr = _RE_MR.search(u)
    if m_mr:
        slug = m_mr.group(1).strip()
        proj = fetch_modrinth_project(slug)
        if not proj:
            out["message"] = f"Modrinth project not found for `{slug}`."
            return out
        out["source"] = "modrinth"
        out["ok"] = True
        out["project"] = {
            "slug": proj.get("slug"),
            "title": proj.get("title"),
            "project_id": proj.get("id"),
            "issues_url": proj.get("issues_url"),
            "source_url": proj.get("source_url"),
            "wiki_url": proj.get("wiki_url"),
            "discord_url": proj.get("discord_url"),
            "project_url": proj.get("project_url") or f"https://modrinth.com/mod/{proj.get('slug') or slug}",
        }
        out["summary_text"] = summarize_project_for_compat(proj)
        return out

    m_num = _RE_CF_NUM.search(u)
    if m_num and mod_downloader is not None:
        pid = m_num.group(1).strip()
        detail = mod_downloader.get_curseforge_mod_detail(pid)
        if detail:
            issues = str(detail.get("issues_url") or "").strip()
            src = str(detail.get("source_code_url") or "").strip()
            web = str(detail.get("website_url") or "").strip()
            out["source"] = "curseforge"
            out["ok"] = True
            out["project"] = {
                "project_id": pid,
                "title": detail.get("title"),
                "summary": (detail.get("summary") or "")[:400],
                "issues_url": issues or None,
                "source_url": src or web or None,
                "web_url": detail.get("project_url") or f"https://www.curseforge.com/minecraft/mc-mods/{pid}",
            }
            lines = [
                f"CurseForge: {detail.get('title')}",
                f"Project id `{pid}`",
            ]
            if issues:
                lines.append(f"Issues: {issues}")
            if src or web:
                lines.append(f"Source / site: {src or web}")
            out["summary_text"] = "\n".join(lines)
            return out

    m_cf = _RE_CF_SLUG.search(u)
    if m_cf and mod_downloader is not None:
        slug = m_cf.group(1).strip()
        if slug.isdigit():
            return harvest_project_url(f"https://www.curseforge.com/minecraft/mc-mods/{slug}", mod_downloader=mod_downloader)
        rows: List[Any] = []
        try:
            rows = mod_downloader.search_curseforge(slug, limit=8, catalog_kind="mods")
        except Exception as exc:
            out["message"] = f"CurseForge search failed: {exc}"
            return out
        hit = None
        slug_l = slug.lower()
        for r in rows:
            if str(getattr(r, "project_id", "") or "").lower() == slug_l:
                hit = r
                break
        if hit is None and rows:
            # Prefer exact slug match in project_url when CF returns string ids
            for r in rows:
                pu = str(getattr(r, "project_url", "") or "").lower()
                if slug_l in pu:
                    hit = r
                    break
        if hit is None and rows:
            hit = rows[0]
        if not hit:
            out["message"] = "CurseForge search returned no rows (check API key)."
            return out
        pid = str(getattr(hit, "project_id", "") or "").strip()
        if not pid.isdigit():
            out["message"] = f"CurseForge resolved slug `{slug}` to a non-numeric id — open the project page manually."
            return out
        return harvest_project_url(
            f"https://www.curseforge.com/minecraft/mc-mods/{pid}",
            mod_downloader=mod_downloader,
        )

    out["message"] = (
        "Unsupported URL pattern. Use a Modrinth mod URL, or a CurseForge mc-mods URL with a saved Curse API key."
    )
    return out
