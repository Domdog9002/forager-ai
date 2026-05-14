from __future__ import annotations

from typing import Any, Dict, List, Optional

from ..analysis.health_score import build_pack_health_score, format_health_narrative
from ..analysis.mod_roles import classify_mods, summarize_roles
from ..analysis.progression import audit_progression
from ..backend.conflict_resolver import ConflictResolver
from ..backend.conflict_scan import build_conflict_scan_report
from ..diagnostics.asset_audit import build_mods_asset_audit, format_asset_audit_for_context
from ..diagnostics.env_fingerprint import format_env_fingerprint_text
from ..diagnostics.instance_preflight import build_launch_target_preflight_report, format_preflight_narrative
from ..diagnostics.known_issues import (
    build_known_issues_probe_text,
    format_known_issue_hits,
    match_known_issues,
)
from ..diagnostics.performance import profile_pack
from ..pack.authoring_memory import (
    format_authoring_brief_for_context,
    format_decision_log_for_context,
    format_golden_prompts_for_context,
    load_authoring_brief,
    load_golden_prompts,
    load_recent_decisions,
)
from ..pack.compat_registry import list_compat_rules
from ..pack.manifest import load_pack_manifest
from .assistant_voice import build_retained_context_for_ai
from .context_snippets import (
    snippet_git_name_status_for_pack,
    snippet_jvm_hints_text,
    snippet_lock_json_excerpt,
    snippet_provenance_compact,
    snippet_trace_tail_text,
)
from .enhancement_store import build_pack_enrichment_for_ai, facts_context_for_prompt
from .git_context import pack_git_summary
from .user_adaptation import load_profile


def build_pack_ai_context(
    *,
    pack_root: str,
    pack_name: str,
    resolver: ConflictResolver,
    selected_mod: Optional[Dict[str, Any]] = None,
    include_performance: bool = True,
    council_lesson_chars: int = 3000,
    cache_dir: Optional[str] = None,
    launcher: Optional[Any] = None,
    game_root: Optional[str] = None,
    conflict_scan: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a compact reusable context object for all pack-aware AI modes."""
    manifest = load_pack_manifest(pack_root)
    if conflict_scan is None:
        conflict_scan = build_conflict_scan_report(
            resolver=resolver,
            manifest=manifest,
            pack_root=pack_root,
            pack_name=pack_name,
            auto_resolve=True,
        )
    compat_rules = list_compat_rules(pack_root)
    role_items = classify_mods(conflict_scan.get("mods") or [])
    role_summary = summarize_roles(role_items)
    perf = profile_pack(pack_root) if include_performance else {}
    health = build_pack_health_score(
        manifest=manifest,
        conflict_summary=conflict_scan.get("summary") or {},
        performance_report=perf,
        compat_rules_count=len(compat_rules),
        role_summary=role_summary,
    )
    progression = audit_progression(
        manifest=manifest,
        pack_root=pack_root,
        compat_rules=compat_rules,
    )
    profile = load_profile()
    facts_ctx = facts_context_for_prompt(pack_name, max_chars=1600)
    health_narrative = format_health_narrative(health, conflict_scan.get("summary") or {}, max_chars=1700)
    snippets: Dict[str, str] = {}
    card_parts: List[str] = []
    bundle_max = 10000

    if profile.get("context_card_lock_excerpt", True):
        s = snippet_lock_json_excerpt(pack_root)
        if s:
            snippets["lock_excerpt"] = s
            card_parts.append("[Lockfile excerpt]\n" + s)
    if profile.get("context_card_trace_tail", True):
        s = snippet_trace_tail_text(pack_root)
        if s:
            snippets["trace_tail"] = s
            card_parts.append(s)
    if profile.get("context_card_provenance", True) and (cache_dir or "").strip():
        s = snippet_provenance_compact(str(cache_dir).strip())
        if s:
            snippets["provenance"] = s
            card_parts.append(s)
    if profile.get("context_card_git_status", False):
        s = snippet_git_name_status_for_pack(pack_root)
        if s:
            snippets["git_name_status"] = s
            card_parts.append("[Git name-status]\n" + s)
    if profile.get("context_card_env_fingerprint", False):
        s = format_env_fingerprint_text(max_chars=900)
        if s:
            snippets["env_fingerprint"] = s
            card_parts.append(s)
    gr = str(game_root or "").strip()
    if profile.get("context_card_instance_preflight", False) and gr and launcher is not None:
        try:
            mc_v = str((manifest or {}).get("minecraft_version") or "1.20.1")
            lo_v = str((manifest or {}).get("loader") or "forge")
            rep = build_launch_target_preflight_report(
                game_root=gr,
                label=pack_name,
                minecraft_version=mc_v,
                loader=lo_v,
                launcher=launcher,
                conflict_resolver=resolver,
                telemetry_enabled=bool(launcher.config.get("preflight_telemetry_enabled", False)),
                telemetry_include_paths=bool(launcher.config.get("preflight_telemetry_include_paths", False)),
            )
            pn = format_preflight_narrative(rep, max_chars=1700)
            if pn:
                snippets["instance_preflight"] = pn
                card_parts.append(pn)
        except Exception:
            pass

    if profile.get("context_card_jvm_hints", False) and launcher is not None:
        s = snippet_jvm_hints_text(launcher, max_chars=1100)
        if s:
            snippets["jvm_hints"] = s
            card_parts.append(s)
    if profile.get("context_card_asset_audit", False):
        try:
            aud = build_mods_asset_audit(str(pack_root).strip(), max_files=350)
            s = format_asset_audit_for_context(aud, max_chars=1500)
            if s:
                snippets["asset_audit"] = s
                card_parts.append(s)
        except Exception:
            pass

    _brief_raw = load_authoring_brief(pack_root)
    _brief_narrative = format_authoring_brief_for_context(_brief_raw)
    _dec_entries = load_recent_decisions(pack_root, max_entries=18)
    _dec_narrative = format_decision_log_for_context(_dec_entries)
    _gp_raw = load_golden_prompts(pack_root)
    _gp_pr = _gp_raw.get("prompts") if isinstance(_gp_raw, dict) else []
    _gp_list = list(_gp_pr) if isinstance(_gp_pr, list) else []
    _gp_narrative = format_golden_prompts_for_context(_gp_list)

    kn_hints = ""
    if profile.get("context_card_known_issues", False):
        probe = build_known_issues_probe_text(
            pack_name=pack_name,
            mods=conflict_scan.get("mods") or [],
            conflicts=(conflict_scan.get("conflicts") or [])[:25],
            progression_findings=progression.get("findings") or [],
        )
        if probe.strip():
            hits = match_known_issues(probe)
            kn_hints = format_known_issue_hits(hits)
            if kn_hints:
                snippets["known_issues"] = kn_hints
                card_parts.append(kn_hints)

    cards_blob = "\n\n---\n\n".join(card_parts).strip()
    if len(cards_blob) > bundle_max:
        cards_blob = cards_blob[: bundle_max - 32] + "\n… (context cards truncated)"

    return {
        "pack_name": pack_name,
        "manifest": manifest,
        "conflict_scan": {
            "summary": conflict_scan.get("summary"),
            "conflicts": (conflict_scan.get("conflicts") or [])[:30],
            "resolution_plan": conflict_scan.get("resolution_plan"),
        },
        "performance": {
            "summary": perf.get("summary", {}),
            "findings": (perf.get("findings") or [])[:20],
        },
        "compat_rules": compat_rules[:50],
        "mod_roles": {
            "summary": role_summary,
            "items": role_items[:120],
        },
        "progression": progression,
        "health_score": health,
        "health_narrative": health_narrative,
        "confirmed_facts_context": facts_ctx,
        "context_cards_bundle": cards_blob,
        "optional_context_snippets": snippets,
        "known_issue_hints": kn_hints,
        "selected_mod": selected_mod,
        "retained_ai_context": build_retained_context_for_ai(max(council_lesson_chars, 2000)),
        "pack_enrichment": build_pack_enrichment_for_ai(pack_name, 2800),
        "git_working_tree": pack_git_summary(pack_root)[:4000],
        "authoring_brief": _brief_raw,
        "authoring_brief_narrative": _brief_narrative,
        "decision_log_recent": _dec_entries,
        "decision_log_narrative": _dec_narrative,
        "golden_prompts": _gp_list,
        "golden_prompts_narrative": _gp_narrative,
    }
