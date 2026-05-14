"""Regression: hub retrieval citation markdown (Batch 4)."""

from __future__ import annotations

from forager_ai.ai.hub_citations import format_hub_retrieval_citation_markdown


def test_citation_blended_branch() -> None:
    row = {"path": "notes/hi.md", "blended": "0.82", "keyword_prefilter": "ok"}
    md = format_hub_retrieval_citation_markdown(row)
    assert "notes/hi.md" in md
    assert "blend" in md
    assert "0.82" in md
    assert "keyword gate" in md


def test_citation_score_branch() -> None:
    row = {"path": "a/b.txt", "score": "1.2"}
    md = format_hub_retrieval_citation_markdown(row)
    assert "a/b.txt" in md
    assert "keyword score" in md


def test_citation_fallback_json() -> None:
    row = {"path": "x.md", "extra": "y"}
    md = format_hub_retrieval_citation_markdown(row)
    assert "x.md" in md
    assert "extra" in md


def test_citation_escapes_markup_in_path() -> None:
    row = {"path": "<script>x</script>.md", "score": "1"}
    md = format_hub_retrieval_citation_markdown(row)
    assert "<script>" not in md
    assert "&lt;script&gt;" in md


def test_non_dict_returns_empty() -> None:
    assert format_hub_retrieval_citation_markdown("x") == ""
