from __future__ import annotations

import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.backend.conflict_resolver import ConflictResolver, ModCompatibility
from forager_ai.backend.conflict_scan import (
    build_install_preflight_report,
    build_conflict_scan_report,
    collect_pack_mods,
    decide_preflight,
    mod_info_from_jar,
    mod_info_from_manifest_entry,
)
from forager_ai.launcher.jar_mod_metadata import read_jar_mod_metadata
from forager_ai.pack.compat_registry import add_compat_rule
from forager_ai.pack.manifest import init_pack_manifest, load_pack_manifest, register_compat_in_manifest
from forager_ai.analysis.mod_graph import build_graph, to_graphviz_dot


class ConflictScanTests(unittest.TestCase):
    def test_decide_preflight_defensive_when_counts_missing_but_conflicts_reported(self) -> None:
        out = decide_preflight(
            {
                "total_conflicts": 3,
                "highest_severity": "high",
                "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 0},
            }
        )
        self.assertEqual(out["decision"], "warn")

    def test_decide_preflight_defensive_blocks_on_critical_highest_when_counts_empty(self) -> None:
        out = decide_preflight(
            {
                "total_conflicts": 1,
                "highest_severity": "critical",
                "severity_counts": {},
            }
        )
        self.assertEqual(out["decision"], "block")

    def test_decide_preflight_allow_when_low_only_in_severity_counts(self) -> None:
        out = decide_preflight(
            {
                "total_conflicts": 2,
                "highest_severity": "low",
                "severity_counts": {"critical": 0, "high": 0, "medium": 0, "low": 2},
            }
        )
        self.assertEqual(out["decision"], "allow")

    def test_manifest_entry_normalizes_common_fields(self) -> None:
        mod = mod_info_from_manifest_entry(
            {
                "display_name": "Create",
                "mod_id": "create",
                "dependencies": [{"id": "flywheel"}],
                "minecraft_version": "1.20.1",
                "loader": "forge",
                "tags": ["technology"],
            }
        )

        self.assertIsNotNone(mod)
        assert mod is not None
        self.assertEqual(mod.id, "create")
        self.assertEqual(mod.name, "Create")
        self.assertEqual(mod.dependencies, ["flywheel"])
        self.assertEqual(mod.minecraft_versions, ["1.20.1"])
        self.assertEqual(mod.loaders, ["forge"])

    def test_collect_pack_mods_uses_manifest_defaults(self) -> None:
        manifest = {
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "mods": [{"name": "Ars Nouveau", "id": "ars_nouveau"}],
        }

        with tempfile.TemporaryDirectory() as tmp:
            mods = collect_pack_mods(manifest, tmp)

        self.assertEqual(len(mods), 1)
        self.assertEqual(mods[0].minecraft_versions, ["1.20.1"])
        self.assertEqual(mods[0].loaders, ["forge"])

    def test_report_detects_missing_dependency_and_version_conflict(self) -> None:
        manifest = {
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "mods": [
                {
                    "name": "Create",
                    "id": "create",
                    "dependencies": ["flywheel"],
                    "minecraft_versions": ["1.20.1"],
                },
                {
                    "name": "Magic Tools",
                    "id": "magic_tools",
                    "minecraft_versions": ["1.19.2"],
                },
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            resolver = ConflictResolver(tmp)
            report = build_conflict_scan_report(
                resolver=resolver,
                manifest=manifest,
                pack_root=tmp,
                pack_name="test-pack",
            )

        conflict_types = {item["type"] for item in report["conflicts"]}
        self.assertIn("missing_dependency", conflict_types)
        self.assertIn("incompatible_versions", conflict_types)
        self.assertEqual(report["summary"]["mods_scanned"], 2)
        self.assertGreaterEqual(report["summary"]["total_conflicts"], 2)
        self.assertEqual(report["council_artifact"]["artifact_type"], "forager_conflict_scan")

    def test_report_detects_known_incompatibility_and_duplicate_names(self) -> None:
        manifest = {
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "mods": [
                {"name": "OptiFine", "id": "optifine"},
                {"name": "Optifine", "id": "optifine_alt"},
                {"name": "Embeddium", "id": "embeddium"},
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            resolver = ConflictResolver(tmp)
            resolver.compatibility_data["optifine"] = ModCompatibility(
                mod_id="optifine",
                compatible_with=[],
                incompatible_with=["embeddium"],
                requires=[],
                conflicts_with=[],
                performance_impact="medium",
                stability_rating=0.5,
                last_updated="test",
            )
            report = build_conflict_scan_report(
                resolver=resolver,
                manifest=manifest,
                pack_root=tmp,
                pack_name="test-pack",
            )

        conflict_types = {item["type"] for item in report["conflicts"]}
        self.assertIn("known_incompatibility", conflict_types)
        self.assertIn("duplicate_content", conflict_types)
        self.assertGreaterEqual(report["summary"]["auto_resolvable"], 1)

    def test_preflight_warns_for_known_pair_candidate(self) -> None:
        manifest = {
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "mods": [{"name": "Create", "id": "create"}],
        }
        candidate = mod_info_from_manifest_entry(
            {
                "name": "Ars Nouveau",
                "id": "ars_nouveau",
                "minecraft_versions": ["1.20.1"],
                "loaders": ["forge"],
            }
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None

        with tempfile.TemporaryDirectory() as tmp:
            resolver = ConflictResolver(tmp)
            report = build_install_preflight_report(
                resolver=resolver,
                manifest=manifest,
                pack_root=tmp,
                pack_name="test-pack",
                candidate=candidate,
            )

        self.assertEqual(report["decision"], "warn")
        self.assertEqual(report["summary"]["mods_scanned"], 2)
        self.assertTrue(any(item["id"] == "known_pair_create_ars_nouveau" for item in report["conflicts"]))

    def test_preflight_blocks_for_non_matching_minecraft_version(self) -> None:
        manifest = {
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "mods": [{"name": "Create", "id": "create", "minecraft_versions": ["1.20.1"]}],
        }
        candidate = mod_info_from_manifest_entry(
            {
                "name": "Old Magic",
                "id": "old_magic",
                "minecraft_versions": ["1.19.2"],
                "loaders": ["forge"],
            }
        )
        self.assertIsNotNone(candidate)
        assert candidate is not None

        with tempfile.TemporaryDirectory() as tmp:
            resolver = ConflictResolver(tmp)
            report = build_install_preflight_report(
                resolver=resolver,
                manifest=manifest,
                pack_root=tmp,
                pack_name="test-pack",
                candidate=candidate,
            )

        self.assertEqual(report["decision"], "block")
        self.assertEqual(report["summary"]["highest_severity"], "critical")

    def test_compat_rule_is_registered_in_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            init_pack_manifest(tmp, pack_id="test-pack")
            added = add_compat_rule(
                tmp,
                rule_name="Create Ars Progression",
                affected_mods=["create", "ars_nouveau"],
                description="Review progression gates.",
                source="test",
            )
            register_compat_in_manifest(
                tmp,
                rule_id=added["rule_id"],
                rule_name=added["rule_name"],
                affected_mods=added["affected_mods"],
                description=added["description"],
            )
            manifest = load_pack_manifest(tmp)

        self.assertEqual(len(manifest["compats"]), 1)
        self.assertEqual(manifest["compats"][0]["rule_id"], "create_ars_progression")

    def test_pack_health_graph_dot_escapes_and_uses_dark_theme(self) -> None:
        manifest = {
            "mods": [{"id": "create"}, {"id": "ars_nouveau"}],
            "compats": [
                {
                    "affected_mods": ["create", "ars_nouveau"],
                    "rule_name": 'balance "curve" v2',
                }
            ],
        }
        dot = to_graphviz_dot(build_graph(manifest))
        self.assertIn('bgcolor="#111827"', dot)
        self.assertIn('\\"', dot)

    def test_read_jar_prefers_mods_toml_over_fabric_mod_json(self) -> None:
        """Hybrid jars often ship fabric.mod.json stubs; Forge metadata must win for Pack Health."""
        toml = '''[[mods]]
modId = "ambient_sounds"
version = "5.0.0"
displayName = "AmbientSounds"
'''
        fabric = '{"id": "fabric_stub", "name": "Stub", "version": "1.0.0"}'
        with tempfile.TemporaryDirectory() as tmp:
            jar = Path(tmp) / "AmbientSounds.jar"
            with zipfile.ZipFile(jar, "w") as z:
                z.writestr("META-INF/mods.toml", toml)
                z.writestr("fabric.mod.json", fabric)
            meta = read_jar_mod_metadata(str(jar))
            self.assertEqual(meta.get("loader_kind"), "forge")
            self.assertEqual(str(meta.get("mod_id") or "").strip(), "ambient_sounds")
            info = mod_info_from_jar(jar, default_minecraft_version="1.20.1", default_loader="forge")
            self.assertEqual(info.loaders, ["forge"])
            self.assertEqual(info.id, "ambient_sounds")

    def test_mc_guardrail_uses_pack_manifest_version(self) -> None:
        """Resolver must compare advertised MC versions to the active pack profile, not a hardcoded 1.20.1."""
        manifest = {
            "minecraft_version": "1.21.1",
            "loader": "forge",
            "mods": [
                {
                    "name": "Example",
                    "id": "example",
                    "minecraft_versions": ["1.21.1"],
                    "loaders": ["forge"],
                }
            ],
        }
        with tempfile.TemporaryDirectory() as tmp:
            resolver = ConflictResolver(tmp)
            report = build_conflict_scan_report(
                resolver=resolver,
                manifest=manifest,
                pack_root=tmp,
                pack_name="mc-test",
            )
        mc_ids = {c["id"] for c in report["conflicts"] if c["id"].startswith("mc_version_guardrail_")}
        self.assertEqual(mc_ids, set())

    def test_pack_health_graph_merges_scan_conflicts(self) -> None:
        manifest: dict = {"mods": [], "compats": []}
        scan_mods = [
            {"id": "mod_a", "dependencies": []},
            {"id": "mod_b", "dependencies": ["mod_a"]},
        ]
        scan_conflicts = [
            {
                "id": "c1",
                "type": "incompatible_versions",
                "severity": "high",
                "affected_mods": ["mod_a", "mod_b"],
                "description": "test",
                "suggested_resolution": "x",
                "auto_resolvable": False,
                "resolution_actions": [],
            }
        ]
        g = build_graph(manifest, scan_mods=scan_mods, scan_conflicts=scan_conflicts, max_render_nodes=80)
        self.assertIn("mod_a", g["nodes"])
        self.assertIn("mod_b", g["nodes"])
        rels = {e["relation"] for e in g["edges"]}
        self.assertIn("depends_on", rels)
        self.assertIn("scan_finding", rels)
        dot = to_graphviz_dot(g)
        self.assertIn("scan:", dot)


if __name__ == "__main__":
    unittest.main()
