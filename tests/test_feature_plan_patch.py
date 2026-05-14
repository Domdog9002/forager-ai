from __future__ import annotations

from forager_ai.engine.feature_plan import validate_feature_plan


def test_validate_patch_toml_ok() -> None:
    plan = {
        "feature_name": "t",
        "actions": [{"type": "patch_toml", "path": "config/x.toml", "set_values": {"a.b": 1}}],
    }
    assert validate_feature_plan("unused", plan) == []


def test_validate_patch_json_rejects_empty_merge() -> None:
    plan = {
        "feature_name": "j",
        "actions": [{"type": "patch_json", "path": "data/x.json", "merge": {}}],
    }
    errs = validate_feature_plan("unused", plan)
    assert any("merge must be non-empty" in e.message for e in errs)
