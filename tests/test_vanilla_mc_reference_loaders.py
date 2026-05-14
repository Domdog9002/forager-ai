"""Regression: ``load_items`` / ``load_blocks`` must both exist (catalog builder)."""

from unittest.mock import patch

from forager_ai.catalog import vanilla_mc_reference as vmr


def test_load_items_and_load_blocks_are_distinct(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_fetch(version: str, filename: str):
        calls.append((version, filename))
        if filename == "items.json":
            return [{"name": "stick", "displayName": "Stick", "stackSize": 64}]
        if filename == "blocks.json":
            return [{"name": "stone", "displayName": "Stone", "hardness": 1.5}]
        return []

    monkeypatch.setattr(vmr, "fetch_json", fake_fetch)
    items = vmr.load_items("1.20.4")
    blocks = vmr.load_blocks("1.20.4")
    assert any(fn == "items.json" for _, fn in calls)
    assert any(fn == "blocks.json" for _, fn in calls)
    assert items[0]["name"] == "stick"
    assert blocks[0]["name"] == "stone"


def test_build_catalog_for_version_calls_both_loaders(monkeypatch) -> None:
    def fake_fetch(version: str, filename: str):
        if filename == "items.json":
            return [{"name": "egg", "displayName": "Spawn Egg", "stackSize": 1}]
        if filename == "blocks.json":
            return [{"name": "dirt", "displayName": "Dirt", "hardness": 0.5}]
        if filename == "foods.json":
            return []
        if filename == "enchantments.json":
            return []
        return None

    monkeypatch.setattr(vmr, "fetch_json", fake_fetch)
    cat = vmr.build_catalog_for_version("1.20.4")
    assert len(cat["items"]) == 1
    assert len(cat["blocks"]) == 1
    assert cat["blocks"][0]["type"] == "block"
