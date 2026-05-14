"""Mob scaffold zip generator."""

import io
import zipfile

from forager_ai.mods.mob_scaffold import (
    ABILITY_IDS,
    MobScaffoldSpec,
    build_mob_scaffold_zip,
    load_mob_authoring_playbooks,
    mob_scaffold_spec_from_mapping,
)


def test_build_zip_contains_java_readme_and_lang() -> None:
    spec = MobScaffoldSpec(
        mod_id="demo_mod",
        java_package="com.demo.mod.mobs",
        entity_class_name="TestWyrm",
        registry_name="test_wyrm",
        display_name="Test Wyrm",
        abilities=("leap_melee", "aoe_slam"),
    )
    raw = build_mob_scaffold_zip(spec)
    zf = zipfile.ZipFile(io.BytesIO(raw), "r")
    names = zf.namelist()
    assert "README_FORAGER_MOB.md" in names
    assert "docs/GECKOLIB_NOTES.md" in names
    assert "src/main/resources/assets/demo_mod/lang/en_us.json" in names
    assert "src/main/java/com/demo/mod/mobs/TestWyrm.java" in names
    assert "src/main/java/com/demo/mod/mobs/TestWyrmEntities.java" in names
    assert "src/main/java/com/demo/mod/mobs/ForagerMobGoals.java" in names
    assert "docs/mob_authoring_playbooks.json" in names
    readme = zf.read("README_FORAGER_MOB.md").decode("utf-8")
    assert "TestWyrm" in readme
    assert "leap_melee" in readme
    java = zf.read("src/main/java/com/demo/mod/mobs/TestWyrm.java").decode("utf-8")
    assert "ForagerLeapMeleeGoal" in java
    assert "package com.demo.mod.mobs" in java


def test_playbooks_load() -> None:
    play = load_mob_authoring_playbooks()
    assert isinstance(play, list)
    assert any(p.get("id") == "mob_smoke_test" for p in play)


def test_spec_from_mapping_filters_abilities() -> None:
    s = mob_scaffold_spec_from_mapping({"abilities": ["leap_melee", "not_real"], "mod_id": "X-Mod!"})
    assert s.mod_id == "x_mod"
    assert s.abilities == ("leap_melee",)


def test_ability_ids_cover_templates() -> None:
    assert "phase_speed_burst" in ABILITY_IDS
