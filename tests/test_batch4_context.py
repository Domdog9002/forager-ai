"""Batch 4: known-issue hints, JSON export, support bundle extras."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

from forager_ai.ai.context_export import build_pack_ai_context_export_json
from forager_ai.backend.conflict_resolver import ConflictResolver
from forager_ai.diagnostics.known_issues import (
    build_known_issues_probe_text,
    format_known_issue_hits,
    match_known_issues,
)
from forager_ai.ops.support_bundle import build_support_bundle_zip_bytes


def test_build_known_issues_probe_includes_mod_ids() -> None:
    probe = build_known_issues_probe_text(
        pack_name="MyPack",
        mods=[{"id": "embeddium", "name": "Embeddium", "file_name": "e.jar"}],
        conflicts=[{"description": "Renderer clash", "type": "x", "affected_mods": ["optifine"]}],
        progression_findings=[{"id": "prog", "message": "note"}],
    )
    assert "embeddium" in probe and "optifine" in probe


def test_format_known_issue_hits_nonempty() -> None:
    hits = [{"id": "t", "severity": "low", "hint": "do a thing"}]
    t = format_known_issue_hits(hits, max_chars=500)
    assert "t" in t and "do a thing" in t


def test_match_known_issues_on_probe() -> None:
    probe = "optifine embeddium forge"
    hits = match_known_issues(probe)
    assert any("optifine" in str(h.get("id", "")).lower() for h in hits)


def test_export_json_contains_pack_name() -> None:
    raw = build_pack_ai_context_export_json({"pack_name": "px", "health_narrative": "h"}, max_json_chars=50_000)
    o = json.loads(raw)
    assert o.get("pack_name") == "px"


def test_support_bundle_memory_and_preflight(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "forager_ai.ops.support_bundle.load_interaction_memory_tail",
        lambda max_chars=8000: "recent session note",
    )
    root = tmp_path / "g"
    (root / "mods").mkdir(parents=True)
    (root / "mods" / "z.jar").write_bytes(b"1")
    cache = tmp_path / "c"
    cache.mkdir()
    cr = ConflictResolver(str(tmp_path / "crdb"))

    class _L:
        config = {"default_memory": 4096}

        def get_system_info(self):
            return {
                "java_installations": [{"path": "java"}],
                "config": {"default_memory": 4096},
                "instances_count": 1,
            }

    z = build_support_bundle_zip_bytes(str(root), str(cache), launcher=_L(), conflict_resolver=cr)
    zf = zipfile.ZipFile(io.BytesIO(z))
    names = zf.namelist()
    assert "interaction_memory_tail.txt" in names
    assert "preflight_snapshot.json" in names
    pre = json.loads(zf.read("preflight_snapshot.json").decode("utf-8"))
    assert "health_score" in pre
