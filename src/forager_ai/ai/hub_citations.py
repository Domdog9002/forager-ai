"""Hub UI helpers for retrieval citation lines (testable without Streamlit)."""

from __future__ import annotations

import html
import json
from typing import Any


def format_hub_retrieval_citation_markdown(row: Any) -> str:
    """
    One markdown bullet for a citation dict, matching the Forager hub expander.
    Caller should only pass ``dict`` rows; non-dicts are handled in the UI separately.
    """
    if not isinstance(row, dict):
        return ""
    ps = html.escape(str(row.get("path", "") or "").replace("`", "")[:760])
    if "blended" in row:
        return (
            f"- `{ps}` · blend **{html.escape(str(row.get('blended')))}** · "
            f"keyword gate **{html.escape(str(row.get('keyword_prefilter', '')))}**"
        )
    if "score" in row:
        return f"- `{ps}` · keyword score **{html.escape(str(row.get('score')))}**"
    return f"- `{ps}` · {html.escape(json.dumps(row, ensure_ascii=True)[:320])}"
