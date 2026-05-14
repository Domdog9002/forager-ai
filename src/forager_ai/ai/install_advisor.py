from __future__ import annotations

import json
from typing import Any, Dict

import requests

from .artifacts import make_ai_artifact
from .assistant_voice import append_interaction_memory, augment_user_facing_system
from .openrouter_client import DEFAULT_MODEL, _extract_json, chat_completion_text


def deterministic_install_advice(preflight: Dict[str, Any]) -> Dict[str, Any]:
    decision = str(preflight.get("decision") or "allow")
    conflicts = preflight.get("conflicts") or []
    reasons = [
        f"{item.get('severity', 'low')} {item.get('type', 'finding')}: {item.get('description', '')}"
        for item in conflicts[:6]
    ]
    if not reasons:
        reasons = ["No conflict findings were detected by preflight."]
    if decision == "block":
        recommendation = "Do not install until the critical findings are fixed or manually accepted."
    elif decision == "warn":
        recommendation = "Install only after reviewing the findings and saving any useful compat rules."
    else:
        recommendation = "Install is safe based on current metadata."
    return {
        "decision": decision,
        "recommendation": recommendation,
        "reasons": reasons,
        "suggested_actions": [item.get("suggested_resolution", "Review manually.") for item in conflicts[:6]],
    }


def generate_install_advice(
    *,
    preflight: Dict[str, Any],
    pack_context: Dict[str, Any],
    api_key: str = "",
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    base = deterministic_install_advice(preflight)
    if api_key.strip():
        system = augment_user_facing_system(
            "You are Forager AI Install Advisor for Minecraft Forge 1.20.1 packs. "
            "Return JSON only: {\"decision\":\"allow|warn|block\",\"recommendation\":\"string\","
            "\"reasons\":[\"string\"],\"suggested_actions\":[\"string\"]}. "
            "Use only provided metadata and stay concise."
        )
        user = json.dumps({"preflight": preflight, "pack_context": pack_context}, ensure_ascii=True)
        try:
            raw = chat_completion_text(
                api_key=api_key,
                system_prompt=system,
                user_text=user,
                model=model,
                temperature=0.15,
                timeout_s=80,
            )
            parsed = _extract_json(raw)
            if isinstance(parsed.get("reasons"), list):
                base.update(parsed)
                append_interaction_memory(
                    source="install_advisor",
                    pack_name=str(pack_context.get("pack_name") or ""),
                    summary=str(base.get("recommendation") or ""),
                )
        except (ValueError, json.JSONDecodeError, requests.RequestException, KeyError, OSError):
            pass
    return make_ai_artifact(
        artifact_type="forager_install_advisor",
        pack_name=str(pack_context.get("pack_name") or "unknown"),
        title="Install Advisor",
        summary=str(base.get("recommendation") or ""),
        payload={"advice": base, "preflight": preflight},
    )
