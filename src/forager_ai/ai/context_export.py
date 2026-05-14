"""Plain-text export of pack AI context (Batch 3)."""

from __future__ import annotations

import json
from typing import Any, Dict, List


def retrieval_export_appendix_present(ctx: Dict[str, Any]) -> bool:
    """True when hub / caller attached non-empty retrieval cites or meta (embedding or keyword path)."""
    cites = ctx.get("retrieval_citations")
    meta = ctx.get("retrieval_meta")
    if isinstance(cites, list) and len(cites) > 0:
        return True
    if isinstance(meta, dict) and len(meta) > 0:
        return True
    return False


def _slim_citation_row(row: Any) -> Dict[str, Any]:
    if not isinstance(row, dict):
        return {"raw": str(row)[:520]}
    out: Dict[str, Any] = {}
    for k in ("path", "score", "blended", "keyword_prefilter"):
        if k in row:
            v = row[k]
            out[k] = v if isinstance(v, (bool, int, float)) else str(v)[:900]
    return out or {"path": str(row.get("path", ""))[:900]}


def format_retrieval_export_text_appendix(
    ctx: Dict[str, Any],
    *,
    max_cite_rows: int = 28,
    max_meta_chars: int = 6000,
) -> str:
    if not retrieval_export_appendix_present(ctx):
        return ""
    cites = ctx.get("retrieval_citations") if isinstance(ctx.get("retrieval_citations"), list) else []
    meta = ctx.get("retrieval_meta") if isinstance(ctx.get("retrieval_meta"), dict) else {}
    lines: List[str] = [
        "## retrieval_appendix",
        "",
        "_Notebook / corpus citations and diagnostics from the last hub retrieval that was merged into this export._",
        "",
        "### retrieval_citations",
        "",
    ]
    for row in cites[:max_cite_rows]:
        sr = _slim_citation_row(row)
        lines.append(f"- {json.dumps(sr, ensure_ascii=True)[:920]}")
    if len(cites) > max_cite_rows:
        lines.append(f"- … ({len(cites) - max_cite_rows} more row(s) omitted)")
    lines.extend(["", "### retrieval_meta", ""])
    meta_blob = json.dumps(meta, indent=2, ensure_ascii=True)
    if len(meta_blob) > max_meta_chars:
        meta_blob = meta_blob[: max_meta_chars - 40] + "\n… (meta truncated)\n"
    lines.append(meta_blob)
    return "\n".join(lines).strip()


def build_pack_ai_context_export_text(ctx: Dict[str, Any], *, max_total_chars: int = 120_000) -> str:
    """Human-readable bundle for tickets / Council / support threads (no secrets)."""
    parts: list[str] = [
        "# Forager AI — pack context export",
        "",
        f"pack_name: {ctx.get('pack_name')}",
        "",
        "## health_narrative",
        str(ctx.get("health_narrative") or "").strip(),
        "",
        "## confirmed_facts_context",
        str(ctx.get("confirmed_facts_context") or "").strip(),
        "",
        "## context_cards_bundle",
        str(ctx.get("context_cards_bundle") or "").strip(),
        "",
        "## known_issue_hints",
        str(ctx.get("known_issue_hints") or "").strip(),
        "",
        "## authoring_brief_narrative",
        str(ctx.get("authoring_brief_narrative") or "").strip(),
        "",
        "## decision_log_narrative",
        str(ctx.get("decision_log_narrative") or "").strip(),
        "",
        "## golden_prompts_narrative",
        str(ctx.get("golden_prompts_narrative") or "").strip(),
        "",
        "## reference_pair_diff_narrative",
        str(ctx.get("reference_pair_diff_narrative") or "").strip(),
        "",
        "## conflict_scan.summary",
        json.dumps((ctx.get("conflict_scan") or {}).get("summary") or {}, indent=2, ensure_ascii=True),
        "",
        "## health_score",
        json.dumps(ctx.get("health_score") or {}, indent=2, ensure_ascii=True)[:8000],
        "",
        "## git_working_tree (truncated in source)",
        str(ctx.get("git_working_tree") or "")[:12000],
        "",
    ]
    _rag_txt = format_retrieval_export_text_appendix(ctx)
    if _rag_txt:
        parts.extend(["", _rag_txt, ""])
    blob = "\n".join(parts).strip()
    if len(blob) > max_total_chars:
        return blob[: max_total_chars - 40] + "\n… (export truncated)\n"
    return blob


def build_pack_ai_context_export_json(ctx: Dict[str, Any], *, max_json_chars: int = 80_000) -> str:
    """Structured subset for tooling (still no API secrets)."""
    snips = ctx.get("optional_context_snippets") or {}
    slim_snips: Dict[str, str] = {}
    if isinstance(snips, dict):
        for k, v in list(snips.items())[:28]:
            slim_snips[str(k)[:80]] = str(v)[:950]
    obj: Dict[str, Any] = {
        "pack_name": ctx.get("pack_name"),
        "health_narrative": str(ctx.get("health_narrative") or "")[:6000],
        "confirmed_facts_context": str(ctx.get("confirmed_facts_context") or "")[:4000],
        "context_cards_bundle": str(ctx.get("context_cards_bundle") or "")[:8000],
        "known_issue_hints": str(ctx.get("known_issue_hints") or "")[:4000],
        "authoring_brief_narrative": str(ctx.get("authoring_brief_narrative") or "")[:4500],
        "decision_log_narrative": str(ctx.get("decision_log_narrative") or "")[:4500],
        "golden_prompts_narrative": str(ctx.get("golden_prompts_narrative") or "")[:4500],
        "reference_pair_diff_narrative": str(ctx.get("reference_pair_diff_narrative") or "")[:5200],
        "conflict_scan_summary": (ctx.get("conflict_scan") or {}).get("summary") or {},
        "health_score": ctx.get("health_score") or {},
        "optional_context_snippets": slim_snips,
    }
    _abrief = ctx.get("authoring_brief")
    if isinstance(_abrief, dict):
        obj["authoring_brief"] = {str(k)[:80]: str(v)[:2000] for k, v in list(_abrief.items())[:24]}
    _dlog = ctx.get("decision_log_recent")
    if isinstance(_dlog, list) and _dlog:
        slim_d: List[Any] = []
        for row in _dlog[-14:]:
            if isinstance(row, dict):
                slim_d.append(
                    {
                        "ts": str(row.get("ts") or "")[:40],
                        "confirmed_by": str(row.get("confirmed_by") or "")[:80],
                        "summary": str(row.get("summary") or "")[:800],
                    }
                )
        obj["decision_log_recent"] = slim_d
    _gpl = ctx.get("golden_prompts")
    if isinstance(_gpl, list) and _gpl:
        obj["golden_prompts"] = [str(x)[:900] for x in _gpl[:40]]
    if retrieval_export_appendix_present(ctx):
        cites = ctx.get("retrieval_citations") if isinstance(ctx.get("retrieval_citations"), list) else []
        meta = ctx.get("retrieval_meta") if isinstance(ctx.get("retrieval_meta"), dict) else {}
        obj["retrieval_citations"] = [_slim_citation_row(r) for r in cites[:36]]
        if len(cites) > 36:
            obj["retrieval_citations_truncated"] = True
        def _meta_val(v: Any) -> Any:
            if isinstance(v, (bool, int, float)) or v is None:
                return v
            if isinstance(v, str):
                return v[:1200]
            try:
                s = json.dumps(v, ensure_ascii=True)
                return s[:1200]
            except (TypeError, ValueError):
                return str(v)[:1200]

        meta_trim = dict(list(meta.items())[:40])
        obj["retrieval_meta"] = {str(k)[:120]: _meta_val(v) for k, v in meta_trim.items()}
    raw = json.dumps(obj, indent=2, ensure_ascii=True)
    if len(raw) > max_json_chars:
        return raw[: max_json_chars - 40] + "\n"
    return raw
