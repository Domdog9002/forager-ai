from __future__ import annotations

from pathlib import Path

from forager_ai.ui.mc_model_mesh import infer_model_preview_kind, mesh_from_java_model, resolve_texture_path_from_model
from forager_ai.ui.mc_model_resolve import resolve_model_for_preview


def test_resolve_cube_all_inherits_geometry(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    tex = root / "assets" / "demo" / "textures" / "block" / "custom.png"
    tex.parent.mkdir(parents=True, exist_ok=True)
    tex.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 48)
    model_path = root / "assets" / "demo" / "models" / "block" / "custom_block.json"
    model_path.parent.mkdir(parents=True, exist_ok=True)
    model_path.write_text(
        '{"parent": "minecraft:block/cube_all", "textures": {"all": "demo:block/custom"}}\n',
        encoding="utf-8",
    )
    raw = __import__("json").loads(model_path.read_text(encoding="utf-8"))
    resolved = resolve_model_for_preview(raw, root)
    assert isinstance(resolved.get("elements"), list) and resolved["elements"]
    assert infer_model_preview_kind(resolved) == "elements"
    tp = resolve_texture_path_from_model(resolved, pack_root=root)
    assert tp is not None and tp.is_file()
    tw, th = 16, 16
    mesh = mesh_from_java_model(resolved, texture_width=tw, texture_height=th)
    assert mesh is not None
    assert len(mesh["indices"]) >= 6
