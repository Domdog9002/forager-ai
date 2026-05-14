from __future__ import annotations

from pathlib import Path

from forager_ai.ui.mc_model_mesh import (
    infer_model_preview_kind,
    load_model_json,
    mesh_from_java_model,
    resolve_texture_path_from_model,
)
from forager_ai.ui.mc_model_mesh import _permute_uv_four


def test_infer_model_preview_kind() -> None:
    assert infer_model_preview_kind({"parent": "minecraft:item/generated"}) == "item_plane"
    assert infer_model_preview_kind({"elements": [{"from": [0, 0, 0], "to": [1, 1, 1]}]}) == "elements"
    assert infer_model_preview_kind({"parent": "minecraft:block/cube_all"}) == "unknown"


def test_permute_uv_four_rotates_ninety() -> None:
    ta, tb, tc, td = (0.0, 1.0), (1.0, 1.0), (1.0, 0.0), (0.0, 0.0)
    ra, rb, rc, rd = _permute_uv_four(ta, tb, tc, td, 90)
    assert ra == td and rb == ta and rc == tb and rd == tc


def test_mesh_from_java_model_single_cube() -> None:
    model = {
        "textures": {"all": "minecraft:block/stone"},
        "elements": [
            {
                "from": [0, 0, 0],
                "to": [16, 16, 16],
                "faces": {
                    "north": {"uv": [0, 0, 16, 16], "texture": "#all"},
                    "south": {"uv": [0, 0, 16, 16], "texture": "#all"},
                    "east": {"uv": [0, 0, 16, 16], "texture": "#all"},
                    "west": {"uv": [0, 0, 16, 16], "texture": "#all"},
                    "up": {"uv": [0, 0, 16, 16], "texture": "#all"},
                    "down": {"uv": [0, 0, 16, 16], "texture": "#all"},
                },
            }
        ],
    }
    mesh = mesh_from_java_model(model, texture_width=16, texture_height=16)
    assert mesh is not None
    assert len(mesh["positions"]) >= 18
    assert len(mesh["indices"]) >= 6


def test_load_model_json_roundtrip(tmp_path: Path) -> None:
    p = tmp_path / "m.json"
    p.write_text('{"parent":"minecraft:block/cube_all"}\n', encoding="utf-8")
    data = load_model_json(p)
    assert data is not None
    assert data.get("parent") == "minecraft:block/cube_all"


def test_resolve_texture_path_from_model(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    tex = root / "assets" / "demo" / "textures" / "block" / "foo.png"
    tex.parent.mkdir(parents=True, exist_ok=True)
    tex.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    model = {"textures": {"all": "demo:block/foo"}}
    got = resolve_texture_path_from_model(model, pack_root=root)
    assert got is not None
    assert got.is_file()


def test_resolve_texture_implicit_minecraft_namespace(tmp_path: Path) -> None:
    root = tmp_path / "pack2"
    tex = root / "assets" / "minecraft" / "textures" / "block" / "bar.png"
    tex.parent.mkdir(parents=True, exist_ok=True)
    tex.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 40)
    model = {"textures": {"all": "block/bar"}}
    got = resolve_texture_path_from_model(model, pack_root=root)
    assert got is not None
    assert got.is_file()
