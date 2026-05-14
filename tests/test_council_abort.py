"""Council cooperative abort + stepwise helpers."""

from __future__ import annotations

from forager_ai.ai import council as council_mod


def test_run_council_review_should_abort_before_second_reviewer(monkeypatch):
    calls: list[int] = []

    def fake_chat(**kwargs):
        calls.append(1)
        return '{"issues":[],"summary":"ok"}'

    monkeypatch.setattr(council_mod, "chat_completion_text", fake_chat)
    checks = [0]

    def should_abort() -> bool:
        checks[0] += 1
        return checks[0] >= 2

    rep = council_mod.run_council_review(
        api_key="k",
        subject="s",
        artifact={"x": 1},
        model="m",
        should_abort=should_abort,
    )
    assert rep.get("council_aborted") is True
    assert rep.get("memory_stored") is False
    assert "safety" in (rep.get("reviews") or {})
    assert "accuracy" not in (rep.get("reviews") or {})
    assert len(calls) == 1


def test_council_wip_stepwise_smoke(monkeypatch):
    n = [0]

    def fake_chat(**kwargs):
        n[0] += 1
        if "Chair" in kwargs.get("system_prompt", "") or "chair" in kwargs.get("system_prompt", "").lower():
            return (
                '{"final_verdict":"pass","issues":[],"polish":[],"recommended_actions":[],"synthesized_lessons":""}'
            )
        return '{"issues":[],"summary":"ok"}'

    monkeypatch.setattr(council_mod, "chat_completion_text", fake_chat)
    wip = council_mod.council_wip_start(api_key="k", subject="sub", artifact={"a": 1}, model="m")
    for _ in range(len(council_mod.REVIEWERS)):
        council_mod.council_wip_run_next_reviewer(wip)
    assert int(wip["step"]) == len(council_mod.REVIEWERS)
    out = council_mod.council_wip_run_chair_and_finish(wip)
    assert out.get("chair", {}).get("final_verdict") == "pass"
    assert out.get("memory_stored") is True
    assert n[0] == len(council_mod.REVIEWERS) + 1
