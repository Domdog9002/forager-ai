"""Regression tests for enhancement modules (no network)."""

from __future__ import annotations

# Keep in sync with dashboard.py FORGER_NAV_LABEL_BY_KEY (all routable page keys).
_FORAGER_NAV_KEYS = frozenset(
    {
        "ai_architect",
        "ai_atlas",
        "ai_council",
        "ai_crash",
        "ai_plans",
        "approvals_inbox",
        "conflicts",
        "content",
        "drift",
        "forge_studio",
        "forager_hub",
        "home",
        "hub",
        "instance_configure",
        "instances",
        "mc_catalog",
        "mods",
        "performance",
        "power_center",
        "resource_packs",
        "settings",
    }
)

from forager_ai.ai.council import council_followup_checklist
from forager_ai.ai.embedding_rag import _cosine
from forager_ai.ai.model_resolve import resolve_ai_model, resolve_council_model


def test_resolve_council_model() -> None:
    cfg = {
        "ai_model": "openrouter/auto",
        "ai_model_quality": "test/q",
        "ai_model_council": "",
    }
    assert resolve_council_model(cfg) == "test/q"
    cfg["ai_model_council"] = "anthropic/claude-3.5-sonnet"
    assert resolve_council_model(cfg) == "anthropic/claude-3.5-sonnet"
    cfg2 = {"ai_model": "x/y", "ai_model_quality": "", "ai_model_council": ""}
    assert resolve_council_model(cfg2) == "x/y"


def test_resolve_ai_model_preset() -> None:
    cfg = {
        "ai_model_preset": "fast",
        "ai_model": "openrouter/auto",
        "ai_model_fast": "test/fast",
        "ai_model_quality": "test/q",
        "ai_model_balanced": "",
    }
    assert resolve_ai_model(cfg) == "test/fast"
    cfg["ai_model_preset"] = "quality"
    assert resolve_ai_model(cfg) == "test/q"
    cfg["ai_model_preset"] = "balanced"
    assert resolve_ai_model(cfg) == "openrouter/auto"


def test_council_checklist_non_empty() -> None:
    steps = council_followup_checklist({"final_verdict": "block", "recommended_actions": ["a", "b", "c"]})
    assert len(steps) >= 3
    assert any("review" in s.lower() or "compat" in s.lower() for s in steps)


def test_cosine_orthogonal() -> None:
    a, b = [1.0, 0.0], [0.0, 1.0]
    assert abs(_cosine(a, b)) < 0.001


def test_cosine_same() -> None:
    v = [0.5, 0.5, 0.5]
    assert abs(_cosine(v, v) - 1.0) < 0.001


def test_retrieve_for_assistant_keyword_fallback() -> None:
    from forager_ai.ai.embedding_rag import retrieve_for_assistant

    text, cite, meta = retrieve_for_assistant(
        "kubejs scripts",
        [],
        api_key="",
        use_embedding_rag=False,
    )
    assert meta.get("mode") == "keyword"


def test_assistant_go_routes_match_dashboard_nav_keys() -> None:
    from forager_ai.ai import assistant_commands

    for _alias, route in assistant_commands._NAV_ALIASES.items():
        assert route in _FORAGER_NAV_KEYS, (
            f"/go and natural navigation use unknown key {route!r} — "
            "add it to dashboard FORGER_NAV_LABEL_BY_KEY or fix the alias map."
        )


def test_go_forge_studio_command() -> None:
    from forager_ai.ai.assistant_commands import parse_assistant_command

    r = parse_assistant_command("/go forge_studio", pack_root=".")
    assert r is not None
    assert r.kind == "navigate"
    assert r.nav_route == "forge_studio"
