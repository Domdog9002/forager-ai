"""Streamlit layout recipes aligned with DESIGN.md (elevated panels, splits, AI lab)."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Generator, Tuple

import streamlit as st


@contextmanager
def workspace_shell() -> Generator[None, None, None]:
    """Bordered zinc workspace shell (Power Center pattern)."""
    try:
        outer = st.container(border=True)
    except TypeError:
        outer = st.container()
    with outer:
        st.markdown('<div class="forager-workspace-shell" aria-hidden="true"></div>', unsafe_allow_html=True)
        yield


@contextmanager
def elevated_section() -> Generator[None, None, None]:
    """Bordered elevated panel; falls back to a plain container on older Streamlit."""
    try:
        outer = st.container(border=True)
    except TypeError:
        outer = st.container()
    with outer:
        yield


def columns_equal(n: int, *, gap: str = "medium") -> Tuple[object, ...]:
    """N equal-width columns (quick action grids, symmetric forms)."""
    if n < 1:
        raise ValueError("n must be >= 1")
    return tuple(st.columns([1.0] * n, gap=gap))


def columns_main_side(*, main: float = 2.2, side: float = 1.0, gap: str = "medium"):
    """List + detail or hero + side rail."""
    return st.columns([main, side], gap=gap)


def columns_ai_lab(*, gap: str = "medium"):
    """Primary workspace + context column (~60/40)."""
    return st.columns([1.55, 1.0], gap=gap)
