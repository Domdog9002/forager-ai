from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.mods.mod_foundry import (
    append_draft,
    append_mini_change,
    build_foundry_artifact,
    evaluate_quality_gates,
    extract_asset_requests,
    feature_plan_from_bundle,
    load_project,
    maybe_run_continuous_review,
    save_project,
    scaffold_compiled_forge_project,
    texture_blueprint_from_assets,
)


class ModFoundryTests(unittest.TestCase):
    def test_project_persistence_drafts_and_mini_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = load_project(tmp)
            project["name"] = "Arcane Gear"
            save_project(tmp, project)
            plan = {"feature_name": "Arcane Gear", "actions": [{"type": "add_file", "path": "kubejs/server_scripts/arcane.js", "content": "// ok"}]}
            gates = evaluate_quality_gates(tmp, plan, asset_requests=[])
            draft = append_draft(tmp, project, plan=plan, bundle={"feature_plan": plan}, filters={"risk": "low"}, gates=gates)
            append_mini_change(tmp, load_project(tmp), request="make it cheaper", status="queued")

            loaded = load_project(tmp)
            self.assertEqual(loaded["name"], "Arcane Gear")
            self.assertEqual(len(loaded["drafts"]), 1)
            self.assertEqual(loaded["drafts"][0]["id"], draft["id"])
            self.assertEqual(len(loaded["mini_changes"]), 1)

    def test_asset_requests_convert_to_texture_blueprint(self) -> None:
        bundle = {
            "feature_plan": {"feature_name": "Widget", "actions": []},
            "asset_requests": [
                {
                    "id": "Arcane Widget",
                    "namespace": "forager_magic",
                    "path": "item/arcane_widget",
                    "asset_kind": "tool",
                    "model_type": "handheld",
                    "resolution": "32x32",
                }
            ],
        }
        plan = feature_plan_from_bundle(bundle)
        assets = extract_asset_requests(bundle, plan)
        blueprint = texture_blueprint_from_assets(assets)
        self.assertEqual(assets[0]["namespace"], "forager_magic")
        self.assertEqual(blueprint["new_textures"][0]["path"], "item/arcane_widget")
        self.assertEqual(blueprint["new_models"][0]["model_type"], "handheld")

    def test_quality_gates_block_unsafe_paths_and_warn_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = {
                "feature_name": "Unsafe",
                "actions": [
                    {"type": "add_file", "path": "../escape.js", "content": "while (true) {}"},
                    {"type": "add_file", "path": "mods/bad.jar", "content": "binary"},
                ],
            }
            gates = evaluate_quality_gates(tmp, plan, asset_requests=[{"namespace": "Bad Namespace", "path": "item/bad"}])
            self.assertFalse(gates["ok"])
            self.assertEqual(gates["verdict"], "block")
            messages = json.dumps(gates)
            self.assertIn("Unsafe path", messages)
            self.assertIn("Invalid namespace", messages)

    def test_quality_gates_validate_generated_media_requests(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            plan = {"feature_name": "Media", "actions": [{"type": "add_file", "path": "docs/media.md", "content": "sound animation"}]}
            gates = evaluate_quality_gates(
                tmp,
                plan,
                asset_requests=[{"namespace": "forager_ai", "path": "../bad.png", "asset_kind": "item"}],
                sound_requests=[{"namespace": "forager_ai", "event": "item.cast", "sound_file": "../bad", "sound_kind": "unknown_kind"}],
                blockbench_animations=[{"target_texture_path": "../item/bad", "animation_kind": "teleport", "length": 90}],
            )
            messages = json.dumps(gates)
            self.assertFalse(gates["ok"])
            self.assertIn("Unsafe asset path", messages)
            self.assertIn("Unsafe sound file path", messages)
            self.assertIn("Unsafe animation target path", messages)
            self.assertIn("Unrecognized sound_kind", messages)

    def test_council_artifact_and_skipped_review_are_persisted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = load_project(tmp)
            plan = {"feature_name": "Reviewed", "actions": [{"type": "add_file", "path": "docs/review.txt", "content": "test"}]}
            gates = evaluate_quality_gates(tmp, plan)
            draft = append_draft(tmp, project, plan=plan, gates=gates)
            artifact = build_foundry_artifact(instance_name="Pack", project=project, draft=draft, gates=gates)
            self.assertEqual(artifact["artifact_type"], "forager_ai_mod_foundry_draft")

            review = maybe_run_continuous_review(
                instance_root=tmp,
                instance_name="Pack",
                project=load_project(tmp),
                draft=draft,
                gates=gates,
                texture_blueprint={},
                api_key="",
                model="openrouter/auto",
                label="unit",
            )
            self.assertEqual(review["final_verdict"], "skipped")
            self.assertTrue((Path(tmp) / ".forager/ai_mod_foundry/reviews").is_dir())

    def test_compiled_forge_scaffold_is_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result = scaffold_compiled_forge_project(
                tmp,
                project_name="Arcane Widget",
                mod_id="arcane_widget",
                package="com.forager.arcane_widget",
                mc_version="1.20.1",
            )
            root = Path(result["project_root"])
            self.assertTrue((root / "build.gradle").is_file())
            self.assertTrue((root / "src/main/resources/META-INF/mods.toml").is_file())
            self.assertTrue(result["build_ready"])
            self.assertIn(".forager/ai_mod_foundry/forge_projects", result["relative_root"])


if __name__ == "__main__":
    unittest.main()
