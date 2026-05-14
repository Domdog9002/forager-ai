from __future__ import annotations

from forager_ai.ui.live_block_preview import (
    DEFAULT_THREE_CDN,
    build_threejs_block_preview_html,
    build_threejs_uv_mesh_preview_html,
)


def test_build_threejs_block_preview_html_contains_script_and_mode() -> None:
    html = build_threejs_block_preview_html(
        dom_id="t1",
        png_base64="iVBORw0KGgo=",
        height=300,
        three_script_src="https://example.invalid/three.min.js",
        preview_mode="texture_cube",
    )
    assert "host-t1" in html
    assert "https://example.invalid/three.min.js" in html
    assert "texture_cube" in html


def test_build_threejs_uv_mesh_preview_html_structure() -> None:
    mesh = {"positions": [0, 0, 0, 1, 0, 0, 1, 1, 0, 0, 1, 0], "uvs": [0, 0, 1, 0, 1, 1, 0, 1], "indices": [0, 1, 2, 0, 2, 3]}
    html = build_threejs_uv_mesh_preview_html(
        dom_id="m1",
        mesh=mesh,
        png_base64="iVBORw0KGgo=",
        height=280,
        three_script_src=DEFAULT_THREE_CDN,
    )
    assert "hostm-m1" in html
    assert "mesh-m1" in html
    assert DEFAULT_THREE_CDN in html
