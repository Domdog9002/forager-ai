from __future__ import annotations

from typing import Any, Dict, List, Set

_THEME_PATTERNS: List[tuple[str, List[str]]] = [
    ("theme:fantasy", ["magic", "spell", "mage", "dragon", "dungeon", "orc", "elf", "fey", "rune", "enchant", "mana"]),
    ("theme:sci_fi", ["tech", "laser", "machine", "robot", "space", "cyber", "circuit", "nano", "plasma", "railgun"]),
    ("theme:adventure", ["ruin", "explore", "temple", "quest", "camp", "waystone", "map", "ancient_city"]),
    ("theme:horror", ["blood", "void", "curse", "dark", "sculk", "phantom", "undead"]),
]

_WEAPON_CLASSES: List[tuple[str, List[str]]] = [
    ("weapon:longsword", ["longsword", "greatsword", "claymore", "zweihander", "great_blade"]),
    ("weapon:mace", ["mace", "hammer", "flail", "war_hammer", "morning_star"]),
    ("weapon:dagger", ["dagger", "knife", "stiletto"]),
    ("weapon:spear", ["spear", "lance", "halberd", "pike", "glaive"]),
    ("weapon:bow", ["bow", "crossbow", "longbow"]),
    ("weapon:staff", ["staff", "scepter", "wand"]),
    ("weapon:gun", ["gun", "rifle", "pistol", "blaster"]),
    ("weapon:legendary", ["legendary", "mythic", "divine", "ancient", "primal", "artifact"]),
    ("weapon:unique", ["unique", "one_of", "singular", "covenant"]),
]

_MOB_ARCHETYPES: List[tuple[str, List[str]]] = [
    ("mob:flying", ["bat", "bee", "phantom", "vex", "wasp", "dragon", "fly"]),
    ("mob:undead", ["zombie", "skeleton", "phantom", "lich", "wraith", "ghost"]),
    ("mob:aquatic", ["fish", "guardian", "squid", "drowned", "trident"]),
    ("mob:construct", ["golem", "automaton", "drone"]),
]

_TIER_KEYWORDS: List[tuple[str, List[str]]] = [
    ("tier:early", ["wood", "stone", "leather", "copper", "flint", "tier_1", "starter"]),
    ("tier:mid", ["iron", "steel", "gold", "tier_2", "tier_3", "advanced"]),
    ("tier:late", ["diamond", "netherite", "obsidian", "tier_4", "elite"]),
    ("tier:endgame", ["nether_star", "dragon", "wither", "creative", "ultimate", "chaotic", "infinity"]),
]


def _match_patterns(blob: str, patterns: List[tuple[str, List[str]]]) -> Set[str]:
    hit: Set[str] = set()
    for tag, keys in patterns:
        if any(k in blob for k in keys):
            hit.add(tag)
    return hit


def _entry_blob(entry: Dict[str, Any]) -> str:
    parts = [str(entry.get("id", "")), str(entry.get("mod_id", ""))]
    dn = entry.get("displayName")
    if dn:
        parts.append(str(dn))
    return " ".join(parts).lower()


def infer_progression_tier(entry: Dict[str, Any]) -> str:
    blob = _entry_blob(entry)
    tiers = _match_patterns(blob, _TIER_KEYWORDS)
    if "tier:endgame" in tiers:
        return "endgame"
    if "tier:late" in tiers:
        return "late"
    if "tier:mid" in tiers:
        return "mid"
    if "tier:early" in tiers:
        return "early"
    et = entry.get("type", "")
    if et == "structure":
        return "mid"
    if et == "mob" and any(b in blob for b in ("boss", "dragon", "wither", "warden", "guardian")):
        return "late"
    return "unknown"


def classify_entry(entry: Dict[str, Any]) -> Dict[str, Any]:
    blob = _entry_blob(entry)
    tags: Set[str] = set()

    tags |= _match_patterns(blob, _THEME_PATTERNS)
    tags |= _match_patterns(blob, _MOB_ARCHETYPES)

    et = entry.get("type", "")
    if et == "item":
        tags |= _match_patterns(blob, _WEAPON_CLASSES)

    if et == "mob":
        if any(b in blob for b in ("boss", "dragon", "wither", "warden", "raid", "elder_guardian")):
            tags.add("role:boss")
        tags |= _match_patterns(blob, _MOB_ARCHETYPES)

    if et in ("structure", "structure_set"):
        tags.add("world:structure")

    tier = infer_progression_tier({**entry, "type": et})
    entry["progression_tier"] = tier
    entry["taxonomy_tags"] = sorted(tags)
    return entry


def enrich_catalog(entries: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [classify_entry(dict(e)) for e in entries]


def tags_union(entries: List[Dict[str, Any]]) -> List[str]:
    s: Set[str] = set()
    for e in entries:
        for t in e.get("taxonomy_tags", []):
            s.add(t)
        if e.get("progression_tier"):
            s.add(f"tier:{e['progression_tier']}")
    return sorted(s)
