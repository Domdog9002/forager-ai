"""Tests for structured TOML/JSON patch helpers."""

from __future__ import annotations

import json

import pytest

from forager_ai.engine.structured_patch import (
    apply_json_merge,
    apply_toml_set_values,
    deep_merge_json,
)


def test_deep_merge_json_nested() -> None:
    base = {"a": {"x": 1}, "b": 2}
    overlay = {"a": {"y": 3}, "c": 4}
    assert deep_merge_json(base, overlay) == {"a": {"x": 1, "y": 3}, "b": 2, "c": 4}


def test_apply_json_merge_new_file() -> None:
    out = apply_json_merge("", {"hello": {"world": True}})
    assert json.loads(out) == {"hello": {"world": True}}


def test_apply_toml_set_values_dotted() -> None:
    src = "[server]\nport = 25565\n"
    out = apply_toml_set_values(src, {"server.port": 25566, "other.flag": True})
    try:
        import tomllib

        parsed = tomllib.loads(out)
    except Exception:
        tomli = pytest.importorskip("tomli")
        parsed = tomli.loads(out)
    assert parsed["server"]["port"] == 25566
    assert parsed["other"]["flag"] is True
