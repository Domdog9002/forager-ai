"""user_profile.json merge + skeptical assistant context."""

from __future__ import annotations

from forager_ai.ai import user_adaptation as ua


def test_adaptation_context_includes_skeptical(monkeypatch) -> None:
    def _fake_load() -> dict:
        d = ua.DEFAULT_PROFILE.copy()
        d["skeptical_mode"] = True
        return d

    monkeypatch.setattr(ua, "load_profile", _fake_load)
    blob = ua.adaptation_context_for_prompt(2000)
    assert "skeptical" in blob.lower()


def test_augment_interactive_includes_skeptical_line(monkeypatch) -> None:
    from forager_ai.ai import assistant_voice as av
    from forager_ai.ai import user_adaptation as ua_mod

    def _fake_load() -> dict:
        d = ua_mod.DEFAULT_PROFILE.copy()
        d["skeptical_mode"] = True
        return d

    monkeypatch.setattr(ua_mod, "load_profile", _fake_load)
    out = av.augment_interactive_assistant_system("Pack context here.")
    assert "pushback" in out.lower() or "disagree" in out.lower()
