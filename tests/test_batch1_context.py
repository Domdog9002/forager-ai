"""Batch 1: pack AI context cards, health narrative, crash ticket extras, fact import."""

from __future__ import annotations

import json
from pathlib import Path

from forager_ai.ai.context_snippets import (
    count_top_level_mod_jars,
    lockfile_sha256_hex,
    snippet_lock_json_excerpt,
)
from forager_ai.ai.pack_context import build_pack_ai_context
from forager_ai.analysis.health_score import format_health_narrative
from forager_ai.backend.conflict_resolver import ConflictResolver
from forager_ai.ops.crash_ticket import build_crash_issue_markdown
from forager_ai.pack.manifest import create_default_manifest, save_pack_manifest


def test_format_health_narrative_nonempty() -> None:
    h = {"score": 72, "verdict": "watch", "findings": [{"severity": "medium", "message": "Two performance notes."}]}
    cs = {"total_conflicts": 3}
    t = format_health_narrative(h, cs, max_chars=2000)
    assert "72" in t and "watch" in t and "3" in t


def test_lock_snippets_and_jar_count(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "a.jar").write_bytes(b"x")
    (root / "forager_mods.lock.json").write_text(json.dumps({"x": 1}), encoding="utf-8")
    assert count_top_level_mod_jars(str(root)) == 1
    hx = lockfile_sha256_hex(str(root))
    assert len(hx) == 64
    ex = snippet_lock_json_excerpt(str(root), max_chars=500)
    assert "x" in ex


def test_build_pack_ai_context_includes_batch1_keys(tmp_path: Path, monkeypatch) -> None:
    from forager_ai.ai import user_adaptation as ua

    root = tmp_path / "p"
    root.mkdir()
    save_pack_manifest(str(root), create_default_manifest("tp"))
    cache = tmp_path / "cache"
    cache.mkdir()
    res = ConflictResolver(str(tmp_path / "crdata"))

    def _prof() -> dict:
        d = ua.DEFAULT_PROFILE.copy()
        d["context_card_lock_excerpt"] = True
        d["context_card_trace_tail"] = False
        d["context_card_provenance"] = False
        d["context_card_git_status"] = False
        return d

    monkeypatch.setattr(ua, "load_profile", _prof)
    ctx = build_pack_ai_context(
        pack_root=str(root),
        pack_name="tp",
        resolver=res,
        cache_dir=str(cache),
    )
    assert "health_narrative" in ctx
    assert "confirmed_facts_context" in ctx
    assert "context_cards_bundle" in ctx
    assert "known_issue_hints" in ctx
    assert isinstance(ctx["health_narrative"], str)
    assert isinstance(ctx["optional_context_snippets"], dict)


def test_build_pack_ai_context_reuses_provided_conflict_scan(tmp_path: Path, monkeypatch) -> None:
    from forager_ai.ai import pack_context as pc
    from forager_ai.ai import user_adaptation as ua

    root = tmp_path / "p"
    root.mkdir()
    save_pack_manifest(str(root), create_default_manifest("tp"))
    res = ConflictResolver(str(tmp_path / "crdata"))
    monkeypatch.setattr(ua, "load_profile", lambda: ua.DEFAULT_PROFILE.copy())
    calls = {"n": 0}
    original = pc.build_conflict_scan_report

    def _spy(*args, **kwargs):
        calls["n"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(pc, "build_conflict_scan_report", _spy)
    preset = {
        "mods": [],
        "conflicts": [],
        "summary": {"total_conflicts": 0, "highest_severity": "none"},
        "resolution_plan": {"auto_resolved": [], "manual_actions_required": []},
    }
    build_pack_ai_context(
        pack_root=str(root),
        pack_name="tp",
        resolver=res,
        conflict_scan=preset,
    )
    assert calls["n"] == 0


def test_build_crash_issue_markdown_embeds_optional_blocks() -> None:
    md = build_crash_issue_markdown(
        summary="boom",
        log_tail="at tail line",
        lock_digest="ab" * 32,
        mod_jar_count=12,
        provenance_brief="- mr `p` → f.jar",
        known_issue_hints="- `dup` (medium): hint",
    )
    assert "boom" in md
    assert "at tail line" in md
    assert "ab" in md
    assert "12" in md
    assert "provenance" in md.lower()
    assert "known-issue" in md.lower()


def test_import_facts_from_lines(tmp_path: Path, monkeypatch) -> None:
    from forager_ai.ai import enhancement_store as es

    monkeypatch.setattr(es, "FACTS_PATH", tmp_path / "facts.json")
    n = es.import_facts_from_lines(" alpha \n\nbeta here\n", pack_key="")
    assert n == 2
    facts = es.list_facts(pack_key=None)
    assert len(facts) == 2
