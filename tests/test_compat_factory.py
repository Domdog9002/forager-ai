"""Compat factory zip smoke tests."""

from __future__ import annotations

import io
import zipfile

from forager_ai.engine.compat_factory import (
    build_combined_compat_factory_zips,
    build_datapack_kubejs_layer,
    slug_token,
)


def test_slug_token_sanitizes() -> None:
    assert slug_token("My Mod!!") == "my_mod"
    assert slug_token("") == "unnamed"


def test_datapack_layer_contains_pack_mcmeta_and_kubejs() -> None:
    files = build_datapack_kubejs_layer(
        source_mod_label="Weapons X",
        target_framework="Epic Fight",
        optional_partner_mod="",
        minecraft_version="1.20.1",
        datapack_namespace="test_ns",
    )
    assert any(k.endswith("pack.mcmeta") for k in files)
    assert any("tags/items" in k for k in files)
    assert "kubejs/startup_scripts/forager_compat_stub.js" in files


def test_combined_zips_are_non_empty_and_readable() -> None:
    zb, za, nb, na = build_combined_compat_factory_zips(
        source_mod_label="Alpha",
        target_framework="BetaFW",
        optional_partner_mod="",
        minecraft_version="1.20.1",
        forge_version="47.2.0",
        datapack_namespace="demo",
        java_mod_id="democompat",
    )
    assert nb.endswith(".zip") and na.endswith(".zip")
    assert len(zb) > 80 and len(za) > 200
    with zipfile.ZipFile(io.BytesIO(zb)) as zf:
        names = zf.namelist()
        assert any(n.endswith("pack.mcmeta") for n in names)
    with zipfile.ZipFile(io.BytesIO(za)) as zf:
        names = zf.namelist()
        assert "build.gradle" in names
        assert any(n.endswith(".java") for n in names)
        assert "gradlew.bat" in names
        assert "gradle/wrapper/gradle-wrapper.properties" in names
        if "gradle/wrapper/gradle-wrapper.jar" in names:
            info = zf.getinfo("gradle/wrapper/gradle-wrapper.jar")
            assert info.file_size > 1000
