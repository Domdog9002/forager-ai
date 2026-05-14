#!/usr/bin/env python3
"""
Headless verification: Modrinth + CurseForge catalog search and file resolution.
Run from repo root: py scripts/verify_mod_catalog_apis.py
Exit 0 if Modrinth works; CurseForge checks run when CURSEFORGE_API_KEY or launcher key exists.
"""
from __future__ import annotations

import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from forager_ai.launcher.mod_downloader import ModDownloader  # noqa: E402


def main() -> int:
    errors: list[str] = []
    cache = tempfile.mkdtemp(prefix="forager_catalog_verify_")
    md = ModDownloader(cache)
    mr: list = []

    # Modrinth: popular mods 1.20.1 forge
    try:
        mr = md.search_modrinth(
            "",
            "1.20.1",
            "forge",
            6,
            offset=0,
            index="downloads",
            project_type="mod",
            catalog_kind="mods",
        )
        if len(mr) < 1:
            errors.append("Modrinth mod search returned no hits")
        else:
            print(f"OK Modrinth mods: {len(mr)} hits (e.g. {mr[0].name!r})")
    except Exception as e:
        errors.append(f"Modrinth mod search: {e}")

    # Modrinth: resource packs
    try:
        rp = md.search_modrinth(
            "",
            "1.20.1",
            "forge",
            5,
            offset=0,
            index="downloads",
            project_type="resourcepack",
            catalog_kind="resourcepack",
        )
        if len(rp) < 1:
            errors.append("Modrinth resource pack search returned no hits")
        else:
            print(f"OK Modrinth resource packs: {len(rp)} hits (e.g. {rp[0].name!r})")
    except Exception as e:
        errors.append(f"Modrinth RP search: {e}")

    # Modrinth: version list for first project
    try:
        if not mr:
            raise RuntimeError("no Modrinth rows to test versions")
        pid = mr[0].project_id
        vers = md.get_modrinth_versions(
            pid, minecraft_version="1.20.1", loader="forge", filter_loader=True, catalog_kind="mods"
        )
        if not vers:
            vers = md.get_modrinth_versions(pid, None, None, filter_loader=False, catalog_kind="mods")[:5]
        if not vers:
            errors.append("Modrinth get_modrinth_versions empty")
        else:
            print(f"OK Modrinth versions for {pid}: {len(vers)} (file {vers[0].file_name})")
    except Exception as e:
        errors.append(f"Modrinth versions: {e}")

    # CurseForge (optional key)
    if md.curseforge_configured():
        try:
            cf = md.search_curseforge(
                "",
                "1.20.1",
                "forge",
                6,
                sort_field=6,
                index=0,
                catalog_kind="mods",
            )
            if len(cf) < 1:
                errors.append("CurseForge mod search returned no hits")
            else:
                print(f"OK CurseForge mods: {len(cf)} hits (e.g. {cf[0].name!r})")
                cand = md.get_curseforge_install_candidate(
                    cf[0].project_id, "1.20.1", "forge", use_loader=True, catalog_kind="mods"
                )
                if not cand or not cand.download_url:
                    errors.append("CurseForge get_curseforge_install_candidate failed")
                else:
                    print(f"OK CurseForge install candidate: {cand.file_name}")
        except Exception as e:
            errors.append(f"CurseForge: {e}")

        try:
            cf_rp = md.search_curseforge(
                "",
                "1.20.1",
                "forge",
                4,
                sort_field=6,
                index=0,
                class_id=12,
                catalog_kind="resourcepack",
            )
            print(f"OK CurseForge resource packs: {len(cf_rp)} hits")
        except Exception as e:
            errors.append(f"CurseForge RP: {e}")
    else:
        print("Skip CurseForge (no API key) — add CURSEFORGE_API_KEY to test CF.")

    # Combined search (interleave)
    try:
        merged = md.search_all_sources(
            "",
            "1.20.1",
            "forge",
            8,
            sources=["modrinth", "curseforge"] if md.curseforge_configured() else ["modrinth"],
            page=1,
            modrinth_index="downloads",
            catalog_kind="mods",
        )
        if len(merged) < 1:
            errors.append("search_all_sources returned empty")
        else:
            print(f"OK search_all_sources: {len(merged)} projects")
    except Exception as e:
        errors.append(f"search_all_sources: {e}")

    for msg in errors:
        print(f"FAIL: {msg}", file=sys.stderr)
    if errors:
        return 1
    print("All checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
