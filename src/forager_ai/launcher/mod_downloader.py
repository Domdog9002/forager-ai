"""
Mod Download Manager
Handles downloading mods from Modrinth, CurseForge, and other sources.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
import urllib3
from urllib3.exceptions import InsecureRequestWarning
from urllib3.util.retry import Retry

from .install_provenance import append_install_provenance, build_provenance_record


def _latin_letter_ratio(text: str) -> float:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    latin = sum(1 for c in letters if ("A" <= c <= "Z") or ("a" <= c <= "z"))
    return latin / len(letters)


def prefer_english_catalog_blurb(text: object, *, max_len: int = 520) -> str:
    """Prefer Latin-heavy segments for short catalog blurbs; drop mostly CJK/non-Latin copy.

    Modrinth/CurseForge often return author-written Chinese; we keep English clauses when present
    (e.g. after em dashes) so the Browse catalog stays readable without a translation service.
    """
    raw = str(text or "").strip().replace("\r", " ").replace("\n", " ")
    if not raw:
        return ""
    raw_clean = " ".join(raw.split())
    best = ""
    best_r = 0.0
    for part in re.split(r"[\u2014\u2013——|]+", raw_clean):
        p = part.strip()
        if not p:
            continue
        r = _latin_letter_ratio(p)
        if r > best_r:
            best_r, best = r, p
    if best_r >= 0.42:
        return best[:max_len]
    if _latin_letter_ratio(raw_clean) >= 0.28:
        return raw_clean[:max_len]
    return ""


@dataclass
class ModInfo:
    """Information about a mod."""
    id: str
    name: str
    description: str
    author: str
    source: str  # modrinth, curseforge, github, direct
    project_id: str
    version_id: Optional[str] = None
    minecraft_versions: List[str] = None
    loaders: List[str] = None  # forge, fabric, quilt
    categories: List[str] = None
    download_url: Optional[str] = None
    file_name: Optional[str] = None
    file_size: Optional[int] = None
    sha1_hash: Optional[str] = None
    dependencies: List[str] = None
    icon_url: Optional[str] = None
    project_url: Optional[str] = None
    download_total: Optional[int] = None
    updated_at: Optional[str] = None
    catalog_kind: Optional[str] = None  # mods, resourcepack, shader, datapack, modpack

    def __post_init__(self):
        if self.minecraft_versions is None:
            self.minecraft_versions = []
        if self.loaders is None:
            self.loaders = []
        if self.categories is None:
            self.categories = []
        if self.dependencies is None:
            self.dependencies = []


def _interleave_mr_cf_rows(mr: List[ModInfo], cf: List[ModInfo], *, limit: int) -> List[ModInfo]:
    """Interleave Modrinth + CurseForge rows, then append any remainder from the longer list.

    The previous index-only interleaving stopped at ``max(len(mr), len(cf))`` *positions*, which drops
    Modrinth tail rows whenever CurseForge returns fewer hits (including zero) — a common ``100 of 200`` bug.
    """
    cap = max(1, int(limit))
    if not mr and not cf:
        return []
    if not mr:
        return cf[:cap]
    if not cf:
        return mr[:cap]
    out: List[ModInfo] = []
    i = 0
    while i < len(mr) and i < len(cf) and len(out) < cap:
        out.append(mr[i])
        if len(out) >= cap:
            return out
        out.append(cf[i])
        i += 1
    if len(out) < cap:
        out.extend(mr[i:][: cap - len(out)])
    if len(out) < cap:
        out.extend(cf[i:][: cap - len(out)])
    return out


class ModDownloader:
    """Downloads and manages mods from various sources."""

    # Catalog search paging (parity with MR/CF site listings).
    CURSEFORGE_SEARCH_PAGE_MAX = 50
    MODRINTH_SEARCH_PAGE_MAX = 100

    MINECRAFT_GAME_ID = 432
    CURSEFORGE_MODS_CLASS_ID = 6
    # Fallback CurseForge class IDs for Minecraft Java (refined via /categories when a key is set).
    CURSEFORGE_KIND_CLASS_DEFAULTS: Dict[str, int] = {
        "mods": 6,
        "resourcepack": 12,
        "shader": 6,
        "datapack": 6,
        "modpack": 4471,
    }
    MODRINTH_PROJECT_TYPE_BY_KIND: Dict[str, str] = {
        "mods": "mod",
        "resourcepack": "resourcepack",
        "shader": "shader",
        "datapack": "datapack",
        "modpack": "modpack",
    }

    def __init__(self, cache_dir: str, user_agent: str = "ForagerAI/1.0"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        self.user_agent = user_agent
        self.session = self._create_session()
        
        # API endpoints
        self.modrinth_api = "https://api.modrinth.com/v2"
        self.curseforge_api = "https://api.curseforge.com/v1"
        self._curseforge_key_override = ""
        self._cf_kind_class_cache: Optional[Dict[str, int]] = None

        # Rate limiting
        self.last_request_time = 0
        self.min_request_interval = 0.1  # 100ms between requests

    def set_curseforge_api_key(self, key: Optional[str]) -> None:
        """Saved launcher key; when empty, ``CURSEFORGE_API_KEY`` env is still used."""
        self._curseforge_key_override = (key or "").strip()
        self._cf_kind_class_cache = None

    def get_curseforge_kind_class_map(self) -> Dict[str, int]:
        """Map dashboard ``catalog_kind`` -> CurseForge ``classId`` (mods section ids)."""
        if self._cf_kind_class_cache is not None:
            return self._cf_kind_class_cache
        base = dict(self.CURSEFORGE_KIND_CLASS_DEFAULTS)
        data: Optional[Any] = None
        for params in (
            {"gameId": self.MINECRAFT_GAME_ID, "classesOnly": True},
            {"gameId": self.MINECRAFT_GAME_ID},
        ):
            data = self._curseforge_get("/categories", params)
            if isinstance(data, dict) and data.get("data"):
                break
        if isinstance(data, dict):
            for c in data.get("data") or []:
                if not isinstance(c, dict) or not c.get("isClass"):
                    continue
                cid = c.get("id")
                if cid is None:
                    continue
                try:
                    cid_int = int(cid)
                except (TypeError, ValueError):
                    continue
                name = (c.get("name") or "").lower()
                slug = (c.get("slug") or "").lower()
                if "modpack" in name or "mod pack" in name or "modpack" in slug:
                    base["modpack"] = cid_int
                if "texture" in name and "pack" in name:
                    base["resourcepack"] = cid_int
                if "data pack" in name or "datapack" in name or "data-pack" in slug:
                    base["datapack"] = cid_int
                if "shader" in name or "iris" in name:
                    base["shader"] = cid_int
                if name.strip() == "mods" or slug == "mc-mods":
                    base["mods"] = cid_int
        self._cf_kind_class_cache = base
        return base

    @staticmethod
    def _curseforge_web_segment_for_class(class_id: int) -> str:
        seg = {
            6: "mc-mods",
            12: "texture-packs",
            4471: "modpacks",
            17: "worlds",
        }.get(class_id)
        return seg or "mc-mods"

    def _curseforge_browse_url_for_slug(self, class_id: int, slug: str) -> Optional[str]:
        if not slug or not str(slug).strip():
            return None
        seg = self._curseforge_web_segment_for_class(class_id)
        return f"https://www.curseforge.com/minecraft/{seg}/{str(slug).strip()}"

    def curseforge_configured(self) -> bool:
        return bool(self._curseforge_key())

    def _curseforge_key(self) -> str:
        return self._curseforge_key_override or (os.environ.get("CURSEFORGE_API_KEY") or "").strip()

    def _curseforge_headers(self) -> Dict[str, str]:
        k = self._curseforge_key()
        if not k:
            return {}
        return {"x-api-key": k}

    @staticmethod
    def _map_loader_to_curseforge(loader: Optional[str]) -> Optional[int]:
        if not loader:
            return None
        low = loader.strip().lower()
        if low in ("forge", "neoforge"):
            return 6 if low == "neoforge" else 1
        if low == "fabric":
            return 4
        if low == "quilt":
            return 5
        return None

    def _curseforge_get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
        key = self._curseforge_key()
        if not key:
            return None
        self._rate_limit()
        url = path if path.startswith("http") else f"{self.curseforge_api}{path}"
        try:
            response = self._get(
                url,
                params=params,
                headers={**self.session.headers, **self._curseforge_headers()},
                timeout=60,
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            print(f"CurseForge API error ({path}): {e}")
            return None

    def _modinfo_from_curseforge_search_row(
        self,
        m: Dict[str, Any],
        cid: int,
        catalog_kind: str,
    ) -> Optional[ModInfo]:
        """Parse one CurseForge ``/mods/search`` row."""
        try:
            mid = m.get("id")
            if mid is None:
                return None
            authors = m.get("authors") or []
            author_name = ", ".join(
                str(a.get("name") or "").strip() for a in authors if isinstance(a, dict)
            ).strip() or "Unknown"

            logo = m.get("logo") or {}
            icon_url = None
            if isinstance(logo, dict):
                icon_url = logo.get("url") or logo.get("thumbnailUrl")

            cats = m.get("categories") or []
            cat_names = [
                str(c.get("name") or "").strip()
                for c in cats
                if isinstance(c, dict) and c.get("name")
            ]

            game_vers: set[str] = set()
            loader_vers: set[str] = set()
            for lf in m.get("latestFiles") or []:
                if isinstance(lf, dict):
                    for gv in lf.get("gameVersions") or []:
                        if gv:
                            game_vers.add(str(gv))
                    for ld in lf.get("modLoaders") or []:
                        if ld:
                            loader_vers.add(str(ld).strip().lower())

            slug = str(m.get("slug") or "")
            api_class = m.get("classId")
            try:
                url_class = int(api_class) if api_class is not None else cid
            except (TypeError, ValueError):
                url_class = cid
            project_url = self._curseforge_browse_url_for_slug(url_class, slug)

            return ModInfo(
                id=str(mid),
                name=str(m.get("name") or "Unknown"),
                description=prefer_english_catalog_blurb(m.get("summary") or ""),
                author=author_name,
                source="curseforge",
                project_id=str(mid),
                minecraft_versions=sorted(game_vers),
                loaders=sorted(loader_vers),
                categories=cat_names,
                icon_url=icon_url,
                project_url=project_url,
                download_total=m.get("downloadCount"),
                updated_at=m.get("dateModified") or m.get("dateReleased"),
                catalog_kind=catalog_kind,
            )
        except (TypeError, KeyError, ValueError) as e:
            print(f"Error parsing CurseForge mod: {e}")
            return None

    def _curseforge_download_url(self, mod_id: int, file_id: int) -> Optional[str]:
        data = self._curseforge_get(f"/mods/{mod_id}/files/{file_id}/download-url")
        if not data:
            return None
        url = data.get("data")
        return url if isinstance(url, str) and url else None

    def search_curseforge(
        self,
        query: str,
        minecraft_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        sort_field: int = 6,
        sort_order: str = "desc",
        index: int = 0,
        class_id: Optional[int] = None,
        catalog_kind: str = "mods",
    ) -> List[ModInfo]:
        """Search CurseForge for a Minecraft Java class (mods, texture packs, modpacks, …). Requires API key.

        Omit or blank ``query`` to list projects (sorted by ``sort_field``) with optional version/loader filters.
        ``index`` is the zero-based pagination offset (API ``index`` query param).
        """
        if not self._curseforge_key():
            return []

        cid = int(class_id) if class_id is not None else self.CURSEFORGE_MODS_CLASS_ID

        base_common: Dict[str, Any] = {
            "gameId": self.MINECRAFT_GAME_ID,
            "classId": cid,
            "sortField": sort_field,
            "sortOrder": sort_order if sort_order in ("asc", "desc") else "desc",
        }
        q = (query or "").strip()
        if q:
            base_common["searchFilter"] = q
        if minecraft_version:
            # CurseForge ``/mods/search`` with ``classId`` modpacks (4471) + ``gameVersion`` often returns
            # far fewer rows than Modrinth for the same MC filter — merged Browse Modpacks then looks
            # "Modrinth only". Omit server-side gameVersion for modpack discovery; use toolbar MC +
            # **Filters → Loaded rows → MC tags** for client-side narrowing instead.
            if (catalog_kind or "mods").strip().lower() != "modpack":
                base_common["gameVersion"] = minecraft_version
        ml = self._map_loader_to_curseforge(loader)
        if ml is not None and minecraft_version and cid == self.CURSEFORGE_MODS_CLASS_ID:
            base_common["modLoaderType"] = ml

        mods: List[ModInfo] = []
        cur_index = max(0, index)
        need = max(1, limit)
        while len(mods) < need:
            chunk = min(self.CURSEFORGE_SEARCH_PAGE_MAX, need - len(mods))
            params = {
                **base_common,
                "pageSize": chunk,
                "index": cur_index,
            }
            payload = self._curseforge_get("/mods/search", params=params)
            if not payload:
                break
            raw = [row for row in (payload.get("data") or []) if isinstance(row, dict)]
            if not raw:
                break
            for m in raw:
                mi = self._modinfo_from_curseforge_search_row(m, cid, catalog_kind)
                if mi:
                    mods.append(mi)
            cur_index += len(raw)
            if len(raw) < chunk:
                break

        return mods[:need]

    def _curseforge_collect_file_rows(
        self,
        mod_id: int,
        base_params: Dict[str, Any],
        *,
        max_pages: int = 5,
    ) -> List[Dict[str, Any]]:
        """Merge paginated ``/mods/{id}/files`` responses (CF often returns empty when filters are too strict)."""
        out: List[Dict[str, Any]] = []
        ps = min(max(1, int(base_params.get("pageSize") or 50)), 50)
        for pnum in range(max_pages):
            params = {**base_params, "pageSize": ps, "index": pnum * ps}
            payload = self._curseforge_get(f"/mods/{mod_id}/files", params=params)
            if not payload:
                break
            chunk = [f for f in (payload.get("data") or []) if isinstance(f, dict)]
            if not chunk:
                break
            out.extend(chunk)
            if len(chunk) < ps:
                break
        return out

    @staticmethod
    def _pick_curseforge_file_row(
        files: List[Dict[str, Any]],
        prefer_minecraft_version: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        if not files:
            return None
        pool = files
        pref = (prefer_minecraft_version or "").strip()
        if pref:
            matched = [
                f
                for f in pool
                if isinstance(f.get("gameVersions"), list)
                and pref in [str(x) for x in (f.get("gameVersions") or [])]
            ]
            if matched:
                pool = matched
        rel = [f for f in pool if f.get("releaseType") == 1]
        use = rel if rel else pool

        def _fd(x: Dict[str, Any]) -> str:
            return str(x.get("fileDate") or "")

        return max(use, key=_fd)

    def get_curseforge_install_candidate(
        self,
        project_id: str,
        minecraft_version: Optional[str],
        loader: str,
        use_loader: bool = True,
        catalog_kind: str = "mods",
    ) -> Optional[ModInfo]:
        """Pick a release file for the given game version and loader; resolve download URL.

        Tries strict filters first, then game version only, then paginates unfiltered files and prefers
        rows that list the requested Minecraft version in ``gameVersions`` — CurseForge often returns
        no rows when ``modLoaderType`` does not match project metadata exactly.
        """
        if not self._curseforge_key() or not project_id:
            return None
        try:
            mod_id = int(project_id)
        except ValueError:
            return None

        mc = (minecraft_version or "").strip() or None
        files: List[Dict[str, Any]] = []

        if mc and use_loader:
            ml = self._map_loader_to_curseforge(loader)
            if ml is not None:
                files = self._curseforge_collect_file_rows(
                    mod_id,
                    {"gameVersion": mc, "modLoaderType": ml, "pageSize": 50},
                )
        if not files and mc:
            files = self._curseforge_collect_file_rows(
                mod_id,
                {"gameVersion": mc, "pageSize": 50},
            )
        if not files:
            files = self._curseforge_collect_file_rows(mod_id, {"pageSize": 50})

        chosen = self._pick_curseforge_file_row(files, mc)
        if not chosen:
            return None
        fname = chosen.get("fileName")
        if not fname:
            return None

        url = chosen.get("downloadUrl")
        if not url:
            fid = chosen.get("id")
            if fid is not None:
                url = self._curseforge_download_url(mod_id, int(fid))

        if not url:
            return None

        sha1 = None
        for h in chosen.get("hashes") or []:
            if isinstance(h, dict) and h.get("algo") == 1 and h.get("value"):
                sha1 = str(h["value"])
                break

        meta = self._curseforge_get_mod_brief(mod_id)
        name = meta.get("name", "Mod") if meta else "Mod"
        summary = prefer_english_catalog_blurb((meta.get("summary", "") if meta else "") or "")
        authors = meta.get("author", "Unknown") if meta else "Unknown"
        icon_url = meta.get("icon_url")
        project_url = meta.get("project_url")
        slug_ref = meta.get("slug", "")

        return ModInfo(
            id=str(chosen.get("id", project_id)),
            name=name,
            description=summary,
            author=authors,
            source="curseforge",
            project_id=str(mod_id),
            version_id=str(chosen.get("id")) if chosen.get("id") is not None else None,
            minecraft_versions=list(chosen.get("gameVersions") or []),
            loaders=[loader] if loader else [],
            download_url=url,
            file_name=str(fname),
            file_size=chosen.get("fileLength"),
            sha1_hash=sha1,
            icon_url=icon_url,
            project_url=project_url or (
                self._curseforge_browse_url_for_slug(
                    int((meta or {}).get("class_id") or self.CURSEFORGE_MODS_CLASS_ID),
                    slug_ref,
                )
                if meta
                else self._curseforge_browse_url_for_slug(self.CURSEFORGE_MODS_CLASS_ID, slug_ref)
            ),
            catalog_kind=catalog_kind,
        )

    def _curseforge_get_mod_brief(self, mod_id: int) -> Optional[Dict[str, Any]]:
        payload = self._curseforge_get(f"/mods/{mod_id}")
        if not payload:
            return None
        m = payload.get("data")
        if not isinstance(m, dict):
            return None
        authors = m.get("authors") or []
        author_name = ", ".join(
            str(a.get("name") or "").strip() for a in authors if isinstance(a, dict)
        ).strip() or "Unknown"
        logo = m.get("logo") or {}
        icon_url = None
        if isinstance(logo, dict):
            icon_url = logo.get("url") or logo.get("thumbnailUrl")
        slug = str(m.get("slug") or "")
        raw_cid = m.get("classId")
        try:
            cid_int = int(raw_cid) if raw_cid is not None else self.CURSEFORGE_MODS_CLASS_ID
        except (TypeError, ValueError):
            cid_int = self.CURSEFORGE_MODS_CLASS_ID
        return {
            "name": str(m.get("name") or "Mod"),
            "summary": str(m.get("summary") or ""),
            "author": author_name,
            "icon_url": icon_url,
            "slug": slug,
            "class_id": cid_int,
            "project_url": self._curseforge_browse_url_for_slug(cid_int, slug),
        }

    def get_modrinth_project_detail(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Rich Modrinth project metadata for an in-app project page (body, gallery, links)."""
        if not project_id or not str(project_id).strip():
            return None
        self._rate_limit()
        try:
            response = self._get(f"{self.modrinth_api}/project/{project_id.strip()}")
            response.raise_for_status()
            p = response.json()
        except requests.RequestException as e:
            print(f"Modrinth project detail: {e}")
            return None
        if not isinstance(p, dict):
            return None
        gal: List[str] = []
        for item in p.get("gallery") or []:
            if not isinstance(item, dict):
                continue
            u = item.get("url") or item.get("raw_url")
            if not u or not isinstance(u, str):
                continue
            u = u.strip()
            if u.startswith("https://") or u.startswith("http://"):
                gal.append(u)
            elif u.startswith("//"):
                gal.append("https:" + u)
            elif u.startswith("/"):
                gal.append("https://cdn.modrinth.com" + u)
        slug = str(p.get("slug") or "")
        body = (p.get("body") or "").strip()
        desc = (p.get("description") or "").strip()
        return {
            "title": str(p.get("title") or ""),
            "slug": slug,
            "description": desc,
            "body_markdown": body,
            "icon_url": self._normalize_modrinth_icon(p.get("icon_url")),
            "project_url": f"https://modrinth.com/mod/{slug}" if slug else None,
            "gallery_urls": gal,
            "issues_url": p.get("issues_url"),
            "source_url": p.get("source_url"),
            "wiki_url": p.get("wiki_url"),
            "discord_url": p.get("discord_url"),
            "downloads": p.get("downloads"),
            "follows": p.get("follows"),
            "categories": [str(c) for c in (p.get("categories") or []) if c],
            "loaders": [str(x) for x in (p.get("loaders") or []) if x],
            "game_versions": [str(x) for x in (p.get("game_versions") or []) if x][:48],
        }

    def get_curseforge_mod_detail(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Rich CurseForge mod metadata (HTML description, screenshots, links). Requires API key."""
        try:
            mid = int(project_id)
        except (TypeError, ValueError):
            return None
        payload = self._curseforge_get(f"/mods/{mid}")
        if not payload:
            return None
        m = payload.get("data")
        if not isinstance(m, dict):
            return None
        authors = m.get("authors") or []
        author_name = ", ".join(
            str(a.get("name") or "").strip() for a in authors if isinstance(a, dict)
        ).strip() or "Unknown"
        logo = m.get("logo") or {}
        icon_url = None
        if isinstance(logo, dict):
            icon_url = logo.get("url") or logo.get("thumbnailUrl")
        links = m.get("links") if isinstance(m.get("links"), dict) else {}
        screenshots: List[str] = []
        for s in m.get("screenshots") or []:
            if isinstance(s, dict) and s.get("url"):
                screenshots.append(str(s["url"]))
        slug = str(m.get("slug") or "")
        cats = m.get("categories") or []
        cat_names = [
            str(c.get("name") or "").strip()
            for c in cats
            if isinstance(c, dict) and c.get("name")
        ]
        raw_cid = m.get("classId")
        try:
            cid_int = int(raw_cid) if raw_cid is not None else self.CURSEFORGE_MODS_CLASS_ID
        except (TypeError, ValueError):
            cid_int = self.CURSEFORGE_MODS_CLASS_ID
        return {
            "title": str(m.get("name") or ""),
            "summary": str(m.get("summary") or ""),
            "description_html": str(m.get("description") or ""),
            "author": author_name,
            "icon_url": icon_url,
            "project_url": self._curseforge_browse_url_for_slug(cid_int, slug),
            "gallery_urls": screenshots,
            "website_url": links.get("websiteUrl") if isinstance(links, dict) else None,
            "wiki_url": links.get("wikiUrl") if isinstance(links, dict) else None,
            "issues_url": links.get("issuesUrl") if isinstance(links, dict) else None,
            "source_code_url": links.get("sourceUrl") if isinstance(links, dict) else None,
            "download_count": m.get("downloadCount"),
            "date_modified": m.get("dateModified"),
            "categories": cat_names,
        }

    def list_curseforge_mod_files(
        self,
        project_id: str,
        minecraft_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 40,
        use_loader: bool = True,
    ) -> List[Dict[str, Any]]:
        """Recent mod JAR files from CurseForge for version picking (newest first)."""
        if not self._curseforge_key():
            return []
        try:
            mod_id = int(project_id)
        except (TypeError, ValueError):
            return []
        params: Dict[str, Any] = {"pageSize": min(max(1, limit), 50)}
        if minecraft_version:
            params["gameVersion"] = minecraft_version
        if use_loader:
            ml = self._map_loader_to_curseforge(loader)
            if ml is not None and minecraft_version:
                params["modLoaderType"] = ml
        payload = self._curseforge_get(f"/mods/{mod_id}/files", params=params)
        if not payload:
            return []
        files = [f for f in (payload.get("data") or []) if isinstance(f, dict)]

        def _fd(x: Dict[str, Any]) -> str:
            return str(x.get("fileDate") or "")

        files.sort(key=_fd, reverse=True)
        return files[:limit]

    def curseforge_file_to_modinfo(self, project_id: str, file_rec: Dict[str, Any], catalog_kind: str = "mods") -> Optional[ModInfo]:
        """Build ModInfo from a CurseForge ``/files`` record for download."""
        try:
            mod_id = int(project_id)
        except (TypeError, ValueError):
            return None
        fname = file_rec.get("fileName")
        if not fname:
            return None
        url = file_rec.get("downloadUrl")
        fid = file_rec.get("id")
        if not url and fid is not None:
            url = self._curseforge_download_url(mod_id, int(fid))
        if not url:
            return None
        sha1 = None
        for h in file_rec.get("hashes") or []:
            if isinstance(h, dict) and h.get("algo") == 1 and h.get("value"):
                sha1 = str(h["value"])
                break
        brief = self._curseforge_get_mod_brief(mod_id) or {}
        slug = str(brief.get("slug") or "")
        return ModInfo(
            id=str(fid) if fid is not None else str(mod_id),
            name=str(brief.get("name") or "Mod"),
            description=prefer_english_catalog_blurb(brief.get("summary") or ""),
            author=str(brief.get("author") or "Unknown"),
            source="curseforge",
            project_id=str(mod_id),
            version_id=str(fid) if fid is not None else None,
            minecraft_versions=list(file_rec.get("gameVersions") or []),
            loaders=[],
            download_url=url,
            file_name=str(fname),
            file_size=file_rec.get("fileLength"),
            sha1_hash=sha1,
            icon_url=brief.get("icon_url"),
            project_url=brief.get("project_url")
            or self._curseforge_browse_url_for_slug(int(brief.get("class_id") or 6), slug),
            catalog_kind=catalog_kind,
        )

    def _normalize_modrinth_icon(self, url: Any) -> Optional[str]:
        if not url or not isinstance(url, str):
            return None
        u = url.strip()
        if u.startswith("https://"):
            return u
        if u.startswith("http://"):
            return u
        if u.startswith("//"):
            return "https:" + u
        if u.startswith("/"):
            return "https://cdn.modrinth.com" + u
        return u

    def _create_session(self) -> requests.Session:
        """Create a requests session with retry strategy."""
        session = requests.Session()
        
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        adapter = HTTPAdapter(max_retries=retry_strategy)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        
        session.headers.update({
            "User-Agent": self.user_agent,
            "Accept": "application/json",
            "Accept-Language": "en, en-US;q=0.9",
        })
        
        return session

    def _get(self, url: str, **kwargs: Any) -> requests.Response:
        """GET with verify=False retry when the OS trust store is broken (common on Windows)."""
        strict_tls = os.environ.get("FORAGER_STRICT_TLS", "").strip().lower()
        if strict_tls in {"1", "true", "yes", "on"}:
            return self.session.get(url, **kwargs)
        try:
            return self.session.get(url, **kwargs)
        except requests.RequestException:
            urllib3.disable_warnings(InsecureRequestWarning)
            retry_kwargs = dict(kwargs)
            retry_kwargs["verify"] = False
            return self.session.get(url, **retry_kwargs)
    
    def _rate_limit(self):
        """Enforce rate limiting between requests."""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_interval:
            time.sleep(self.min_request_interval - time_since_last)
        
        self.last_request_time = time.time()

    def _modinfo_from_modrinth_search_hit(self, hit: Dict[str, Any], catalog_kind: str) -> Optional[ModInfo]:
        try:
            slug = hit.get("slug") or ""
            raw_cats = [str(c).strip() for c in (hit.get("categories") or []) if str(c).strip()]
            known_loaders = {"forge", "fabric", "quilt", "neoforge"}
            loaders = sorted({c.lower() for c in raw_cats if c.lower() in known_loaders})
            categories = [c for c in raw_cats if c.lower() not in known_loaders]
            return ModInfo(
                id=hit["project_id"],
                name=hit["title"],
                description=prefer_english_catalog_blurb(hit.get("description") or ""),
                author=hit.get("author") or "",
                source="modrinth",
                project_id=hit["project_id"],
                minecraft_versions=hit.get("versions", []) or [],
                loaders=loaders,
                categories=categories or raw_cats,
                icon_url=self._normalize_modrinth_icon(hit.get("icon_url")),
                project_url=f"https://modrinth.com/mod/{slug}" if slug else None,
                download_total=hit.get("downloads"),
                updated_at=hit.get("date_modified"),
                catalog_kind=catalog_kind,
            )
        except (KeyError, TypeError, ValueError) as e:
            print(f"Error parsing Modrinth search hit: {e}")
            return None

    def search_modrinth(
        self,
        query: str,
        minecraft_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        index: str = "relevance",
        project_type: str = "mod",
        catalog_kind: str = "mods",
    ) -> List[ModInfo]:
        """Search Modrinth. Leave ``query`` blank to browse (sort with ``index``, e.g. ``downloads``).

        Pages automatically when ``limit`` exceeds Modrinth's per-request maximum (mirrors heavier site grids).
        """
        pt = (project_type or "mod").strip().lower()
        facet_parts: List[str] = [f'["project_type:{pt}"]']
        if minecraft_version:
            facet_parts.append(f'["versions:{minecraft_version}"]')
        if loader and pt in ("mod", "modpack"):
            facet_parts.append(f'["categories:{loader}"]')
        allowed_index = {"relevance", "downloads", "newest", "updated", "follows"}
        idx = index if index in allowed_index else "relevance"
        qtxt = (query or "").strip()
        facets = "[" + ",".join(facet_parts) + "]"

        mods: List[ModInfo] = []
        cur_off = max(0, offset)
        need = max(1, limit)
        try:
            while len(mods) < need:
                chunk = min(self.MODRINTH_SEARCH_PAGE_MAX, need - len(mods))
                params: Dict[str, Any] = {
                    "limit": chunk,
                    "offset": cur_off,
                    "facets": facets,
                    "index": idx,
                }
                if qtxt:
                    params["query"] = qtxt
                self._rate_limit()
                response = self._get(f"{self.modrinth_api}/search", params=params)
                response.raise_for_status()
                data = response.json()
                hits = [h for h in (data.get("hits") or []) if isinstance(h, dict)]
                if not hits:
                    break
                for hit in hits:
                    mi = self._modinfo_from_modrinth_search_hit(hit, catalog_kind)
                    if mi:
                        mods.append(mi)
                cur_off += len(hits)
                if len(hits) < chunk:
                    break

            return mods[:need]

        except requests.RequestException as e:
            print(f"Error searching Modrinth: {e}")
            return []
    
    def get_modrinth_versions(
        self,
        project_id: str,
        minecraft_version: Optional[str] = None,
        loader: Optional[str] = None,
        filter_loader: bool = True,
        catalog_kind: str = "mods",
    ) -> List[ModInfo]:
        """Get available versions for a Modrinth project."""
        self._rate_limit()
        
        params: Dict[str, str] = {}
        if minecraft_version:
            params["game_versions"] = f'["{minecraft_version}"]'
        if loader and filter_loader:
            params["loaders"] = f'["{loader}"]'
        
        try:
            response = self._get(
                f"{self.modrinth_api}/project/{project_id}/version",
                params=params
            )
            response.raise_for_status()
            versions = response.json()
            
            # Get project info
            project_response = self._get(f"{self.modrinth_api}/project/{project_id}")
            project_response.raise_for_status()
            project_data = project_response.json()
            
            mod_versions = []
            for version in versions:
                if not isinstance(version, dict):
                    continue
                raw_files = version.get("files") or []
                files_list = [f for f in raw_files if isinstance(f, dict) and f.get("url") and f.get("filename")]
                if not files_list:
                    continue
                primary_file = next((f for f in files_list if f.get("primary")), None)
                picked = primary_file if primary_file else files_list[0]
                icon_raw = project_data.get("icon_url")
                slug = str(project_data.get("slug") or "")
                mod = ModInfo(
                    id=version["id"],
                    name=project_data["title"],
                    description=prefer_english_catalog_blurb(project_data.get("description") or ""),
                    author=str(project_data.get("author") or project_data.get("team") or "—"),
                    source="modrinth",
                    project_id=project_id,
                    version_id=version["id"],
                    minecraft_versions=version.get("game_versions", []),
                    loaders=version.get("loaders", []),
                    download_url=picked["url"],
                    file_name=picked["filename"],
                    file_size=picked.get("size"),
                    sha1_hash=(picked.get("hashes") or {}).get("sha1") if isinstance(picked.get("hashes"), dict) else None,
                    dependencies=[dep["project_id"] for dep in version.get("dependencies", []) if isinstance(dep, dict) and dep.get("project_id")],
                    icon_url=self._normalize_modrinth_icon(icon_raw),
                    project_url=f"https://modrinth.com/mod/{slug}" if slug else None,
                    catalog_kind=catalog_kind,
                )
                mod_versions.append(mod)
            
            return mod_versions
            
        except requests.RequestException as e:
            print(f"Error getting Modrinth versions: {e}")
            return []

    def get_modrinth_version_by_id(self, version_id: str, *, catalog_kind: str = "mods") -> Optional[ModInfo]:
        """Fetch a single Modrinth version by UUID (for replay downloads from provenance)."""
        vid = (version_id or "").strip()
        if not vid:
            return None
        self._rate_limit()
        try:
            response = self._get(f"{self.modrinth_api}/version/{vid}")
            response.raise_for_status()
            version = response.json()
        except requests.RequestException:
            return None
        if not isinstance(version, dict):
            return None
        project_id = str(version.get("project_id") or "").strip()
        if not project_id:
            return None
        try:
            project_response = self._get(f"{self.modrinth_api}/project/{project_id}")
            project_response.raise_for_status()
            project_data = project_response.json()
        except requests.RequestException:
            return None
        if not isinstance(project_data, dict):
            return None
        raw_files = version.get("files") or []
        files_list = [f for f in raw_files if isinstance(f, dict) and f.get("url") and f.get("filename")]
        if not files_list:
            return None
        primary_file = next((f for f in files_list if f.get("primary")), None)
        picked = primary_file if primary_file else files_list[0]
        icon_raw = project_data.get("icon_url")
        slug = str(project_data.get("slug") or "")
        return ModInfo(
            id=str(version.get("id") or vid),
            name=str(project_data.get("title") or slug or project_id),
            description=prefer_english_catalog_blurb(project_data.get("description") or ""),
            author=str(project_data.get("author") or project_data.get("team") or "—"),
            source="modrinth",
            project_id=project_id,
            version_id=str(version.get("id") or vid),
            minecraft_versions=list(version.get("game_versions") or []) if isinstance(version.get("game_versions"), list) else [],
            loaders=list(version.get("loaders") or []) if isinstance(version.get("loaders"), list) else [],
            download_url=picked["url"],
            file_name=picked["filename"],
            file_size=picked.get("size"),
            sha1_hash=(picked.get("hashes") or {}).get("sha1") if isinstance(picked.get("hashes"), dict) else None,
            dependencies=[
                dep["project_id"]
                for dep in (version.get("dependencies") or [])
                if isinstance(dep, dict) and dep.get("project_id")
            ],
            icon_url=self._normalize_modrinth_icon(icon_raw),
            project_url=f"https://modrinth.com/mod/{slug}" if slug else None,
            catalog_kind=catalog_kind,
        )

    def download_mod(
        self,
        mod_info: ModInfo,
        destination_dir: str,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> Optional[str]:
        """Download a mod file."""
        if not mod_info.download_url:
            return None
        
        destination_path = Path(destination_dir) / mod_info.file_name
        destination_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Check if file already exists and matches hash
        if destination_path.exists() and mod_info.sha1_hash:
            if self._verify_file_hash(destination_path, mod_info.sha1_hash):
                dest_s = str(destination_path)
                try:
                    rec = build_provenance_record(mod_info, dest_s, note="reuse_verified_sha1")
                    append_install_provenance(self.cache_dir, rec)
                except OSError:
                    pass
                return dest_s
        
        try:
            self._rate_limit()
            
            response = self._get(mod_info.download_url, stream=True)
            response.raise_for_status()
            
            total_size = int(response.headers.get('content-length', 0))
            downloaded = 0
            
            with open(destination_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        
                        if progress_callback:
                            progress_callback(downloaded, total_size)
            
            # Verify hash if provided
            if mod_info.sha1_hash:
                if not self._verify_file_hash(destination_path, mod_info.sha1_hash):
                    destination_path.unlink()  # Delete corrupted file
                    return None
            
            dest_s = str(destination_path)
            try:
                rec = build_provenance_record(mod_info, dest_s, note="")
                append_install_provenance(self.cache_dir, rec)
            except OSError:
                pass
            return dest_s
            
        except requests.RequestException as e:
            print(f"Error downloading mod: {e}")
            if destination_path.exists():
                destination_path.unlink()
            return None
    
    def _verify_file_hash(self, file_path: Path, expected_sha1: str) -> bool:
        """Verify file SHA1 hash."""
        try:
            sha1_hash = hashlib.sha1()
            with open(file_path, 'rb') as f:
                for chunk in iter(lambda: f.read(4096), b""):
                    sha1_hash.update(chunk)
            
            return sha1_hash.hexdigest().lower() == expected_sha1.lower()
        except (OSError, IOError):
            return False
    
    def get_mod_dependencies(self, mod_info: ModInfo) -> List[ModInfo]:
        """Get dependencies for a mod."""
        if not mod_info.dependencies:
            return []
        if mod_info.catalog_kind and mod_info.catalog_kind != "mods":
            return []
        if mod_info.source == "curseforge":
            return []
        if mod_info.source != "modrinth":
            return []

        dependencies = []
        for dep_id in mod_info.dependencies:
            try:
                # Get the latest version of the dependency
                dep_versions = self.get_modrinth_versions(
                    dep_id,
                    minecraft_version=mod_info.minecraft_versions[0] if mod_info.minecraft_versions else None,
                    loader=mod_info.loaders[0] if mod_info.loaders else None
                )
                
                if dep_versions:
                    dependencies.append(dep_versions[0])  # Use latest version
                    
            except Exception as e:
                print(f"Error getting dependency {dep_id}: {e}")
        
        return dependencies
    
    def batch_download(
        self,
        mods: List[ModInfo],
        destination_dir: str,
        progress_callback: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, Optional[str]]:
        """Download multiple mods."""
        results = {}
        
        for i, mod in enumerate(mods):
            if progress_callback:
                progress_callback(i, len(mods), mod.name)
            
            result = self.download_mod(mod, destination_dir)
            results[mod.id] = result
            
            # Small delay between downloads
            time.sleep(0.5)
        
        return results
    
    def search_all_sources(
        self,
        query: str,
        minecraft_version: Optional[str] = None,
        loader: Optional[str] = None,
        limit: int = 20,
        sources: Optional[List[str]] = None,
        curseforge_sort_field: int = 6,
        page: int = 1,
        modrinth_index: str = "relevance",
        catalog_kind: str = "mods",
    ) -> List[ModInfo]:
        """Search Modrinth and/or CurseForge.

        ``sources`` entries should be "modrinth" and/or "curseforge".
        CurseForge is skipped when no API key is configured.
        ``page`` is 1-based; each page skips ``(page-1) * per_source_chunk`` hits per source.
        ``catalog_kind``: mods | resourcepack | shader | datapack | modpack
        """
        want = [
            s.strip().lower()
            for s in (sources or ["modrinth", "curseforge"])
            if s and s.strip().lower() in ("modrinth", "curseforge")
        ]
        if not want:
            want = ["modrinth", "curseforge"]

        # Quota + merge mode must follow sources we *actually* query. If the UI lists CurseForge but
        # no API key is configured, treating it as a second source halves per_src and round-robin merge
        # against an empty CF list yields only half the requested rows (e.g. 100 instead of 200).
        effective: List[str] = []
        if "modrinth" in want:
            effective.append("modrinth")
        if "curseforge" in want and self._curseforge_key():
            effective.append("curseforge")
        if not effective:
            return []

        n_eff = len(effective)
        per_src = max(1, (max(1, limit) + n_eff - 1) // n_eff)

        page_off = max(0, (max(1, page) - 1) * per_src)

        ck = (catalog_kind or "mods").strip().lower()
        if ck not in self.MODRINTH_PROJECT_TYPE_BY_KIND:
            ck = "mods"
        mr_pt = self.MODRINTH_PROJECT_TYPE_BY_KIND[ck]
        cf_class = self.get_curseforge_kind_class_map().get(ck, self.CURSEFORGE_MODS_CLASS_ID)

        mr_hits: List[ModInfo] = []
        cf_hits: List[ModInfo] = []

        if "modrinth" in effective:
            mr_hits = self.search_modrinth(
                query,
                minecraft_version,
                loader,
                per_src,
                offset=page_off,
                index=modrinth_index,
                project_type=mr_pt,
                catalog_kind=ck,
            )

        if "curseforge" in effective:
            cf_hits = self.search_curseforge(
                query,
                minecraft_version,
                loader,
                per_src,
                sort_field=curseforge_sort_field,
                index=page_off,
                class_id=cf_class,
                catalog_kind=ck,
            )

        if n_eff < 2:
            all_mods = mr_hits + cf_hits
        else:
            lim = max(1, limit)
            all_mods = _interleave_mr_cf_rows(mr_hits, cf_hits, limit=lim)
            mr_next = page_off + len(mr_hits)
            cf_next = page_off + len(cf_hits)
            _fill_rounds = 0
            while len(all_mods) < lim and _fill_rounds < 48:
                _fill_rounds += 1
                progressed = False
                need = lim - len(all_mods)
                if "modrinth" in effective and need > 0:
                    extra_mr = self.search_modrinth(
                        query,
                        minecraft_version,
                        loader,
                        need,
                        offset=mr_next,
                        index=modrinth_index,
                        project_type=mr_pt,
                        catalog_kind=ck,
                    )
                    if extra_mr:
                        all_mods.extend(extra_mr[:need])
                        mr_next += len(extra_mr)
                        progressed = True
                need = lim - len(all_mods)
                if "curseforge" in effective and need > 0:
                    extra_cf = self.search_curseforge(
                        query,
                        minecraft_version,
                        loader,
                        need,
                        sort_field=curseforge_sort_field,
                        index=cf_next,
                        class_id=cf_class,
                        catalog_kind=ck,
                    )
                    if extra_cf:
                        all_mods.extend(extra_cf[:need])
                        cf_next += len(extra_cf)
                        progressed = True
                if not progressed:
                    break

        return all_mods[: max(1, limit)]

    def search_all_sources_at_offsets(
        self,
        query: str,
        minecraft_version: Optional[str] = None,
        loader: Optional[str] = None,
        chunk_per_source: int = 48,
        mr_offset: int = 0,
        cf_index: int = 0,
        sources: Optional[List[str]] = None,
        curseforge_sort_field: int = 6,
        modrinth_index: str = "relevance",
        catalog_kind: str = "mods",
    ) -> tuple:
        """Fetch one catalog slice per source at explicit API offsets (deep pagination / full crawl).

        Returns ``(rows, next_mr_offset, next_cf_index, mr_exhausted, cf_exhausted)``. A source is
        *exhausted* when it is not queried, or when it returns fewer than ``chunk_per_source`` rows.
        """
        want = [
            s.strip().lower()
            for s in (sources or ["modrinth", "curseforge"])
            if s and s.strip().lower() in ("modrinth", "curseforge")
        ]
        if not want:
            want = ["modrinth", "curseforge"]

        ck = (catalog_kind or "mods").strip().lower()
        if ck not in self.MODRINTH_PROJECT_TYPE_BY_KIND:
            ck = "mods"
        mr_pt = self.MODRINTH_PROJECT_TYPE_BY_KIND[ck]
        cf_class = self.get_curseforge_kind_class_map().get(ck, self.CURSEFORGE_MODS_CLASS_ID)

        chunk = max(1, int(chunk_per_source))
        mo = max(0, int(mr_offset))
        ci = max(0, int(cf_index))

        mr_hits: List[ModInfo] = []
        cf_hits: List[ModInfo] = []

        if "modrinth" in want:
            mr_hits = self.search_modrinth(
                query,
                minecraft_version,
                loader,
                chunk,
                offset=mo,
                index=modrinth_index,
                project_type=mr_pt,
                catalog_kind=ck,
            )
            next_mr = mo + len(mr_hits)
            mr_exhausted = len(mr_hits) < chunk
        else:
            next_mr = mo
            mr_exhausted = True

        if "curseforge" in want and self._curseforge_key():
            cf_hits = self.search_curseforge(
                query,
                minecraft_version,
                loader,
                chunk,
                sort_field=curseforge_sort_field,
                index=ci,
                class_id=cf_class,
                catalog_kind=ck,
            )
            next_cf = ci + len(cf_hits)
            cf_exhausted = len(cf_hits) < chunk
        else:
            next_cf = ci
            cf_exhausted = True

        effective: List[str] = []
        if "modrinth" in want:
            effective.append("modrinth")
        if "curseforge" in want and self._curseforge_key():
            effective.append("curseforge")

        if len(effective) < 2:
            all_mods = mr_hits + cf_hits
        else:
            merged: List[ModInfo] = []
            for i in range(max(len(mr_hits), len(cf_hits))):
                if i < len(mr_hits):
                    merged.append(mr_hits[i])
                if i < len(cf_hits):
                    merged.append(cf_hits[i])
            all_mods = merged

        return all_mods, next_mr, next_cf, mr_exhausted, cf_exhausted