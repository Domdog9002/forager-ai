from __future__ import annotations

from typing import Any, Dict, List


ROLE_KEYWORDS = {
    "performance": {"embeddium", "rubidium", "sodium", "ferrite", "entityculling", "memory", "fps", "spark"},
    "library": {"api", "lib", "cloth", "architectury", "geckolib", "curios", "patchouli", "framework"},
    "magic": {"ars", "magic", "spell", "mana", "irons", "occult", "botania", "apotheosis"},
    "tech": {"create", "thermal", "mekanism", "immersive", "industrial", "pipe", "machine"},
    "worldgen": {"biome", "world", "terra", "structure", "dungeon", "yung", "repurposed"},
    "utility": {"jei", "jade", "map", "inventory", "mouse", "configured", "search"},
    "visual": {"shader", "texture", "visual", "dynamic", "lights", "animation"},
}

CLIENT_HINTS = {"sodium", "embeddium", "rubidium", "oculus", "iris", "map", "minimap", "zoom", "tooltip", "jade"}
RISKY_HINTS = {"optifine", "coremod", "mixin", "rubidium", "oculus"}


def _text_for_mod(mod: Dict[str, Any]) -> str:
    fields = [
        mod.get("id"),
        mod.get("name"),
        mod.get("file_name"),
        mod.get("description"),
        " ".join(str(x) for x in mod.get("categories", []) if x),
    ]
    return " ".join(str(x or "").lower() for x in fields)


def classify_mod(mod: Dict[str, Any]) -> Dict[str, Any]:
    text = _text_for_mod(mod)
    roles: List[str] = []
    for role, needles in ROLE_KEYWORDS.items():
        if any(needle in text for needle in needles):
            roles.append(role)
    if not roles:
        roles.append("content")

    side = "client" if any(hint in text for hint in CLIENT_HINTS) else "both"
    risk = "medium" if any(hint in text for hint in RISKY_HINTS) else "low"
    if "performance" in roles and "optifine" not in text:
        risk = "low"
    return {
        "id": str(mod.get("id") or mod.get("mod_id") or mod.get("name") or "unknown"),
        "name": str(mod.get("name") or mod.get("id") or "Unknown Mod"),
        "roles": sorted(set(roles)),
        "side": side,
        "risk": risk,
        "reason": "Matched local metadata keywords." if roles != ["content"] else "No strong role keyword matched.",
    }


def classify_mods(mods: List[Dict[str, Any]], *, limit: int = 250) -> List[Dict[str, Any]]:
    return [classify_mod(mod) for mod in mods[:limit] if isinstance(mod, dict)]


def summarize_roles(classified: List[Dict[str, Any]]) -> Dict[str, Any]:
    counts: Dict[str, int] = {}
    risks: Dict[str, int] = {}
    for item in classified:
        for role in item.get("roles", []):
            counts[role] = counts.get(role, 0) + 1
        risk = str(item.get("risk") or "low")
        risks[risk] = risks.get(risk, 0) + 1
    return {"role_counts": dict(sorted(counts.items())), "risk_counts": dict(sorted(risks.items()))}
