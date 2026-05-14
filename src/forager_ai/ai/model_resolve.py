"""Map AI model preset (fast / balanced / quality) to a concrete OpenRouter model id."""

from __future__ import annotations

from typing import Any, Dict


def resolve_ai_model(cfg: Dict[str, Any]) -> str:
    """Return model string for chat completions based on preset + per-tier overrides."""
    preset = str(cfg.get("ai_model_preset") or "quality").strip().lower()
    if preset not in ("fast", "balanced", "quality"):
        preset = "balanced"
    fallback = str(cfg.get("ai_model") or "openai/gpt-4o").strip() or "openai/gpt-4o"
    if preset == "fast":
        return str(cfg.get("ai_model_fast") or fallback).strip() or fallback
    if preset == "quality":
        return str(cfg.get("ai_model_quality") or fallback).strip() or fallback
    balanced = str(cfg.get("ai_model_balanced") or "").strip()
    return balanced or fallback


def resolve_council_model(cfg: Dict[str, Any]) -> str:
    """Model for multi-pass Council: optional override, else quality-tier model (fallback: main ai_model)."""
    explicit = str(cfg.get("ai_model_council") or "").strip()
    if explicit:
        return explicit
    fallback = str(cfg.get("ai_model") or "openai/gpt-4o").strip() or "openai/gpt-4o"
    quality = str(cfg.get("ai_model_quality") or "").strip()
    return quality or fallback
