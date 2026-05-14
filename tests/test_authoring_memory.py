"""Authoring brief + decision log helpers under .forager/."""

from __future__ import annotations

import json
from pathlib import Path

from forager_ai.pack.authoring_memory import (
    append_decision_log,
    format_authoring_brief_for_context,
    format_decision_log_for_context,
    format_golden_prompts_for_context,
    load_authoring_brief,
    load_golden_prompts,
    load_recent_decisions,
    save_authoring_brief,
    save_golden_prompts,
)


def test_authoring_brief_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "pack"
    (root / ".forager").mkdir(parents=True)
    save_authoring_brief(
        str(root),
        {
            "goals": " Stable Forge 1.20.1 ",
            "non_goals": "Kitchen-sink",
            "target_audience": "Co-op",
            "today_focus": "Perf",
        },
    )
    loaded = load_authoring_brief(str(root))
    assert loaded["goals"] == "Stable Forge 1.20.1"
    assert "Co-op" in format_authoring_brief_for_context(loaded)


def test_golden_prompts_roundtrip(tmp_path: Path) -> None:
    root = tmp_path / "gp"
    save_golden_prompts(str(root), ["  one  ", "two", "one"])
    lg = load_golden_prompts(str(root))
    assert lg["prompts"] == ["one", "two"]
    assert "one" in format_golden_prompts_for_context(lg["prompts"])


def test_decision_log_append_and_tail(tmp_path: Path) -> None:
    root = tmp_path / "p2"
    append_decision_log(str(root), summary=" Chose mod A ")
    append_decision_log(str(root), summary="Second call")
    ents = load_recent_decisions(str(root), max_entries=10)
    assert len(ents) == 2
    fmt = format_decision_log_for_context(ents)
    assert "Chose mod A" in fmt
    assert "Second call" in fmt
    p = root / ".forager" / "decision_log.jsonl"
    assert p.is_file()
    line = p.read_text(encoding="utf-8").strip().splitlines()[0]
    row = json.loads(line)
    assert "ts" in row
    assert row["summary"] == "Chose mod A"
