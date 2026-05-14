"""
Extract display metadata from local Minecraft mod jars (NeoForge/Forge, Fabric, Quilt).

Used by the dashboard Mod library — best-effort only; many jars omit or relocate files.
"""

from __future__ import annotations

import base64
import json
import re
import zipfile
from typing import Any, Dict, List, Optional, Tuple

_MAX_IMG_BYTES = 48_000
_MAX_DESC_STORE = 4_000


def _mime_for_img(data: bytes) -> str:
    if len(data) >= 8 and data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return "image/jpeg"
    if len(data) >= 6 and data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _read_zip_bytes(z: zipfile.ZipFile, rel: str) -> Optional[bytes]:
    rel = rel.replace("\\", "/").lstrip("/")
    for cand in (rel, rel.lower()):
        try:
            return z.read(cand)
        except KeyError:
            continue
    return None


def _read_zip_text(z: zipfile.ZipFile, names: Tuple[str, ...]) -> Optional[str]:
    for n in names:
        try:
            return z.read(n).decode("utf-8", errors="replace")
        except KeyError:
            continue
        except OSError:
            continue
    return None


def _parse_fabric_mod_json(raw: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    mid = str(data.get("id") or "").strip()
    name = str(data.get("name") or mid).strip()
    desc = str(data.get("description") or "").strip()
    icon = data.get("icon")
    icon_path = str(icon).strip() if isinstance(icon, str) else None
    tags: List[str] = []
    for a in data.get("authors") or []:
        if isinstance(a, dict) and a.get("name"):
            tags.append(str(a["name"]).strip())
        elif isinstance(a, str) and a.strip():
            tags.append(a.strip())
    env = data.get("environment")
    if isinstance(env, str) and env:
        tags.append(f"env:{env}")
    ver = data.get("version")
    ver_s = str(ver).strip() if isinstance(ver, str) else ""
    author_list: List[str] = []
    for a in data.get("authors") or []:
        if isinstance(a, dict) and a.get("name"):
            author_list.append(str(a["name"]).strip())
        elif isinstance(a, str) and a.strip():
            author_list.append(a.strip())
    return {
        "mod_id": mid,
        "display_name": name or mid,
        "description": desc[:_MAX_DESC_STORE],
        "logo_path": icon_path,
        "loader_kind": "fabric",
        "extra_tags": tags,
        "author_list": author_list,
        "mod_version": ver_s,
    }


def _parse_quilt_mod_json(raw: str) -> Optional[Dict[str, Any]]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    ql = data.get("quilt_loader")
    if not isinstance(ql, dict):
        return None
    mid = str(ql.get("id") or "").strip()
    meta = ql.get("metadata")
    if not isinstance(meta, dict):
        meta = {}
    name = str(meta.get("name") or mid).strip()
    desc = str(meta.get("description") or "").strip()
    icon = meta.get("icon")
    icon_path = str(icon).strip() if isinstance(icon, str) else None
    tags: List[str] = []
    author_list: List[str] = []
    contrib = meta.get("contributors")
    if isinstance(contrib, dict):
        for role, names in contrib.items():
            if isinstance(names, str) and names.strip():
                tags.append(f"{role}:{names.strip()}")
                if role.lower() in ("author", "authors", "owner", "maintainer"):
                    author_list.append(names.strip())
    ver = meta.get("version")
    ver_s = str(ver).strip() if isinstance(ver, str) else ""
    return {
        "mod_id": mid,
        "display_name": name or mid,
        "description": desc[:_MAX_DESC_STORE],
        "logo_path": icon_path,
        "loader_kind": "quilt",
        "extra_tags": tags,
        "author_list": author_list,
        "mod_version": ver_s,
    }


def _parse_mods_toml(raw: str) -> Optional[Dict[str, Any]]:
    data: Optional[Dict[str, Any]] = None
    try:
        import tomllib

        data = tomllib.loads(raw)
    except Exception:
        data = None
    if not isinstance(data, dict):
        return _parse_mods_toml_regex(raw)
    mods = data.get("mods")
    if not isinstance(mods, list) or not mods:
        return _parse_mods_toml_regex(raw)
    m0 = mods[0]
    if not isinstance(m0, dict):
        return _parse_mods_toml_regex(raw)
    mid = str(m0.get("modId") or m0.get("modid") or "").strip()
    name = str(m0.get("displayName") or m0.get("display_name") or mid).strip()
    desc = m0.get("description")
    desc_s = str(desc).strip()[:_MAX_DESC_STORE] if desc is not None else ""
    logo = m0.get("logoFile") or m0.get("logo_file")
    logo_path = str(logo).strip() if logo else None
    tags: List[str] = []
    author_list: List[str] = []
    authors = m0.get("authors")
    if isinstance(authors, str):
        for p in re.split(r"[\n,&]", authors):
            s = p.strip()
            if s:
                tags.append(s)
                author_list.append(s)
    elif isinstance(authors, list):
        for a in authors:
            if isinstance(a, str) and a.strip():
                tags.append(a.strip())
                author_list.append(a.strip())
            elif isinstance(a, dict) and a.get("name"):
                nm = str(a["name"]).strip()
                tags.append(nm)
                author_list.append(nm)
    ver_raw = m0.get("version")
    ver_s = str(ver_raw).strip() if isinstance(ver_raw, str) else ""
    lk = "forge"
    lid = str(m0.get("modId") or "").lower()
    if "neoforge" in raw.lower() or lid.endswith("_neoforge"):
        lk = "neoforge"
    return {
        "mod_id": mid,
        "display_name": name or mid,
        "description": desc_s,
        "logo_path": logo_path,
        "loader_kind": lk,
        "extra_tags": tags,
        "author_list": author_list,
        "mod_version": ver_s,
    }


def _parse_mods_toml_regex(raw: str) -> Optional[Dict[str, Any]]:
    """Tiny fallback when TOML is malformed."""
    m_id = re.search(r'(?im)^\s*modId\s*=\s*"([^"]+)"', raw)
    m_dn = re.search(r'(?im)^\s*(?:displayName|display_name)\s*=\s*"([^"]*)"', raw)
    mid = m_id.group(1).strip() if m_id else ""
    name = m_dn.group(1).strip() if m_dn else mid
    if not mid and not name:
        return None
    return {
        "mod_id": mid,
        "display_name": name or mid,
        "description": "",
        "logo_path": None,
        "loader_kind": "forge",
        "extra_tags": [],
        "author_list": [],
        "mod_version": "",
    }


def _logo_data_uri(z: zipfile.ZipFile, rel: Optional[str]) -> str:
    if not rel:
        return ""
    data = _read_zip_bytes(z, rel)
    if not data or len(data) > _MAX_IMG_BYTES:
        return ""
    mime = _mime_for_img(data)
    b64 = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{b64}"


def read_jar_mod_metadata(jar_path: str) -> Dict[str, Any]:
    """
    Return keys: display_name, mod_id, description, loader_kind, tags (sorted),
    logo_data_uri (small inline image or empty), file_stem (for fallback title).
    """
    out: Dict[str, Any] = {
        "display_name": "",
        "mod_id": "",
        "description": "",
        "loader_kind": "unknown",
        "tags": [],
        "logo_data_uri": "",
        "authors": [],
        "version": "",
    }
    try:
        with zipfile.ZipFile(jar_path, "r") as z:
            parsed: Optional[Dict[str, Any]] = None
            # Prefer Forge/NeoForge ``mods.toml`` when present. Many hybrid or library jars ship a
            # ``fabric.mod.json`` for API/submodule metadata; reading Fabric first mislabels the jar
            # and triggers false "not Forge compatible" Pack Health guardrails.
            raw_toml = _read_zip_text(
                z,
                ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"),
            )
            if raw_toml:
                parsed = _parse_mods_toml(raw_toml)
            if not parsed:
                raw_fab = _read_zip_text(z, ("fabric.mod.json",))
                if raw_fab:
                    parsed = _parse_fabric_mod_json(raw_fab)
            if not parsed:
                raw_q = _read_zip_text(z, ("quilt.mod.json",))
                if raw_q:
                    parsed = _parse_quilt_mod_json(raw_q)
            if not parsed:
                return out

            out["mod_id"] = parsed.get("mod_id") or ""
            out["display_name"] = str(parsed.get("display_name") or "").strip()
            out["description"] = str(parsed.get("description") or "").strip()
            out["loader_kind"] = str(parsed.get("loader_kind") or "unknown")
            auth_src = parsed.get("author_list")
            author_out: List[str] = []
            if isinstance(auth_src, list):
                seen_a: set = set()
                for a in auth_src:
                    sx = str(a).strip()
                    if sx and len(sx) < 96 and sx.lower() not in seen_a:
                        seen_a.add(sx.lower())
                        author_out.append(sx)
            out["authors"] = author_out[:10]
            out["version"] = str(parsed.get("mod_version") or "").strip()
            logo_path = parsed.get("logo_path")
            if isinstance(logo_path, str) and logo_path:
                uri = _logo_data_uri(z, logo_path)
                if uri and len(uri) < 65_000:
                    out["logo_data_uri"] = uri

            tag_set: set = set()
            for t in parsed.get("extra_tags") or []:
                s = str(t).strip()
                if s and len(s) < 80:
                    tag_set.add(s)
            if out["loader_kind"] != "unknown":
                tag_set.add(out["loader_kind"])
            if out["mod_id"]:
                tag_set.add(out["mod_id"][:48])
            tag_set.add("local jar")
            out["tags"] = sorted(tag_set, key=str.lower)
    except (zipfile.BadZipFile, OSError):
        pass
    return out
