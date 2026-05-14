from __future__ import annotations

from unittest.mock import patch

from forager_ai.dev.instance_matrix import (
    build_unified_rows,
    capability_for,
    merge_devkit_binding,
    parse_mc_version,
    profile_key_forager,
)


def test_parse_mc_version() -> None:
    assert parse_mc_version("1.20.1") == (1, 20, 1)
    assert parse_mc_version("1.21") == (1, 21, 0)


def test_capability_forge_120() -> None:
    c = capability_for(minecraft_version="1.20.1", loader="forge", loader_version="47.2.0")
    assert c["tier"] == "supported"
    assert "17" in c["jdk_recommendation"]


def test_capability_fabric() -> None:
    c = capability_for(minecraft_version="1.20.1", loader="fabric", loader_version="0.15.0")
    assert c["devkit_kind"] == "fabric_loom"


def test_merge_devkit_binding_roundtrip() -> None:
    b = merge_devkit_binding({}, "forager|x", "C:\\dev\\mdk")
    assert b["forager|x"]["devkit_root"] == "C:\\dev\\mdk"
    b2 = merge_devkit_binding(b, "forager|x", "")
    assert "forager|x" not in b2


@patch("forager_ai.dev.instance_matrix.discover_external_instances", return_value=[])
def test_build_unified_rows_empty_config(_mock_discover: object) -> None:
    rows = build_unified_rows(instances=[], config={})
    assert rows == []


def test_profile_key_forager() -> None:
    assert profile_key_forager("My Pack") == "forager|My Pack"
