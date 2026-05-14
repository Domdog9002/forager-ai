from __future__ import annotations

import json
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from forager_ai.content.content_manager import ContentManager
from forager_ai.content.blockbench_models import build_bbmodel_project, validate_bbmodel
from forager_ai.content.texture_forge import (
    extract_reference_style_from_image,
    model_json_for_spec,
    render_animation_strip,
    render_texture_asset,
)
from forager_ai.content.texture_workshop import (
    apply_pixel_transform,
    load_style_memory,
    repair_texture,
    save_queue_metadata,
    save_style_profile,
)


class TextureForgeTests(unittest.TestCase):
    def test_render_texture_asset_is_deterministic_and_minecraft_sized(self) -> None:
        spec = {
            "namespace": "minecraft",
            "path": "item/arcane_wrench",
            "asset_kind": "tool",
            "resolution": 32,
            "material": "metal",
            "shape_language": "diagonal tool with arcane highlight",
            "color_hint": "#44d7e8",
        }
        theme = {"title": "arcane tech", "palette": ["#44d7e8", "#7c3aed", "#1e293b"]}
        first = render_texture_asset(spec, theme, index=0)
        second = render_texture_asset(spec, theme, index=0)

        self.assertEqual(first.image.size, (32, 32))
        self.assertEqual(first.image.tobytes(), second.image.tobytes())
        self.assertGreaterEqual(first.quality["score"], 50)

    def test_render_animation_strip_has_valid_frame_shape(self) -> None:
        result = render_animation_strip(
            {"path": "block/charged_core", "asset_kind": "ore", "resolution": 16, "color_hint": "#58c95f"},
            {"palette": ["#58c95f", "#172554"]},
            frames=5,
        )
        self.assertEqual(result.image.size, (16, 80))
        self.assertFalse(result.quality["warnings"])

    def test_model_json_for_spec_supports_handheld_and_cube(self) -> None:
        handheld = model_json_for_spec(
            {"model_type": "handheld", "texture_layer0": "minecraft:textures/item/arcane_wrench"},
            namespace="minecraft",
            rel="item/arcane_wrench",
        )
        cube = model_json_for_spec({}, namespace="minecraft", rel="block/arcane_block")
        self.assertEqual(handheld["parent"], "minecraft:item/handheld")
        self.assertIn("layer0", handheld["textures"])
        self.assertEqual(cube["textures"]["all"], "minecraft:textures/block/arcane_block")

    def test_apply_ai_resource_plan_writes_real_textures_models_and_export(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ContentManager(tmp)
            manager.create_resource_pack("forge_test", "Texture Forge test", pack_format=15)
            plan = {
                "theme": {"title": "Arcane Tech", "palette": ["#44d7e8", "#7c3aed", "#1e293b"]},
                "new_textures": [
                    {
                        "namespace": "minecraft",
                        "path": "item/arcane_wrench",
                        "asset_kind": "tool",
                        "resolution": 32,
                        "material": "metal",
                        "shape_language": "diagonal tool",
                        "color_hint": "#44d7e8",
                    },
                    {
                        "namespace": "minecraft",
                        "path": "block/arcane_machine_uv",
                        "asset_kind": "model_texture",
                        "resolution": 32,
                        "uv_template": "cube",
                        "color_hint": "#7c3aed",
                    },
                ],
                "new_models": [
                    {
                        "namespace": "minecraft",
                        "path": "item/arcane_wrench",
                        "model_type": "handheld",
                        "texture_layer0": "minecraft:textures/item/arcane_wrench",
                    }
                ],
                "animations": [
                    {"namespace": "minecraft", "texture_path": "block/charged_core", "frames": 4, "frametime": 2}
                ],
            }
            report = manager.apply_ai_resource_plan("forge_test", plan)
            pack = Path(manager.get_resource_pack("forge_test").path)  # type: ignore[union-attr]

            item_png = pack / "assets" / "minecraft" / "textures" / "item" / "arcane_wrench.png"
            model_json = pack / "assets" / "minecraft" / "models" / "item" / "arcane_wrench.json"
            anim_png = pack / "assets" / "minecraft" / "textures" / "block" / "charged_core.png"
            anim_meta = pack / "assets" / "minecraft" / "textures" / "block" / "charged_core.png.mcmeta"

            self.assertTrue(item_png.is_file())
            self.assertTrue(model_json.is_file())
            self.assertTrue(anim_png.is_file())
            self.assertTrue(anim_meta.is_file())
            with Image.open(item_png) as img:
                self.assertEqual(img.size, (32, 32))
            with open(model_json, "r", encoding="utf-8") as fh:
                model = json.load(fh)
            self.assertEqual(model["parent"], "minecraft:item/handheld")
            self.assertTrue(report["quality"])

            zip_path = Path(tmp) / "forge_test.zip"
            self.assertTrue(manager.export_resource_pack("forge_test", str(zip_path)))
            with zipfile.ZipFile(zip_path) as zf:
                self.assertIn("assets/minecraft/textures/item/arcane_wrench.png", zf.namelist())

    def test_reference_style_influences_palette(self) -> None:
        ref = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
        for x in range(4, 12):
            for y in range(4, 12):
                ref.putpixel((x, y), (240, 40, 90, 255))
        style = extract_reference_style_from_image(ref)
        result = render_texture_asset(
            {
                "path": "item/ref_sword",
                "asset_kind": "item",
                "resolution": 16,
                "reference_palette": style["palette"],
                "color_hint": style["palette"][0],
            },
            {},
        )
        self.assertIn(style["palette"][0].lower(), [c.lower() for c in result.metadata["palette"]])
        self.assertEqual(result.image.size, (16, 16))

    def test_blockbench_model_embeds_texture(self) -> None:
        texture = render_texture_asset({"path": "block/test_cube", "asset_kind": "model_texture"}).image
        model = build_bbmodel_project(name="test_cube", texture=texture, model_type="cube")
        validation = validate_bbmodel(model)
        self.assertTrue(validation["ok"], validation["warnings"])
        self.assertEqual(model["meta"]["model_format"], "free")
        self.assertTrue(model["textures"][0]["source"].startswith("data:image/png;base64,"))
        self.assertTrue(model["elements"])

    def test_blockbench_templates_create_distinct_sources(self) -> None:
        texture = render_texture_asset({"path": "block/test_template", "asset_kind": "model_texture"}).image
        for template in ("slab", "pillar", "handheld tool", "crossed plant", "simple mob", "simple armor display", "decorative object"):
            model = build_bbmodel_project(name=f"test_{template}", texture=texture, model_type=template)
            self.assertTrue(validate_bbmodel(model)["ok"])
            self.assertTrue(model["elements"])

    def test_style_memory_queue_and_pixel_repair_helpers(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            save_style_profile(
                tmp,
                "Test Style",
                {
                    "palette": ["#112233", "#445566"],
                    "motifs": ["readable glyphs"],
                    "resolution": "32x32",
                    "preferred_model_types": ["cube_all"],
                    "accessibility_rules": ["high contrast"],
                },
            )
            memory = load_style_memory(tmp)
            self.assertEqual(memory["active"], "Test Style")
            self.assertIn("Test Style", memory["profiles"])

            queue_path = save_queue_metadata(tmp, [{"id": "one", "approved": True}], name="unit_queue")
            self.assertTrue(Path(queue_path).is_file())

            image = render_texture_asset({"path": "item/repair_me", "resolution": 16}).image
            outlined = apply_pixel_transform(image, "outline")
            self.assertEqual(outlined.size, image.size)
            repaired, report = repair_texture(image)
            self.assertEqual(repaired.size, image.size)
            self.assertIn("after", report)

    def test_write_texture_replacement_creates_metadata_and_bbmodel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ContentManager(tmp)
            manager.create_resource_pack("replace_test", "Replacement test", pack_format=15)
            report = manager.write_texture_replacement(
                "replace_test",
                target={"id": "minecraft:diamond_sword", "type": "item", "mod_id": "minecraft"},
                spec={
                    "namespace": "minecraft",
                    "path": "item/diamond_sword",
                    "asset_kind": "tool",
                    "resolution": 32,
                    "model_type": "handheld",
                    "color_hint": "#44d7e8",
                },
            )
            pack = Path(manager.get_resource_pack("replace_test").path)  # type: ignore[union-attr]
            self.assertTrue((pack / "assets/minecraft/textures/item/diamond_sword.png").is_file())
            self.assertTrue((pack / "assets/minecraft/models/item/diamond_sword.json").is_file())
            self.assertTrue((pack / ".forager/blockbench/diamond_sword.bbmodel").is_file())
            self.assertTrue((pack / ".forager/replacements/diamond_sword.json").is_file())
            self.assertTrue(report["quality"])
            self.assertTrue((pack / ".forager/texture_forge/reports/latest.json").is_file())

    def test_export_report_blockbench_export_and_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            manager = ContentManager(tmp)
            manager.create_resource_pack("rollback_test", "Rollback test", pack_format=15)
            pack = Path(manager.get_resource_pack("rollback_test").path)  # type: ignore[union-attr]
            target_png = pack / "assets/minecraft/textures/item/diamond_sword.png"
            target_png.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGBA", (16, 16), (1, 2, 3, 255)).save(target_png)

            manager.write_texture_replacement(
                "rollback_test",
                target={"id": "minecraft:diamond_sword", "type": "item", "mod_id": "minecraft"},
                spec={"namespace": "minecraft", "path": "item/diamond_sword", "resolution": 16},
            )
            source_zip = Path(tmp) / "bb_sources.zip"
            self.assertTrue(manager.export_blockbench_source_pack("rollback_test", str(source_zip)))
            self.assertTrue(source_zip.is_file())
            validation = manager.texture_forge_export_report("rollback_test")
            self.assertGreaterEqual(validation["png_count"], 1)

            rollback = manager.rollback_last_texture_forge_apply("rollback_test")
            self.assertTrue(rollback["restored"])
            with Image.open(target_png) as restored:
                self.assertEqual(restored.getpixel((0, 0)), (1, 2, 3, 255))


if __name__ == "__main__":
    unittest.main()
