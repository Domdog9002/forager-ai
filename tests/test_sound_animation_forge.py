from __future__ import annotations

import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.content.blockbench_models import build_bbmodel_project, validate_bbmodel
from forager_ai.content.content_manager import ContentManager
from forager_ai.content.sound_forge import render_sound_effect, write_wav
from forager_ai.content.texture_forge import render_texture_asset
from forager_ai.mods.mod_foundry import (
    evaluate_quality_gates,
    extract_blockbench_animation_requests,
    extract_sound_requests,
)


class SoundAnimationForgeTests(unittest.TestCase):
    def test_sound_forge_is_deterministic_and_writes_wav(self) -> None:
        spec = {"sound_kind": "magic_chime", "duration_ms": 350, "pitch": 1.2, "volume": 0.6}
        first = render_sound_effect(spec)
        second = render_sound_effect(spec)
        self.assertEqual(first.samples[:200], second.samples[:200])
        self.assertGreaterEqual(first.quality["score"], 70)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "magic.wav"
            write_wav(path, first)
            self.assertTrue(path.is_file())
            with wave.open(str(path), "rb") as fh:
                self.assertEqual(fh.getnchannels(), 1)
                self.assertEqual(fh.getframerate(), 44100)
                self.assertGreater(fh.getnframes(), 0)

    def test_content_manager_writes_sound_preview_and_sounds_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ContentManager(tmp)
            manager.create_resource_pack("sound_test", "Sound test", pack_format=15)
            report = manager.apply_ai_resource_plan(
                "sound_test",
                {
                    "sound_events": [
                        {
                            "namespace": "forager_ai",
                            "event": "item.arcane_widget.cast",
                            "subtitle": "Arcane Widget Cast",
                            "sound_file": "custom/arcane_widget_cast",
                            "sound_kind": "spell_cast",
                            "duration_ms": 250,
                            "generation_mode": "local_procedural",
                        }
                    ]
                },
            )
            pack = Path(manager.get_resource_pack("sound_test").path)  # type: ignore[union-attr]
            self.assertTrue((pack / "assets/forager_ai/sounds.json").is_file())
            self.assertTrue((pack / ".forager/sounds/forager_ai/custom/arcane_widget_cast.wav").is_file())
            with open(pack / "assets/forager_ai/sounds.json", "r", encoding="utf-8") as fh:
                sounds = json.load(fh)
            self.assertIn("item.arcane_widget.cast", sounds)
            self.assertTrue(report["warnings"])

    def test_blockbench_model_can_include_animation_timeline(self) -> None:
        texture = render_texture_asset({"path": "block/animated_core", "asset_kind": "model_texture"}).image
        model = build_bbmodel_project(
            name="animated_core",
            texture=texture,
            model_type="decorative_object",
            animations=[{"name": "idle_bob", "animation_kind": "idle_bob", "length": 1.5, "loop": True}],
        )
        self.assertTrue(validate_bbmodel(model)["ok"])
        self.assertIn("animations", model)
        self.assertTrue(model["animations"][0]["animators"])

    def test_foundry_extracts_sound_and_animation_requests_for_gates(self) -> None:
        bundle = {
            "sound_requests": [{"namespace": "forager_ai", "event": "item.widget.use", "sound_file": "custom/widget_use"}],
            "blockbench_animations": [{"target_texture_path": "item/widget", "animation_kind": "swing"}],
        }
        sounds = extract_sound_requests(bundle)
        anims = extract_blockbench_animation_requests(bundle)
        self.assertEqual(sounds[0]["sound_file"], "custom/widget_use")
        self.assertEqual(anims[0]["animation_kind"], "swing")
        with tempfile.TemporaryDirectory() as tmp:
            gates = evaluate_quality_gates(
                tmp,
                {"feature_name": "Widget", "actions": [{"type": "add_file", "path": "docs/widget.txt", "content": "ok"}]},
                sound_requests=sounds,
                blockbench_animations=anims,
            )
            self.assertTrue(gates["ok"])
            self.assertIn("sound_requests", json.dumps(gates))


if __name__ == "__main__":
    unittest.main()
