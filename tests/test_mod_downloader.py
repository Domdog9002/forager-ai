from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.launcher.mod_downloader import ModDownloader, ModInfo, prefer_english_catalog_blurb


class _FakeSession:
    def __init__(self) -> None:
        self.calls = []

    def get(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if len(self.calls) == 1:
            raise requests.exceptions.SSLError("certificate verify failed")
        return object()


class ModDownloaderTests(unittest.TestCase):
    def test_get_retries_tls_failure_without_verification(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            downloader = ModDownloader(tmp)
            fake = _FakeSession()
            downloader.session = fake  # type: ignore[assignment]

            response = downloader._get("https://api.modrinth.com/v2/search", params={"limit": 1})

            self.assertIsNotNone(response)
            self.assertEqual(len(fake.calls), 2)
            self.assertFalse(fake.calls[1][1]["verify"])

    def test_get_respects_strict_tls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            downloader = ModDownloader(tmp)
            fake = _FakeSession()
            downloader.session = fake  # type: ignore[assignment]
            old_value = os.environ.get("FORAGER_STRICT_TLS")
            os.environ["FORAGER_STRICT_TLS"] = "1"
            try:
                with self.assertRaises(requests.exceptions.SSLError):
                    downloader._get("https://api.modrinth.com/v2/search")
            finally:
                if old_value is None:
                    os.environ.pop("FORAGER_STRICT_TLS", None)
                else:
                    os.environ["FORAGER_STRICT_TLS"] = old_value

    def test_search_all_sources_full_modrinth_quota_when_cf_selected_but_no_key(self) -> None:
        """UI may list both sources; without a CF key we must not halve per-source fetch + interleave against empty CF."""
        with tempfile.TemporaryDirectory() as tmp:
            dl = ModDownloader(tmp)
            mr_limits: list[int] = []

            def fake_mr(
                query,
                minecraft_version=None,
                loader=None,
                limit=20,
                offset=0,
                index="relevance",
                project_type="mod",
                catalog_kind="mods",
            ):
                mr_limits.append(int(limit))
                n = min(int(limit), 200)
                return [
                    ModInfo(
                        id=f"mr{i}",
                        name=f"MR {i}",
                        description="",
                        author="a",
                        source="modrinth",
                        project_id=f"mr{i}",
                        minecraft_versions=[],
                        loaders=[],
                        categories=[],
                        icon_url=None,
                        project_url=None,
                        download_total=0,
                        updated_at=None,
                        catalog_kind="mods",
                    )
                    for i in range(n)
                ]

            dl.search_modrinth = fake_mr  # type: ignore[method-assign]
            out = dl.search_all_sources(
                "",
                minecraft_version=None,
                loader=None,
                limit=200,
                sources=["modrinth", "curseforge"],
                page=1,
                modrinth_index="downloads",
                catalog_kind="mods",
            )
            self.assertEqual(mr_limits, [200])
            self.assertEqual(len(out), 200)

    def test_search_all_sources_fills_modrinth_when_cf_side_returns_nothing(self) -> None:
        """CurseForge can be 'active' yet return 0 hits; we must still reach ``limit`` from Modrinth."""
        with tempfile.TemporaryDirectory() as tmp:
            dl = ModDownloader(tmp)
            dl.set_curseforge_api_key("fake-key-for-branch")
            mr_calls: list[tuple[int, int]] = []

            def fake_mr(
                query,
                minecraft_version=None,
                loader=None,
                limit=20,
                offset=0,
                index="relevance",
                project_type="mod",
                catalog_kind="mods",
            ):
                mr_calls.append((int(offset), int(limit)))
                off = int(offset)
                lim = int(limit)
                if off == 0:
                    return [
                        ModInfo(
                            id=f"mr{i}",
                            name=f"MR {i}",
                            description="",
                            author="a",
                            source="modrinth",
                            project_id=f"mr{i}",
                            catalog_kind="mods",
                        )
                        for i in range(100)
                    ]
                return [
                    ModInfo(
                        id=f"mr{i}",
                        name=f"MR {i}",
                        description="",
                        author="a",
                        source="modrinth",
                        project_id=f"mr{i}",
                        catalog_kind="mods",
                    )
                    for i in range(off, off + min(lim, 100))
                ]

            def fake_cf(*args, **kwargs):
                return []

            dl.search_modrinth = fake_mr  # type: ignore[method-assign]
            dl.search_curseforge = fake_cf  # type: ignore[method-assign]
            out = dl.search_all_sources(
                "",
                minecraft_version=None,
                loader=None,
                limit=200,
                sources=["modrinth", "curseforge"],
                page=1,
                modrinth_index="downloads",
                catalog_kind="mods",
            )
            self.assertEqual(len(out), 200)
            offs = [c[0] for c in mr_calls]
            self.assertIn(0, offs)
            self.assertIn(100, offs)


class PreferEnglishCatalogBlurbTests(unittest.TestCase):
    def test_mixed_cjk_then_english_after_em_dash(self) -> None:
        s = "僵尸入侵 100 天 —— Same as Forge Labs 100 Days Zombie Apocalypse in new Minecraft"
        out = prefer_english_catalog_blurb(s)
        self.assertIn("Forge Labs", out)
        self.assertNotIn("僵尸", out)

    def test_mostly_cjk_only_returns_empty(self) -> None:
        s = "厌倦了每次开局都是一样的钻石剑和弓，每场重生都像开盲盒。"
        out = prefer_english_catalog_blurb(s)
        self.assertEqual(out, "")

    def test_plain_english_preserved(self) -> None:
        s = "A cozy tech modpack for Forge 1.20.1 with Create and friends."
        self.assertEqual(prefer_english_catalog_blurb(s), s)


if __name__ == "__main__":
    unittest.main()
