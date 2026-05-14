"""
Vanilla Minecraft reference data (items, blocks, mobs, …) for in-app browsing.

Data: PrismarineJS minecraft-data (JSON). Textures: InventivetalentDev minecraft-assets
via raw.githubusercontent.com (official 16×16 / 32×32 PNGs; displayed scaled with crisp pixel scaling).
"""

from __future__ import annotations

import functools
import re
from typing import Any, Dict, List, Optional, Sequence

import requests

from forager_ai.catalog.taxonomy import classify_entry, infer_progression_tier

MINECRAFT_DATA_BASE = "https://raw.githubusercontent.com/PrismarineJS/minecraft-data/master/data/pc"
TEXTURE_BASE = (
    "https://raw.githubusercontent.com/InventivetalentDev/minecraft-assets/{ver}/assets/minecraft/textures"
)

# Versions known to ship the full JSON set this UI expects (``items.json``, etc. on ``pc/<ver>/``).
# Note: ``1.20.1`` exists on Prismarine but only ships ``version.json`` + ``sounds.json`` — use a nearby full export.
SUPPORTED_VERSIONS: Sequence[str] = ("1.21.4", "1.21.1", "1.20.6", "1.20.4", "1.20")

_session = requests.Session()
_session.headers.update({"User-Agent": "ForagerAI/1.0 (vanilla reference; +https://github.com/PrismarineJS/minecraft-data)"})

# Mobs that are important but do not have a spawn egg item in survival-style lists.
EXTRA_MOB_NAMES: Sequence[str] = (
    "ender_dragon",
    "wither",
    "giant",
    "illusioner",
)

# Rough hostility for spawn-egg-derived mobs (unknown defaults to neutral).
_PASSIVE = frozenset(
    {
        "allay",
        "axolotl",
        "bat",
        "camel",
        "cat",
        "chicken",
        "cod",
        "cow",
        "donkey",
        "frog",
        "glow_squid",
        "horse",
        "mooshroom",
        "mule",
        "ocelot",
        "parrot",
        "pig",
        "pufferfish",
        "rabbit",
        "salmon",
        "sheep",
        "skeleton_horse",
        "sniffer",
        "snow_golem",
        "squid",
        "strider",
        "tadpole",
        "tropical_fish",
        "turtle",
        "villager",
        "wandering_trader",
    }
)
_HOSTILE = frozenset(
    {
        "blaze",
        "bogged",
        "breeze",
        "cave_spider",
        "creaking",
        "creeper",
        "drowned",
        "elder_guardian",
        "ender_dragon",
        "enderman",
        "endermite",
        "evoker",
        "ghast",
        "guardian",
        "hoglin",
        "husk",
        "magma_cube",
        "phantom",
        "piglin",
        "piglin_brute",
        "pillager",
        "ravager",
        "shulker",
        "silverfish",
        "skeleton",
        "slime",
        "spider",
        "stray",
        "vex",
        "vindicator",
        "warden",
        "witch",
        "wither",
        "wither_skeleton",
        "zoglin",
        "zombie",
        "zombie_villager",
        "zombified_piglin",
    }
)

VANILLA_STRUCTURES: List[Dict[str, Any]] = [
    {"id": "village", "displayName": "Village", "dimension": "overworld", "icon_item": "bell"},
    {"id": "pillager_outpost", "displayName": "Pillager Outpost", "dimension": "overworld", "icon_item": "crossbow"},
    {"id": "mineshaft", "displayName": "Mineshaft", "dimension": "overworld", "icon_item": "minecart"},
    {"id": "stronghold", "displayName": "Stronghold", "dimension": "overworld", "icon_item": "ender_eye"},
    {"id": "monument", "displayName": "Ocean Monument", "dimension": "overworld", "icon_item": "prismarine_shard"},
    {"id": "mansion", "displayName": "Woodland Mansion", "dimension": "overworld", "icon_item": "totem_of_undying"},
    {"id": "desert_pyramid", "displayName": "Desert Pyramid", "dimension": "overworld", "icon_item": "sand"},
    {"id": "jungle_pyramid", "displayName": "Jungle Pyramid", "dimension": "overworld", "icon_item": "cobblestone"},
    {"id": "igloo", "displayName": "Igloo", "dimension": "overworld", "icon_item": "snow_block"},
    {"id": "swamp_hut", "displayName": "Swamp Hut", "dimension": "overworld", "icon_item": "cauldron"},
    {"id": "shipwreck", "displayName": "Shipwreck", "dimension": "overworld", "icon_item": "oak_boat"},
    {"id": "ocean_ruin", "displayName": "Ocean Ruins", "dimension": "overworld", "icon_item": "mossy_stone_bricks"},
    {"id": "buried_treasure", "displayName": "Buried Treasure", "dimension": "overworld", "icon_item": "chest"},
    {"id": "ruined_portal", "displayName": "Ruined Portal", "dimension": "any", "icon_item": "obsidian"},
    {"id": "ancient_city", "displayName": "Ancient City", "dimension": "overworld", "icon_item": "sculk_sensor"},
    {"id": "trail_ruins", "displayName": "Trail Ruins", "dimension": "overworld", "icon_item": "brush"},
    {"id": "trial_chambers", "displayName": "Trial Chambers", "dimension": "overworld", "icon_item": "trial_key"},
    {"id": "nether_fortress", "displayName": "Nether Fortress", "dimension": "nether", "icon_item": "blaze_rod"},
    {"id": "bastion_remnant", "displayName": "Bastion Remnant", "dimension": "nether", "icon_item": "gilded_blackstone"},
    {"id": "nether_fossil", "displayName": "Nether Fossil", "dimension": "nether", "icon_item": "bone"},
    {"id": "end_city", "displayName": "End City", "dimension": "end", "icon_item": "shulker_shell"},
    {"id": "end_gateway", "displayName": "End Gateway", "dimension": "end", "icon_item": "ender_pearl"},
]

VANILLA_BIOMES: List[Dict[str, Any]] = [
    {"id": "plains", "displayName": "Plains", "dimension": "overworld", "icon_block": "grass_block_top"},
    {"id": "forest", "displayName": "Forest", "dimension": "overworld", "icon_block": "oak_log_top"},
    {"id": "dark_forest", "displayName": "Dark Forest", "dimension": "overworld", "icon_block": "dark_oak_log_top"},
    {"id": "taiga", "displayName": "Taiga", "dimension": "overworld", "icon_block": "spruce_log_top"},
    {"id": "snowy_taiga", "displayName": "Snowy Taiga", "dimension": "overworld", "icon_block": "snow"},
    {"id": "desert", "displayName": "Desert", "dimension": "overworld", "icon_block": "sand"},
    {"id": "badlands", "displayName": "Badlands", "dimension": "overworld", "icon_block": "red_sand"},
    {"id": "savanna", "displayName": "Savanna", "dimension": "overworld", "icon_block": "acacia_log_top"},
    {"id": "jungle", "displayName": "Jungle", "dimension": "overworld", "icon_block": "jungle_log_top"},
    {"id": "swamp", "displayName": "Swamp", "dimension": "overworld", "icon_block": "mangrove_roots"},
    {"id": "deep_dark", "displayName": "Deep Dark", "dimension": "overworld", "icon_block": "sculk"},
    {"id": "lush_caves", "displayName": "Lush Caves", "dimension": "overworld", "icon_block": "moss_block"},
    {"id": "dripstone_caves", "displayName": "Dripstone Caves", "dimension": "overworld", "icon_block": "pointed_dripstone_down_tip"},
    {"id": "meadow", "displayName": "Meadow", "dimension": "overworld", "icon_block": "short_grass"},
    {"id": "cherry_grove", "displayName": "Cherry Grove", "dimension": "overworld", "icon_block": "cherry_leaves"},
    {"id": "nether_wastes", "displayName": "Nether Wastes", "dimension": "nether", "icon_block": "netherrack"},
    {"id": "soul_sand_valley", "displayName": "Soul Sand Valley", "dimension": "nether", "icon_block": "soul_sand"},
    {"id": "crimson_forest", "displayName": "Crimson Forest", "dimension": "nether", "icon_block": "crimson_stem"},
    {"id": "warped_forest", "displayName": "Warped Forest", "dimension": "nether", "icon_block": "warped_stem"},
    {"id": "basalt_deltas", "displayName": "Basalt Deltas", "dimension": "nether", "icon_block": "basalt_top"},
    {"id": "the_end", "displayName": "The End", "dimension": "end", "icon_block": "end_stone"},
    {"id": "small_end_islands", "displayName": "Small End Islands", "dimension": "end", "icon_block": "purpur_block"},
]


def _tb(ver: str) -> str:
    return TEXTURE_BASE.format(ver=ver)


def item_texture_primary(name: str, version: str) -> str:
    return f"{_tb(version)}/item/{name}.png"


def block_texture_primary(name: str, version: str) -> str:
    return f"{_tb(version)}/block/{name}.png"


# Entity PNG path relative to textures/ (without .png) when not entity/<name>/<name>.png
_MOB_TEXTURE_REL_PATH: Dict[str, str] = {
    "ender_dragon": "entity/enderdragon/dragon",
    "snow_golem": "entity/snowman",
}


def mob_texture_primary(mob_name: str, version: str) -> str:
    base = _tb(version)
    n = mob_name.strip().lower()
    rel = _MOB_TEXTURE_REL_PATH.get(n)
    if rel:
        return f"{base}/{rel}.png"
    return f"{base}/entity/{n}/{n}.png"


@functools.lru_cache(maxsize=32)
def fetch_json(version: str, filename: str) -> Optional[Any]:
    url = f"{MINECRAFT_DATA_BASE}/{version}/{filename}"
    try:
        r = _session.get(url, timeout=50)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"vanilla_mc_reference: {url} -> {e}")
        return None


def catalog_data_version_for_instance(mc_version: str) -> tuple[str, Optional[str]]:
    """
    Map an instance's Minecraft version to a Prismarine ``pc/<ver>`` dataset with ``items.json``.

    Returns ``(data_version, user_note)`` where ``user_note`` explains fallback when needed.
    """
    v = (mc_version or "").strip()
    if v in SUPPORTED_VERSIONS:
        return v, None
    if re.match(r"^1\.20\.1$", v):
        return (
            "1.20.4",
            "Prismarine does not publish full ``items.json`` for **1.20.1**; this browser uses **1.20.4** "
            "reference data and textures (almost all ids match 1.20.1).",
        )
    if re.match(r"^1\.20\.[23]$", v):
        return "1.20.4", f"Using **1.20.4** reference data for instance **{v}** (nearest full export)."
    if re.match(r"^1\.20(\.0)?$", v) or v == "1.20":
        return "1.20", None
    return (
        SUPPORTED_VERSIONS[0],
        f"No tuned mapping for **{v}** — showing **{SUPPORTED_VERSIONS[0]}** reference data.",
    )


def load_items(version: str) -> List[Dict[str, Any]]:
    data = fetch_json(version, "items.json")
    return data if isinstance(data, list) else []


def load_blocks(version: str) -> List[Dict[str, Any]]:
    data = fetch_json(version, "blocks.json")
    return data if isinstance(data, list) else []


def load_enchantments(version: str) -> List[Dict[str, Any]]:
    data = fetch_json(version, "enchantments.json")
    return data if isinstance(data, list) else []


def load_foods(version: str) -> List[Dict[str, Any]]:
    data = fetch_json(version, "foods.json")
    return data if isinstance(data, list) else []


def _food_name_set(version: str) -> frozenset:
    """Item `name` strings that appear in minecraft-data foods.json for this version."""
    foods = load_foods(version)
    names: List[str] = []
    for f in foods:
        if isinstance(f, dict):
            n = f.get("name")
            if n:
                names.append(str(n))
    return frozenset(names)


def enrich_item_row(raw: Dict[str, Any], version: str, food_names: frozenset) -> Dict[str, Any]:
    name = str(raw.get("name", ""))
    display = str(raw.get("displayName", name))
    stack = int(raw.get("stackSize") or 0)
    entry: Dict[str, Any] = {
        "type": "item",
        "id": name,
        "displayName": display,
        "stackSize": stack,
        "image": item_texture_primary(name, version),
        "image_fallback": block_texture_primary(name, version),
        "is_food": name in food_names,
    }
    entry = classify_entry(
        {
            **entry,
            "displayName": display,
        }
    )
    return entry


def enrich_block_row(raw: Dict[str, Any], version: str) -> Dict[str, Any]:
    name = str(raw.get("name", ""))
    display = str(raw.get("displayName", name))
    hardness = raw.get("hardness")
    entry: Dict[str, Any] = {
        "type": "block",
        "id": name,
        "displayName": display,
        "hardness": hardness,
        "stackSize": 64,
        "image": block_texture_primary(name, version),
        "image_fallback": item_texture_primary(name, version),
    }
    entry = classify_entry({**entry, "displayName": display})
    return entry


def mob_hostility(mob: str) -> str:
    m = mob.lower()
    if m in _PASSIVE:
        return "passive"
    if m in _HOSTILE:
        return "hostile"
    return "neutral"


def enrich_mob_row(mob_name: str, display_name: str, version: str) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "type": "mob",
        "id": mob_name,
        "displayName": display_name,
        "stackSize": 0,
        "image": mob_texture_primary(mob_name, version),
        "image_fallback": item_texture_primary(f"{mob_name}_spawn_egg", version),
        "hostility": mob_hostility(mob_name),
    }
    entry = classify_entry({**entry, "displayName": display_name})
    return entry


def derive_mobs_from_items(items: List[Dict[str, Any]], version: str) -> List[Dict[str, Any]]:
    seen: Dict[str, str] = {}
    for it in items:
        if not isinstance(it, dict):
            continue
        n = str(it.get("name", ""))
        if n.endswith("_spawn_egg"):
            mob = n[: -len("_spawn_egg")]
            disp = str(it.get("displayName", mob))
            if mob and mob not in seen:
                seen[mob] = disp.replace(" Spawn Egg", "").strip() or mob.replace("_", " ").title()
    for extra in EXTRA_MOB_NAMES:
        if extra not in seen:
            seen[extra] = extra.replace("_", " ").title()
    out: List[Dict[str, Any]] = []
    for mob_name in sorted(seen.keys()):
        out.append(enrich_mob_row(mob_name, seen[mob_name], version))
    return out


def enrich_structure_row(raw: Dict[str, Any], version: str) -> Dict[str, Any]:
    sid = str(raw["id"])
    display = str(raw.get("displayName", sid))
    icon = str(raw.get("icon_item", "map"))
    entry: Dict[str, Any] = {
        "type": "structure",
        "id": sid,
        "displayName": display,
        "dimension": str(raw.get("dimension", "overworld")),
        "stackSize": 0,
        "image": item_texture_primary(icon, version),
        "image_fallback": block_texture_primary("stone_bricks", version),
    }
    entry = classify_entry({**entry, "displayName": display})
    return entry


def enrich_biome_row(raw: Dict[str, Any], version: str) -> Dict[str, Any]:
    bid = str(raw["id"])
    display = str(raw.get("displayName", bid))
    blk = str(raw.get("icon_block", "grass_block_top"))
    entry: Dict[str, Any] = {
        "type": "biome",
        "id": bid,
        "displayName": display,
        "dimension": str(raw.get("dimension", "overworld")),
        "stackSize": 0,
        "image": block_texture_primary(blk, version),
        "image_fallback": block_texture_primary("grass_block_top", version),
    }
    entry = classify_entry({**entry, "displayName": display})
    return entry


def enrich_food_row(raw: Dict[str, Any], version: str) -> Dict[str, Any]:
    name = str(raw.get("name", ""))
    display = str(raw.get("displayName", name))
    entry: Dict[str, Any] = {
        "type": "food",
        "id": name,
        "displayName": display,
        "stackSize": int(raw.get("stackSize") or 64),
        "foodPoints": raw.get("foodPoints"),
        "saturation": raw.get("saturation"),
        "effectiveQuality": raw.get("effectiveQuality"),
        "image": item_texture_primary(name, version),
        "image_fallback": block_texture_primary(name, version),
        "is_food": True,
    }
    entry = classify_entry({**entry, "displayName": display})
    return entry


def enrich_enchant_row(raw: Dict[str, Any], version: str) -> Dict[str, Any]:
    """Prismarine enchantments vary slightly by version; normalize fields."""
    eid = str(raw.get("name") or raw.get("id") or "unknown")
    display = str(raw.get("displayName", eid.replace("_", " ").title()))
    max_lvl = raw.get("maxLevel") or raw.get("lvl") or "?"
    entry: Dict[str, Any] = {
        "type": "enchantment",
        "id": eid,
        "displayName": display,
        "stackSize": 0,
        "maxLevel": max_lvl,
        "image": item_texture_primary("enchanted_book", version),
        "image_fallback": item_texture_primary("book", version),
    }
    entry = classify_entry({**entry, "displayName": display})
    return entry


def filter_entries(
    entries: List[Dict[str, Any]],
    *,
    q: str,
    tiers: Optional[Sequence[str]] = None,
    dimensions: Optional[Sequence[str]] = None,
    hostilities: Optional[Sequence[str]] = None,
    stack_bucket: str = "any",
    food_only: bool = False,
    taxonomy_contains: Optional[str] = None,
) -> List[Dict[str, Any]]:
    qlow = (q or "").strip().lower()
    want_tiers = {t.lower() for t in tiers} if tiers else None
    want_dim = {d.lower() for d in dimensions} if dimensions else None
    want_host = {h.lower() for h in hostilities} if hostilities else None
    out: List[Dict[str, Any]] = []
    for e in entries:
        if food_only and not e.get("is_food"):
            continue
        if want_tiers:
            if str(e.get("progression_tier", "unknown")).lower() not in want_tiers:
                continue
        if want_dim:
            d = str(e.get("dimension", "")).lower()
            if d and d not in want_dim and d != "any":
                continue
        if want_host:
            h = str(e.get("hostility", "")).lower()
            if h and h not in want_host:
                continue
        if stack_bucket == "1" and int(e.get("stackSize") or 0) != 1:
            continue
        if stack_bucket == "16" and int(e.get("stackSize") or 0) != 16:
            continue
        if stack_bucket == "64" and int(e.get("stackSize") or 0) != 64:
            continue
        if taxonomy_contains:
            needle = taxonomy_contains.lower().strip()
            tags = [str(t).lower() for t in (e.get("taxonomy_tags") or [])]
            if not any(needle in t for t in tags):
                continue
        if qlow:
            blob = (
                str(e.get("id", ""))
                + " "
                + str(e.get("displayName", ""))
                + " "
                + " ".join(str(t) for t in (e.get("taxonomy_tags") or []))
            ).lower()
            if qlow not in blob:
                continue
        out.append(e)
    return out


def build_catalog_for_version(version: str) -> Dict[str, List[Dict[str, Any]]]:
    """Load Prismarine data once and return enriched rows per category (for UI caching)."""
    food_names = _food_name_set(version)
    items_raw = load_items(version)
    items = [enrich_item_row(i, version, food_names) for i in items_raw if isinstance(i, dict)]
    blocks = [enrich_block_row(b, version) for b in load_blocks(version) if isinstance(b, dict)]
    mobs = derive_mobs_from_items(items_raw, version)
    structures = [enrich_structure_row(s, version) for s in VANILLA_STRUCTURES]
    biomes = [enrich_biome_row(b, version) for b in VANILLA_BIOMES]
    enchants = [enrich_enchant_row(e, version) for e in load_enchantments(version) if isinstance(e, dict)]
    foods = [enrich_food_row(f, version) for f in load_foods(version) if isinstance(f, dict)]
    return {
        "items": items,
        "blocks": blocks,
        "mobs": mobs,
        "structures": structures,
        "biomes": biomes,
        "enchantments": enchants,
        "foods": foods,
    }
