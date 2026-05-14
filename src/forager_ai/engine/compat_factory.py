"""
Bounded "compat factory" outputs: (B) datapack + KubeJS starter layer, (A) Forge mod scaffold zip.

These are intentional scaffolds + checklists — not guaranteed in-game compatibility.
"""

from __future__ import annotations

import io
import json
import re
import zipfile
from typing import Dict, Optional, Tuple

from .gradle_bundle import (
    gradle_wrapper_jar_bytes,
    gradlew_bat_text,
    gradlew_sh_text,
    wrapper_properties_text,
)


def slug_token(raw: str, *, max_len: int = 40) -> str:
    s = (raw or "").strip().lower()
    s = re.sub(r"[^a-z0-9_-]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    if not s:
        s = "unnamed"
    return s[:max_len]


def java_package_segment(raw: str) -> str:
    """One segment of a Java package (no dots)."""
    s = slug_token(raw, max_len=30).replace("-", "_")
    if s[0].isdigit():
        s = "m_" + s
    return s


def build_datapack_kubejs_layer(
    *,
    source_mod_label: str,
    target_framework: str,
    optional_partner_mod: str,
    minecraft_version: str,
    datapack_namespace: str,
) -> Dict[str, str]:
    """
    (B) Files relative to **pack root** when extracted: ``datapacks/<pack>/`` and ``kubejs/``.
    """
    ns = slug_token(datapack_namespace, max_len=24).replace("-", "_")
    if ns[0].isdigit():
        ns = "f_" + ns
    pack_dir = f"datapacks/forager_compat_{ns}"

    sm = source_mod_label.strip() or "unknown_source"
    tf = target_framework.strip() or "target_framework"
    pm = (optional_partner_mod or "").strip()
    mc = minecraft_version.strip() or "1.20.1"

    pack_mcmeta = {
        "pack": {"pack_format": 15, "description": f"Forager compat layer — {sm} ↔ {tf} (MC {mc}). Review before ship."}
    }

    # Placeholder tag files users can fill with real item ids (1.20 JSON tag format).
    tag_stub = {"replace": False, "values": []}

    files: Dict[str, str] = {}
    files[f"{pack_dir}/pack.mcmeta"] = json.dumps(pack_mcmeta, indent=2) + "\n"
    files[f"{pack_dir}/data/{ns}/tags/items/forager_compat_weapon_candidates.json"] = json.dumps(tag_stub, indent=2) + "\n"
    files[f"{pack_dir}/data/{ns}/tags/items/forager_compat_blacklist.json"] = json.dumps(tag_stub, indent=2) + "\n"
    files[f"{pack_dir}/README_FORAGER.txt"] = (
        f"Forager compat factory — datapack (B)\n"
        f"=====================================\n"
        f"Source mod / content: {sm}\n"
        f"Target framework (e.g. combat/stances): {tf}\n"
        f"Optional second mod: {pm or '(none)'}\n"
        f"Minecraft: {mc}\n\n"
        "Next steps:\n"
        "1) Replace empty tag files with real item ids (use `/give` creative tabs or `/kubejs hand` if available).\n"
        "2) Wire tags into framework-specific datapacks or delegate to KubeJS in (B) kubejs stubs.\n"
        "3) Load in a test world; fix errors before shipping.\n"
    )

    files["kubejs/README_FORAGER_COMPAT.txt"] = (
        "Forager compat factory — KubeJS (B)\n"
        "==================================\n"
        "Edit `startup_scripts/forager_compat_stub.js`.\n"
        "Use ItemEvents, tags, or your framework's documented registration hooks.\n"
        "Never trust generated JS until you verify in-game.\n"
    )
    files["kubejs/startup_scripts/forager_compat_stub.js"] = (
        "// Forager generated stub — MC "
        + mc
        + "\n"
        + f"// Intent: bridge `{sm}` items toward `{tf}`"
        + (f" (with `{pm}`)" if pm else "")
        + "\n\n"
        "console.info('[Forager compat stub] loaded — replace with real logic');\n\n"
        "// Example patterns (uncomment and adapt):\n"
        "// ItemEvents.modification(event => { ... });\n"
        "// ServerEvents.tags('item', event => { ... });\n"
    )

    return files


def build_forge_compat_mod_scaffold(
    *,
    mod_id: str,
    source_mod_label: str,
    target_framework: str,
    minecraft_version: str,
    forge_version: str,
) -> Dict[str, str]:
    """
    (A) Standalone Gradle project tree (extract outside the pack, open in IDE).
    """
    mid = slug_token(mod_id, max_len=32).replace("-", "_")
    if mid[0].isdigit():
        mid = "mod_" + mid
    sm = source_mod_label.strip() or "source"
    tf = target_framework.strip() or "target"
    mc = minecraft_version.strip() or "1.20.1"
    fg = forge_version.strip() or "47.2.0"
    pkg = f"com.forager.compat.{java_package_segment(mid)}"
    pkg_path = pkg.replace(".", "/")

    mods_toml = f'''modLoader="javafml"
loaderVersion="[47,)"

license="All Rights Reserved"

[[mods]]
modId="{mid}"
version="0.1.0"
displayName="Forager Compat — {mid}"
authors="Forager AI (scaffold)"
description="""
Generated compatibility scaffold.
Source focus: {sm}
Target: {tf}
Replace this description and add real code + mixins only after review.
"""

[[dependencies.{mid}]]
    modId="forge"
    mandatory=true
    versionRange="[47,)"

[[dependencies.{mid}]]
    modId="minecraft"
    mandatory=true
    versionRange="[{mc}]"
'''

    java_main = f"""package {pkg};

import net.minecraftforge.fml.common.Mod;

/**
 * Empty entry — add registration / event bus subscribers / mixins after design.
 * Target: {tf} · context: {sm} · MC {mc}
 */
@Mod("{mid}")
public final class {java_class_name(mid)} {{
    public static final String MOD_ID = "{mid}";

    public {java_class_name(mid)}() {{
        // TODO: compat wiring — register configs, events, or capability hooks here.
    }}
}}
"""

    gradle_props = f"""org.gradle.jvmargs=-Xmx3G
org.gradle.daemon=false
"""

    # Keep Gradle self-contained: literal MC/Forge coordinates from the wizard (no fragile token expand).
    build_gradle = f"""plugins {{
    id 'eclipse'
    id 'idea'
    id 'maven-publish'
    id 'net.minecraftforge.gradle' version '[6.0,6.2)'
}}

version = '0.1.0'
group = 'com.forager.compat'

base {{
    archivesName = '{mid}'
}}

java.toolchain.languageVersion = JavaLanguageVersion.of(17)

minecraft {{
    mappings channel: 'official', version: '{mc}'
    copyIdeResources = true

    runs {{
        configureEach {{
            workingDirectory project.file('run')
            property 'forge.logging.markers', 'REGISTRIES'
            property 'forge.logging.console.level', 'debug'
            mods {{
                '{mid}' {{
                    source sourceSets.main
                }}
            }}
        }}
        client {{ }}
        server {{
            args '--nogui'
        }}
    }}
}}

repositories {{ }}

dependencies {{
    minecraft 'net.minecraftforge:forge:{mc}-{fg}'
}}

// Optional: enable Mixins after you add SpongePowered repository + processor (see Forge MDK docs).
// repositories {{ maven {{ url = 'https://repo.spongepowered.org/repository/maven-public/' }} }}
// dependencies {{
//     annotationProcessor 'org.spongepowered:mixin:0.8.5:processor'
//     implementation 'org.spongepowered:mixin:0.8.5'
// }}

tasks.withType(JavaCompile).configureEach {{
    options.encoding = 'UTF-8'
}}
"""

    settings_gradle = f"rootProject.name = '{mid}'\n"

    java_client = f"""package {pkg}.client;

import net.minecraftforge.api.distmarker.Dist;
import net.minecraftforge.event.TickEvent;
import net.minecraftforge.eventbus.api.SubscribeEvent;
import net.minecraftforge.fml.common.Mod;

@Mod.EventBusSubscriber(modid = "{mid}", bus = Mod.EventBusSubscriber.Bus.FORGE, value = Dist.CLIENT)
public final class ForagerCompatClientHooks {{
    @SubscribeEvent
    public static void onClientTick(final TickEvent.ClientTickEvent event) {{
        if (event.phase != TickEvent.Phase.END) {{
            return;
        }}
        // Client-only hooks (HUD, keybinds, safe caches). Keep logic minimal.
    }}
}}
"""

    mixins_doc = {
        "required": True,
        "minVersion": "0.8",
        "package": f"{pkg}.mixin",
        "compatibilityLevel": "JAVA_17",
        "mixins": [],
        "client": [],
        "server": [],
    }
    mixins_json = json.dumps(mixins_doc, indent=2) + "\n"

    package_info = (
        f"/** Mixin package for `{mid}` — add targeted patches only after design review. */\n"
        f"package {pkg}.mixin;\n"
    )

    readme = f"""# Forager compat mod scaffold (A)

**Not a finished compatibility mod.** This is a Forge {mc} starter you build on.

## Intent
- **Source / problem mod (label):** {sm}
- **Target framework:** {tf}

## Gradle wrapper
This zip includes **Gradle 8.4** wrapper scripts and (when bundled) `gradle-wrapper.jar` from Forager’s `engine/data/`.
Extract and run `gradlew.bat build` (Windows) or `./gradlew build` (Unix) from the project root.

## Next steps
1. Add your real dependencies in `build.gradle` (CurseMaven / Modrinth Maven / local jars).
2. Implement small, testable changes (events, tags, optional Mixins with care).
3. Run `gradlew runClient` and fix until stable.
4. Publish only after license and attribution review.

Generated by Forager AI compat factory.
"""

    files: Dict[str, str] = {}
    files["gradle.properties"] = gradle_props
    files["settings.gradle"] = settings_gradle
    files["build.gradle"] = build_gradle
    files["src/main/resources/META-INF/mods.toml"] = mods_toml
    files[f"src/main/java/{pkg_path}/{java_class_name(mid)}.java"] = java_main
    files[f"src/main/java/{pkg_path}/client/ForagerCompatClientHooks.java"] = java_client
    files[f"src/main/java/{pkg_path}/mixin/package-info.java"] = package_info
    files[f"src/main/resources/{mid}.mixins.json"] = mixins_json
    files["src/main/resources/META-INF/accesstransformer.cfg"] = (
        "# Optional Forge access transformers — one fully-qualified rule per line when needed.\n"
    )
    files["docs/API_RESEARCH_TEMPLATE.md"] = (
        f"# API research: {sm} ↔ {tf}\n\n"
        "## Checklist\n"
        "- [ ] Modrinth + CurseForge project pages (issues, source, loaders).\n"
        "- [ ] Minimal repro instance (two mods + deps + this bridge).\n"
        "- [ ] Public API / events first; Mixins only when unavoidable.\n\n"
        f"- Mod id: `{mid}` · base package: `{pkg}`\n"
    )
    files["README.md"] = readme
    files[".gitignore"] = (
        "run/\n.gradle/\nbuild/\nout/\n.idea/\n*.iml\n.classpath\n.project\n.settings/\nbin/\n"
    )

    try:
        files["gradlew.bat"] = gradlew_bat_text()
        files["gradlew"] = gradlew_sh_text()
        files["gradle/wrapper/gradle-wrapper.properties"] = wrapper_properties_text()
    except OSError:
        pass
    except FileNotFoundError:
        pass

    return files


def java_class_name(mod_id: str) -> str:
    base = slug_token(mod_id, max_len=24).replace("-", "_")
    parts = base.split("_")
    return "".join(p[:1].upper() + p[1:] for p in parts if p) or "CompatMod"


def zip_text_files(files: Dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, content in files.items():
            rel_norm = rel.replace("\\", "/").lstrip("/")
            zi = zipfile.ZipInfo(rel_norm)
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, content.encode("utf-8"))
    return buf.getvalue()


def zip_mixed_project(text_files: Dict[str, str], binary_files: Optional[Dict[str, bytes]] = None) -> bytes:
    """Zip UTF-8 text paths plus optional binary blobs (e.g. ``gradle-wrapper.jar``)."""
    binary_files = binary_files or {}
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel, content in text_files.items():
            rel_norm = rel.replace("\\", "/").lstrip("/")
            zi = zipfile.ZipInfo(rel_norm)
            zi.external_attr = 0o644 << 16
            zf.writestr(zi, content.encode("utf-8"))
        for rel, raw in binary_files.items():
            rel_norm = rel.replace("\\", "/").lstrip("/")
            zi = zipfile.ZipInfo(rel_norm)
            if rel_norm == "gradlew" or rel_norm.endswith("/gradlew"):
                zi.external_attr = 0o755 << 16
            else:
                zi.external_attr = 0o644 << 16
            zf.writestr(zi, raw)
    return buf.getvalue()


def build_combined_compat_factory_zips(
    *,
    source_mod_label: str,
    target_framework: str,
    optional_partner_mod: str,
    minecraft_version: str,
    forge_version: str,
    datapack_namespace: str,
    java_mod_id: str,
) -> Tuple[bytes, bytes, str, str]:
    """
    Returns (zip_b_layer, zip_a_scaffold, suggested_b_name, suggested_a_name).
    """
    a_slug = slug_token(source_mod_label, max_len=20)
    b_slug = slug_token(target_framework, max_len=20)
    b_files = build_datapack_kubejs_layer(
        source_mod_label=source_mod_label,
        target_framework=target_framework,
        optional_partner_mod=optional_partner_mod,
        minecraft_version=minecraft_version,
        datapack_namespace=datapack_namespace,
    )
    a_files = build_forge_compat_mod_scaffold(
        mod_id=java_mod_id,
        source_mod_label=source_mod_label,
        target_framework=target_framework,
        minecraft_version=minecraft_version,
        forge_version=forge_version,
    )
    b_name = f"forager_compat_layer_{a_slug}_{b_slug}.zip"
    a_name = f"forager_compat_mod_scaffold_{slug_token(java_mod_id, max_len=24)}.zip"
    a_bin: Dict[str, bytes] = {}
    jar = gradle_wrapper_jar_bytes()
    if jar:
        a_bin["gradle/wrapper/gradle-wrapper.jar"] = jar
    return zip_text_files(b_files), zip_mixed_project(a_files, a_bin), b_name, a_name
