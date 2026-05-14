"""Sample jars for declared Minecraft ranges / Fabric environment hints."""

from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional


def _read_zip_text(z: zipfile.ZipFile, names: tuple[str, ...]) -> Optional[str]:
    for n in names:
        try:
            return z.read(n).decode("utf-8", errors="replace")
        except KeyError:
            continue
        except OSError:
            continue
    return None


def _fabric_mc_depends(raw: str) -> List[str]:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(data, dict):
        return []
    dep = data.get("depends")
    if not isinstance(dep, dict):
        return []
    mc = dep.get("minecraft")
    if isinstance(mc, str) and mc.strip():
        return [mc.strip()]
    if isinstance(mc, dict):
        ver = mc.get("version")
        if isinstance(ver, str) and ver.strip():
            return [ver.strip()]
    return []


def _forge_toml_mc_ranges(raw: str) -> List[str]:
    out: List[str] = []
    for m in re.finditer(
        r"(?im)(?:versionRange|minecraftVersionRange|version)\s*=\s*\"([^\"]+)\"",
        raw,
    ):
        g = m.group(1).strip()
        if g and g not in out:
            out.append(g)
    return out[:6]


def _fabric_env(raw: str) -> str:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return ""
    if not isinstance(data, dict):
        return ""
    env = data.get("environment")
    if isinstance(env, str) and env.strip():
        return env.strip().lower()
    return ""


def audit_jar_version_and_env(
    pack_root: str,
    effective_mc: str,
    *,
    max_jars: int = 48,
) -> Dict[str, Any]:
    """
    Sample ``mods/*.jar`` for Fabric/Quilt ``depends.minecraft`` and Forge ``mods.toml`` ranges.

    ``matches`` is best-effort: true when the effective MC string appears in any declared range text.
    """
    root = Path(str(pack_root or "").strip())
    mods = root / "mods"
    if not mods.is_dir():
        return {
            "sampled_jars": 0,
            "unknown_ratio": 1.0,
            "mismatch_count": 0,
            "notes": [],
            "client_only": 0,
            "server_only": 0,
            "env_unknown": 0,
            "dual_env_scan": False,
        }

    jars = sorted([p for p in mods.glob("*.jar") if p.is_file()])[:max_jars]
    mc_eff = str(effective_mc or "").strip()
    notes: List[str] = []
    mismatches = 0
    unknown = 0
    client_only = 0
    server_only = 0
    env_unknown = 0
    sampled = 0

    for jp in jars:
        sampled += 1
        decls: List[str] = []
        env_hit = ""
        raw_fab: Optional[str] = None
        try:
            with zipfile.ZipFile(jp, "r") as z:
                raw_fab = _read_zip_text(z, ("fabric.mod.json", "quilt.mod.json"))
                if raw_fab:
                    decls.extend(_fabric_mc_depends(raw_fab))
                    env_hit = _fabric_env(raw_fab)
                raw_toml = _read_zip_text(z, ("META-INF/neoforge.mods.toml", "META-INF/mods.toml"))
                if raw_toml:
                    decls.extend(_forge_toml_mc_ranges(raw_toml))
        except (zipfile.BadZipFile, OSError):
            unknown += 1
            continue

        if env_hit == "client":
            client_only += 1
        elif env_hit == "server":
            server_only += 1
        elif raw_fab:
            env_unknown += 1

        if not decls:
            unknown += 1
            continue
        joined = " | ".join(decls)
        ok = bool(mc_eff) and any(mc_eff in d for d in decls)
        if not ok and mc_eff:
            loose = mc_eff in joined
            ok = loose
        if mc_eff and not ok:
            mismatches += 1
            if len(notes) < 8:
                notes.append(f"{jp.name}: declared `{joined[:120]}` vs effective `{mc_eff}`")

    denom = max(1, sampled)
    unknown_ratio = min(1.0, unknown / denom)
    return {
        "sampled_jars": sampled,
        "unknown_ratio": round(unknown_ratio, 3),
        "mismatch_count": mismatches,
        "notes": notes,
        "client_only": client_only,
        "server_only": server_only,
        "env_unknown": env_unknown,
        "dual_env_scan": False,
    }
