"""Batch 2: env + preflight context, Council overlay wiring."""

from __future__ import annotations

from forager_ai.ai.council import run_council_review
from forager_ai.diagnostics.env_fingerprint import format_env_fingerprint_text
from forager_ai.diagnostics.instance_preflight import format_preflight_narrative


def test_format_preflight_narrative_basic() -> None:
    rep = {
        "label": "Test",
        "game_root": "/tmp/x",
        "health_score": {"score": 80, "verdict": "healthy"},
        "conflict_scan": {"summary": {"total_conflicts": 2}},
        "startup": {"checks": [{"id": "java", "status": "ok", "detail": "1 Java install(s)."}]},
    }
    t = format_preflight_narrative(rep, max_chars=2000)
    assert "80" in t and "2" in t and "java" in t.lower()


def test_format_env_fingerprint_text_nonempty() -> None:
    t = format_env_fingerprint_text(max_chars=2000, timeout_s=4.0)
    assert "python" in t.lower() or "os:" in t.lower()


def test_run_council_review_embeds_overlay(monkeypatch) -> None:
    payloads: list[str] = []
    idx = {"n": 0}

    def _fake_chat(
        *,
        api_key: str,
        system_prompt: str,
        user_text: str,
        model: str = "",
        temperature: float = 0.0,
        timeout_s: int = 30,
        max_tokens: int | None = None,
    ) -> str:
        payloads.append(user_text)
        idx["n"] += 1
        if idx["n"] <= 6:
            return '{"issues":[],"summary":"ok"}'
        return (
            '{"final_verdict":"pass","issues":[],"polish":[],"recommended_actions":[],"synthesized_lessons":""}'
        )

    monkeypatch.setattr("forager_ai.ai.council.chat_completion_text", _fake_chat)
    run_council_review(
        api_key="k",
        subject="subj",
        artifact={"x": 1},
        model="m",
        pack_context_overlay={"pack_name": "demo"},
    )
    assert payloads
    assert any('"pack_context_overlay"' in p for p in payloads)
