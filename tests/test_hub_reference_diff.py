"""Hub reference pair diff narrative formatter."""

from __future__ import annotations

from forager_ai.pack.hub_reference_diff import format_hub_reference_diff_narrative


def test_format_hub_reference_diff_narrative_smoke() -> None:
    mods = {
        "only_in_a": [{"logical_key": "a.jar", "rel": "mods/a.jar"}],
        "only_in_b": [{"logical_key": "b.jar", "rel": "mods/b.jar"}],
        "same_logical_jar_different_hash": [{"logical_key": "c.jar", "sha256_a": "a…", "sha256_b": "b…"}],
        "basename_collisions": [],
        "truncated_a": False,
        "truncated_b": False,
    }
    surface = {
        "sections": {
            "config": {
                "only_in_a": ["x.cfg"],
                "only_in_b": ["y.cfg"],
                "in_both_count": 2,
            },
        },
        "note": "top-level only",
    }
    out = format_hub_reference_diff_narrative(
        mods_cmp=mods,
        surface_cmp=surface,
        label_active="Pack A",
        label_reference="Pack B",
        max_chars=8000,
    )
    assert "Pack A" in out
    assert "a.jar" in out
    assert "b.jar" in out
    assert "c.jar" in out
    assert "x.cfg" in out
