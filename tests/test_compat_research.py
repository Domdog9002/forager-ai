"""Offline tests for compat research text helpers."""

from __future__ import annotations

from forager_ai.tools.compat_research import summarize_project_for_compat


def test_summarize_project_for_compat_basic() -> None:
    text = summarize_project_for_compat(
        {
            "title": "Test Mod",
            "slug": "test-mod",
            "description": "Does things.",
            "categories": ["utility"],
            "loaders": ["forge"],
            "game_versions": ["1.20.1"],
            "issues_url": "https://example.invalid/issues",
            "source_url": "",
        }
    )
    assert "Test Mod" in text
    assert "test-mod" in text
    assert "forge" in text
