from __future__ import annotations

import os
from typing import Any, Dict, List


PILLAR_MODS = {
    "create": "tech",
    "ars_nouveau": "magic",
    "irons_spellbooks": "combat_magic",
    "origins": "character_builds",
}


def _manifest_mod_ids(manifest: Dict[str, Any]) -> set[str]:
    out: set[str] = set()
    for mod in manifest.get("mods") or []:
        if isinstance(mod, dict):
            raw = mod.get("id") or mod.get("mod_id") or mod.get("slug") or mod.get("name")
            if raw:
                out.add(str(raw).strip().lower().replace("-", "_").replace(" ", "_"))
    return out


def _count_script_files(pack_root: str) -> int:
    count = 0
    for rel_root in ("kubejs", "scripts", "datapacks"):
        root = os.path.join(pack_root, rel_root)
        if not os.path.isdir(root):
            continue
        for _, _, files in os.walk(root):
            count += sum(1 for name in files if name.lower().endswith((".js", ".zs", ".json", ".mcfunction")))
    return count


def audit_progression(
    *,
    manifest: Dict[str, Any],
    pack_root: str,
    compat_rules: List[Dict[str, Any]],
) -> Dict[str, Any]:
    mod_ids = _manifest_mod_ids(manifest)
    active_pillars = {mod_id: pillar for mod_id, pillar in PILLAR_MODS.items() if mod_id in mod_ids}
    findings: List[Dict[str, Any]] = []
    recommendations: List[str] = []

    if {"create", "ars_nouveau"}.issubset(active_pillars):
        findings.append(
            {
                "severity": "medium",
                "id": "create_ars_progression",
                "message": "Create automation and Ars Nouveau magic can skip each other without recipe/config gates.",
            }
        )
        recommendations.append("Add a staged compat rule that ties early mana automation to Create brass progression.")

    if {"irons_spellbooks", "origins"}.issubset(active_pillars):
        findings.append(
            {
                "severity": "medium",
                "id": "combat_origin_scaling",
                "message": "Origin powers plus Iron's Spells can create early combat spikes.",
            }
        )
        recommendations.append("Review early spell availability and origin damage/mobility bonuses.")

    scripts_count = _count_script_files(pack_root)
    if active_pillars and scripts_count == 0:
        findings.append(
            {
                "severity": "low",
                "id": "no_progression_scripts",
                "message": "Major progression pillars are present but no scripts/datapacks were found.",
            }
        )
        recommendations.append("Add a guide or recipe/data script layer before release.")

    if findings and not compat_rules:
        recommendations.append("Persist reviewed progression findings as compat rules so future scans remember them.")

    return {
        "active_pillars": active_pillars,
        "script_files": scripts_count,
        "findings": findings,
        "recommendations": recommendations,
    }
