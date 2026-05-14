"""
Capability matrix + unified instance rows for devkit / Gradle workflows.

This is a **supported-matrix** model: unknown combos fall back to guidance, not silent success.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from ..launcher.external_instances import ExternalInstanceInfo, discover_external_instances
from ..launcher.instance_manager import MinecraftInstance


def parse_mc_version(raw: str) -> Optional[Tuple[int, int, int]]:
    s = (raw or "").strip()
    m = re.match(r"^(\d+)\.(\d+)(?:\.(\d+))?", s)
    if not m:
        return None
    major = int(m.group(1))
    minor = int(m.group(2))
    patch = int(m.group(3) or 0)
    return major, minor, patch


def _norm_loader(loader: str) -> str:
    return (loader or "unknown").strip().lower()


def capability_for(
    *,
    minecraft_version: str,
    loader: str,
    loader_version: str = "",
) -> Dict[str, Any]:
    """
    Return JDK / toolchain guidance for a (MC version, loader) pair.

    ``tier``: ``supported`` (Forge-family MDK + JDK table), ``partial`` (best guess),
    ``unknown`` (user must confirm upstream docs).
    """
    lo = _norm_loader(loader)
    ver = parse_mc_version(minecraft_version)
    lv = (loader_version or "").strip()

    notes: List[str] = []
    tier = "partial"
    jdk = "17"
    devkit_kind = "forge_or_neoforge_mdk"
    gradle = "Use the official MDK / Forager (A) zip; run `gradlew` from that project root."

    if lo in ("fabric", "quilt"):
        devkit_kind = "fabric_loom"
        jdk = "17"
        tier = "partial"
        notes.append("Fabric / Quilt use **Gradle + Loom**, not the Forge MDK. Clone a Fabric example mod for that MC version.")
    elif lo == "vanilla":
        devkit_kind = "n_a"
        tier = "unknown"
        jdk = "match launcher"
        notes.append("Vanilla instances have no mod loader MDK. Use a modded template if you are bridging mods.")
    elif lo == "unknown":
        tier = "unknown"
        notes.append("Loader unknown — confirm in CurseForge / Modrinth / launcher UI, then pick matching MDK.")

    if ver:
        maj, mino, _pat = ver
        if maj >= 1 and mino >= 21:
            jdk = "21"
            tier = "partial"
            notes.append("Minecraft 1.21+ often targets **Java 21** for mod dev — verify your exact Forge/Neo/Fabric docs.")
        elif maj >= 1 and mino == 20:
            jdk = "17"
            if lo in ("forge", "neoforge", "unknown"):
                tier = "supported" if lo in ("forge", "neoforge") else tier
        elif maj >= 1 and 18 <= mino <= 19:
            jdk = "17"
            tier = "supported" if lo in ("forge", "neoforge") else tier
        elif maj >= 1 and mino == 17:
            jdk = "16 or 17"
            tier = "partial"
            notes.append("1.17.x modding: confirm whether your toolchain expects 16 or 17.")
        elif maj >= 1 and mino <= 16:
            jdk = "8 or 11"
            tier = "partial"
            notes.append("Older MC (≤1.16.x) often used **Java 8** (Forge) or **11** — check the MDK you use.")

    if lo == "neoforge":
        notes.append("NeoForge uses its own MDK/Gradle plugin set — do not assume Forge 47.x coordinates.")

    return {
        "tier": tier,
        "jdk_recommendation": jdk,
        "devkit_kind": devkit_kind,
        "gradle_note": gradle,
        "loader_resolved": lo,
        "loader_version": lv,
        "minecraft_version": minecraft_version,
        "notes": notes,
        "fallbacks": [
            "If Forager’s tier is partial/unknown, open the official MDK page for your **exact** MC + loader.",
            "Bind a **devkit folder** (contains `gradlew.bat`) per profile below; Forager only runs Gradle there.",
        ],
    }


def profile_key_forager(instance_name: str) -> str:
    return f"forager|{instance_name.strip()}"


def profile_key_external(info: ExternalInstanceInfo) -> str:
    return f"{info.source}|{info.stable_id}"


def widget_safe_key(profile_key: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", profile_key).strip("_")[:72] or "profile"


@dataclass(frozen=True)
class UnifiedInstanceRow:
    profile_key: str
    label: str
    source: str
    game_root: str
    minecraft_version: str
    loader: str
    loader_version: str


def build_unified_rows(*, instances: List[MinecraftInstance], config: Dict[str, Any]) -> List[UnifiedInstanceRow]:
    rows: List[UnifiedInstanceRow] = []
    for inst in instances:
        rows.append(
            UnifiedInstanceRow(
                profile_key=profile_key_forager(inst.name),
                label=inst.name,
                source="forager",
                game_root=str(inst.instance_path or "").strip(),
                minecraft_version=str(inst.minecraft_version or "unknown"),
                loader=str(inst.loader or "unknown"),
                loader_version=str(inst.loader_version or ""),
            )
        )
    for ext in discover_external_instances(config):
        rows.append(
            UnifiedInstanceRow(
                profile_key=profile_key_external(ext),
                label=ext.display_name,
                source=ext.source,
                game_root=str(ext.game_root or "").strip(),
                minecraft_version=str(ext.minecraft_version or "unknown"),
                loader=str(ext.loader or "unknown"),
                loader_version=str(ext.loader_version or ""),
            )
        )
    return rows


def merge_devkit_binding(existing: Dict[str, Any], profile_key: str, devkit_root: str) -> Dict[str, Any]:
    out = dict(existing or {})
    root = (devkit_root or "").strip()
    if root:
        entry = dict(out.get(profile_key) or {})
        entry["devkit_root"] = root
        out[profile_key] = entry
    elif profile_key in out:
        ent = dict(out[profile_key])
        ent.pop("devkit_root", None)
        if ent:
            out[profile_key] = ent
        else:
            del out[profile_key]
    return out
