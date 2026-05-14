"""Batch 3: JVM + asset audit cards, context export, crash ticket extras, support bundle."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from forager_ai.ai.context_export import (
    build_pack_ai_context_export_json,
    build_pack_ai_context_export_text,
    retrieval_export_appendix_present,
)
from forager_ai.diagnostics.asset_audit import build_mods_asset_audit, format_asset_audit_for_context
from forager_ai.ops.crash_ticket import build_crash_issue_markdown
from forager_ai.ops.support_bundle import build_support_bundle_zip_bytes


def test_format_asset_audit_for_context_nonempty(tmp_path: Path) -> None:
    root = tmp_path / "g"
    m = root / "mods"
    m.mkdir(parents=True)
    (m / "a.jar").write_bytes(b"x" * 100)
    rep = build_mods_asset_audit(str(root), max_files=50)
    t = format_asset_audit_for_context(rep, max_chars=2000)
    assert "100" in t or "a.jar" in t


def test_retrieval_appendix_exports_when_present() -> None:
    cites = [{"path": "notes/a.md", "score": "0.91"}]
    meta = {"mode": "hybrid"}
    ctx = {
        "pack_name": "p",
        "health_narrative": "",
        "confirmed_facts_context": "",
        "context_cards_bundle": "",
        "conflict_scan": {"summary": {}},
        "health_score": {},
        "git_working_tree": "",
        "retrieval_citations": cites,
        "retrieval_meta": meta,
    }
    assert retrieval_export_appendix_present(ctx)
    txt = build_pack_ai_context_export_text(ctx, max_total_chars=50_000)
    assert "retrieval_appendix" in txt
    assert "notes/a.md" in txt
    raw = build_pack_ai_context_export_json(ctx, max_json_chars=50_000)
    o = json.loads(raw)
    assert isinstance(o.get("retrieval_citations"), list) and o["retrieval_citations"]
    assert o.get("retrieval_meta", {}).get("mode") == "hybrid"


def test_build_pack_ai_context_export_text_truncates() -> None:
    big = "x" * 2000
    ctx = {
        "pack_name": "p",
        "health_narrative": big,
        "confirmed_facts_context": "",
        "context_cards_bundle": "",
        "conflict_scan": {"summary": {}},
        "health_score": {"score": 1},
        "git_working_tree": "",
    }
    out = build_pack_ai_context_export_text(ctx, max_total_chars=500)
    assert len(out) <= 520
    assert "p" in out


def test_crash_ticket_jvm_and_asset_sections() -> None:
    md = build_crash_issue_markdown(
        summary="s",
        jvm_hints_brief="-Xmx note",
        asset_audit_brief="[Mods asset audit]\njar",
    )
    assert "JVM" in md
    assert "asset" in md.lower()


def test_support_bundle_includes_audit_and_jvm(tmp_path: Path) -> None:
    root = tmp_path / "g"
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "z.jar").write_bytes(b"1")
    cache = tmp_path / "c"
    cache.mkdir()
    z = build_support_bundle_zip_bytes(str(root), str(cache))
    zf = zipfile.ZipFile(io.BytesIO(z))
    names = zf.namelist()
    assert "mods_asset_audit.json" in names
    assert "jvm_hints.txt" in names
    aud = json.loads(zf.read("mods_asset_audit.json").decode("utf-8"))
    assert aud.get("jar_count", 0) >= 1
