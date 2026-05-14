from __future__ import annotations

import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.ai.artifacts import compat_proposals_from_conflicts, make_ai_artifact
from forager_ai.ai.config_assistant import draft_config_feature_plan, summarize_config_targets
from forager_ai.ai.install_advisor import deterministic_install_advice
from forager_ai.ai.openrouter_client import _extract_json
import forager_ai.ai.openrouter_client as openrouter_client
from forager_ai.analysis.health_score import build_pack_health_score
from forager_ai.analysis.mod_roles import classify_mod, classify_mods, summarize_roles
from forager_ai.analysis.progression import audit_progression
from forager_ai.diagnostics.crash_parser import analyze_crash_log_ai
from forager_ai.fs.safe_writer import write_text_utf8_nobom


class AiPowerFeatureTests(unittest.TestCase):
    def test_mod_roles_and_summary(self) -> None:
        roles = classify_mods(
            [
                {"id": "create", "name": "Create"},
                {"id": "cloth-config", "name": "Cloth Config API"},
                {"id": "embeddium", "name": "Embeddium"},
            ]
        )
        summary = summarize_roles(roles)
        self.assertIn("tech", summary["role_counts"])
        self.assertIn("library", summary["role_counts"])
        self.assertIn("performance", summary["role_counts"])
        self.assertEqual(classify_mod({"id": "optifine", "name": "OptiFine"})["risk"], "medium")

    def test_health_score_deducts_conflict_and_perf_risk(self) -> None:
        report = build_pack_health_score(
            manifest={"mods": [{"id": "create"}]},
            conflict_summary={"total_conflicts": 2, "severity_counts": {"high": 1, "medium": 1}},
            performance_report={"findings": [{"severity": "medium"}]},
            compat_rules_count=0,
            role_summary={"risk_counts": {"medium": 1}},
        )
        self.assertLess(report["score"], 100)
        self.assertIn(report["verdict"], {"watch", "risky", "critical"})

    def test_progression_flags_major_pillars_without_scripts(self) -> None:
        manifest = {"mods": [{"id": "create"}, {"id": "ars_nouveau"}]}
        with tempfile.TemporaryDirectory() as tmp:
            audit = audit_progression(manifest=manifest, pack_root=tmp, compat_rules=[])
        ids = {item["id"] for item in audit["findings"]}
        self.assertIn("create_ars_progression", ids)
        self.assertIn("no_progression_scripts", ids)

    def test_config_assistant_finds_targets_and_drafts_plan(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config", "ars_nouveau-common.toml")
            write_text_utf8_nobom(path, "mana = 10\n")
            summary = summarize_config_targets(tmp, "reduce ars mana")
            self.assertTrue(summary["matches"])
            plan = draft_config_feature_plan(tmp, "reduce ars mana")
        self.assertEqual(plan["feature_name"], "config_assistant_draft")
        self.assertEqual(plan["actions"][0]["type"], "edit_file")

    def test_artifacts_and_compat_proposals(self) -> None:
        conflicts = [
            {
                "id": "known_pair_create_ars",
                "type": "known_incompatibility",
                "severity": "medium",
                "affected_mods": ["create", "ars_nouveau"],
                "description": "Needs progression review.",
                "suggested_resolution": "Add a compat rule.",
            }
        ]
        proposals = compat_proposals_from_conflicts(conflicts)
        self.assertEqual(proposals[0]["affected_mods"], ["create", "ars_nouveau"])
        artifact = make_ai_artifact(
            artifact_type="test",
            pack_name="pack",
            title="Title",
            summary="Summary",
            payload={"ok": True},
        )
        self.assertEqual(artifact["artifact_type"], "test")

    def test_install_advice_and_crash_fallback(self) -> None:
        advice = deterministic_install_advice(
            {
                "decision": "warn",
                "conflicts": [{"severity": "high", "type": "missing_dependency", "description": "Missing API"}],
            }
        )
        self.assertEqual(advice["decision"], "warn")
        crash = analyze_crash_log_ai("Create kinetic stress crash", api_key="")
        self.assertFalse(crash["ai_used"])
        self.assertIn("feature_plan", crash)

    def test_model_json_extraction_handles_multiple_objects_and_braces_in_strings(self) -> None:
        parsed = _extract_json('notes {"ignored": true} then {"feature_plan": {"actions": []}, "text": "{literal}"}')
        self.assertEqual(parsed["feature_plan"]["actions"], [])
        self.assertEqual(parsed["text"], "{literal}")

    def test_foundry_repair_failure_preserves_first_bundle(self) -> None:
        original = openrouter_client.chat_completion_text
        responses = iter(
            [
                '{"strategy":{"builder_directive":"build safe"}}',
                '{"feature_plan":{"feature_name":"First","actions":[]},"asset_requests":[]}',
                '{"score":42,"issues":["needs repair"],"repair_directive":"fix it"}',
                'not json',
            ]
        )

        def fake_chat_completion_text(**_kwargs: object) -> str:
            return next(responses)

        try:
            openrouter_client.chat_completion_text = fake_chat_completion_text  # type: ignore[assignment]
            bundle = openrouter_client.generate_mod_foundry_bundle(
                api_key="key",
                user_request="make a safe feature",
                pack_context={},
                filters={},
            )
        finally:
            openrouter_client.chat_completion_text = original  # type: ignore[assignment]

        self.assertEqual(bundle["feature_plan"]["feature_name"], "First")
        self.assertFalse(bundle["intelligence_report"]["repaired"])
        self.assertTrue(bundle["intelligence_report"]["repair_error"])


if __name__ == "__main__":
    unittest.main()
