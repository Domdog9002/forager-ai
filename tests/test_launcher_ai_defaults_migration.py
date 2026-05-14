"""Migration from legacy plain OpenRouter auto-routing ids toward bundled tier defaults."""

from __future__ import annotations

from forager_ai.launcher.launcher_core import (
    DEFAULT_AI_ROUTER_CHAT_MODEL,
    DEFAULT_AI_ROUTER_QUALITY_MODEL,
    FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY,
    FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2,
    apply_frontier_router_defaults,
    apply_legacy_router_model_defaults,
)


def test_migration_skips_when_marker_present():
    cfg = {
        FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY: True,
        "ai_model": "openrouter/auto",
        "ai_model_balanced": "",
    }
    out = apply_legacy_router_model_defaults(cfg)
    assert out is cfg
    assert out["ai_model"] == "openrouter/auto"


def test_migration_plain_auto_balanced_upgrade():
    cfg = {"ai_model": "openrouter/auto", "ai_model_balanced": ""}
    out = apply_legacy_router_model_defaults(cfg)
    assert out[FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY] is True
    assert out["ai_model"] == DEFAULT_AI_ROUTER_CHAT_MODEL
    assert out["ai_model_balanced"] == DEFAULT_AI_ROUTER_CHAT_MODEL


def test_migration_quality_tier_upgrade():
    cfg = {"ai_model_quality": "openrouter/auto"}
    out = apply_legacy_router_model_defaults(cfg)
    assert out["ai_model_quality"] == DEFAULT_AI_ROUTER_QUALITY_MODEL


def test_rev2_skips_when_marker_present():
    cfg = {
        FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2: True,
        "ai_model": "openai/gpt-4o-mini",
    }
    out = apply_frontier_router_defaults(cfg)
    assert out is cfg
    assert out["ai_model"] == "openai/gpt-4o-mini"


def test_rev2_main_mini_to_4o():
    cfg = {"ai_model": "openai/gpt-4o-mini", "ai_model_balanced": ""}
    out = apply_frontier_router_defaults(cfg)
    assert out["ai_model"] == DEFAULT_AI_ROUTER_CHAT_MODEL
    assert out[FORAGER_ROUTER_DEFAULTS_MIGRATION_KEY_REV2] is True


def test_rev2_quality_gpt4o_to_frontier():
    cfg = {"ai_model_quality": "openai/gpt-4o"}
    out = apply_frontier_router_defaults(cfg)
    assert out["ai_model_quality"] == DEFAULT_AI_ROUTER_QUALITY_MODEL


def test_rev2_preset_balanced_to_quality_when_redundant_override():
    cfg = {
        "ai_model_preset": "balanced",
        "ai_model": "openai/gpt-4o",
        "ai_model_balanced": "openai/gpt-4o",
    }
    out = apply_frontier_router_defaults(cfg)
    assert out["ai_model_preset"] == "quality"
