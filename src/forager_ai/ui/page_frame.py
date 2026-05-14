"""Shared page chrome: calm intros and empty states (Streamlit + HTML wrappers)."""

from __future__ import annotations

import html
import re
from typing import Optional

import streamlit as st

_SLUG = re.compile(r"[^a-zA-Z0-9_-]+")


def _slug(s: str, *, fallback: str) -> str:
    t = _SLUG.sub("-", (s or "").strip().lower()).strip("-")
    return t[:48] if t else fallback


def _trim_lede(text: str, *, max_chars: int) -> str:
    raw = (text or "").strip()
    if not raw or max_chars <= 0:
        return ""
    if len(raw) <= max_chars:
        return raw
    cut = raw[: max_chars - 1].rstrip()
    if " " in cut:
        cut = cut.rsplit(" ", 1)[0]
    return cut + "…"


def forager_page_intro(
    *,
    headline: str,
    lede: Optional[str] = None,
    anchor: str = "intro",
    lede_max: int = 120,
) -> None:
    """Headline and optional supporting line (uses ``.forager-page-intro`` CSS)."""
    h = html.escape((headline or "Overview").strip())
    d_raw = _trim_lede(str(lede or ""), max_chars=int(lede_max))
    aid = html.escape(_slug(anchor, fallback="intro"), quote=True)
    lede_html = (
        f'<p class="forager-page-intro-lede">{html.escape(d_raw)}</p>' if d_raw else ""
    )
    st.markdown(
        f'<div class="forager-page-intro" id="forager-page-intro-{aid}">'
        f'<p class="forager-page-intro-head">{h}</p>'
        f"{lede_html}</div>",
        unsafe_allow_html=True,
    )


def forager_section_label(text: str) -> None:
    """Sentence-case section label (replaces uppercase kickers)."""
    t = html.escape((text or "").strip())
    if not t:
        return
    st.markdown(f'<p class="forager-section-label">{t}</p>', unsafe_allow_html=True)


def forager_empty_state(*, title: str, body: str, anchor: str = "empty") -> None:
    """Centered empty pattern when a list has no rows (uses ``.forager-empty-state`` CSS)."""
    t = html.escape((title or "Nothing here yet").strip())
    b = html.escape(_trim_lede(str(body or ""), max_chars=200))
    aid = html.escape(_slug(anchor, fallback="empty"), quote=True)
    st.markdown(
        f'<div class="forager-empty-state" id="forager-empty-{aid}">'
        f'<p class="forager-empty-title">{t}</p><p class="forager-empty-body">{b}</p></div>',
        unsafe_allow_html=True,
    )
