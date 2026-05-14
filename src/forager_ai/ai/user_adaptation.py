"""
Lightweight per-user adaptation for AI calls: verbosity, topics, optional notes.

Stored in ~/.forager_ai/user_profile.json (UTF-8, no BOM). No cloud; local only.
"""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List

PROFILE_VERSION = 1

DEFAULT_PROFILE: Dict[str, Any] = {
    "version": PROFILE_VERSION,
    "verbosity": "normal",  # brief | normal | detailed
    "exchanges": 0,
    "topic_ring": [],
    "inferred_tags": [],
    "user_notes": "",
    "cite_sources": True,
    "state_assumptions": True,
    "skeptical_mode": False,
    # Optional pack AI context cards (see build_pack_ai_context)
    "context_card_lock_excerpt": True,
    "context_card_trace_tail": True,
    "context_card_provenance": True,
    "context_card_git_status": False,
    "context_card_env_fingerprint": False,
    "context_card_instance_preflight": False,
    "context_card_jvm_hints": False,
    "context_card_asset_audit": False,
    "context_card_known_issues": False,
}


def _profile_path() -> Path:
    base = Path.home() / ".forager_ai"
    base.mkdir(parents=True, exist_ok=True)
    return base / "user_profile.json"


def load_profile() -> Dict[str, Any]:
    path = _profile_path()
    if not path.is_file():
        return deepcopy(DEFAULT_PROFILE)
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return deepcopy(DEFAULT_PROFILE)
    except (OSError, json.JSONDecodeError, UnicodeError):
        return deepcopy(DEFAULT_PROFILE)
    out = deepcopy(DEFAULT_PROFILE)
    for k, v in DEFAULT_PROFILE.items():
        if k not in data:
            continue
        if k in ("topic_ring", "inferred_tags") and isinstance(data[k], list):
            out[k] = [str(x)[:120] for x in data[k][:30] if str(x).strip()]
        elif k == "verbosity" and str(data[k]).lower() in ("brief", "normal", "detailed"):
            out[k] = str(data[k]).lower()
        elif k == "exchanges":
            try:
                out[k] = max(0, int(data[k]))
            except (TypeError, ValueError):
                pass
        elif k == "user_notes" and isinstance(data[k], str):
            out[k] = data[k][:2000]
        elif k in ("cite_sources", "state_assumptions", "skeptical_mode") and isinstance(data[k], bool):
            out[k] = bool(data[k])
        elif str(k).startswith("context_card_") and isinstance(data[k], bool):
            out[k] = bool(data[k])
        elif k == "version":
            out[k] = int(data.get("version", PROFILE_VERSION))
    return out


def save_profile(profile: Dict[str, Any]) -> None:
    path = _profile_path()
    profile = dict(profile)
    profile["version"] = PROFILE_VERSION
    try:
        path.write_text(json.dumps(profile, ensure_ascii=True, indent=2), encoding="utf-8")
    except OSError:
        pass


def reset_learning_keep_notes() -> None:
    p = load_profile()
    p["exchanges"] = 0
    p["topic_ring"] = []
    p["inferred_tags"] = []
    save_profile(p)


def _squish(s: str, n: int) -> str:
    t = " ".join((s or "").split())
    return t if len(t) <= n else t[: n - 1] + "…"


def _bump_topic_ring(profile: Dict[str, Any], phrase: str) -> None:
    ring: List[str] = profile.get("topic_ring") or []
    if not isinstance(ring, list):
        ring = []
    p = _squish(phrase, 96)
    if not p:
        return
    if ring and ring[-1] == p:
        return
    ring.append(p)
    profile["topic_ring"] = ring[-25:]


def _infer_tags(lower: str, profile: Dict[str, Any]) -> None:
    tags: List[str] = list(profile.get("inferred_tags") or [])
    hints = [
        ("kubejs", r"\bkube\s*js\b|kubejs"),
        ("performance", r"\b(fps|lag|stutter|tps|mspt|performance|optimize)\b"),
        ("crashes", r"\b(crash|exception|stack\s*trace|error)\b"),
        ("create", r"\bcreate\s*(mod)?\b"),
        ("kubejs_scripts", r"\b(script|server_scripts|startup_scripts)\b"),
        ("datapack", r"\b(datapack|data\s*pack)\b"),
        ("fabric", r"\bfabric\b"),
        ("forge", r"\bforge\b"),
    ]
    for label, pat in hints:
        if re.search(pat, lower, re.I) and label not in tags:
            tags.append(label)
    profile["inferred_tags"] = tags[-12:]


def observe_user_message(text: str) -> None:
    """Update inferred preferences from phrasing (brief, detailed, etc.)."""
    t = (text or "").strip()
    if not t:
        return
    lower = t.lower()
    profile = load_profile()
    changed = False
    if re.search(r"\b(brief|short answer|tl;dr|be concise|too long)\b", lower):
        profile["verbosity"] = "brief"
        changed = True
    elif re.search(
        r"\b(more detail|explain (more|thoroughly)|step by step|walk me through|verbose)\b",
        lower,
    ):
        profile["verbosity"] = "detailed"
        changed = True
    _infer_tags(lower, profile)
    if changed or profile.get("inferred_tags"):
        save_profile(profile)


def observe_assistant_exchange(*, user_message: str, assistant_preview: str, pack_name: str = "") -> None:
    """Record that an exchange happened; ring-buffer topics for future context."""
    from .enhancement_store import append_pack_topic

    profile = load_profile()
    try:
        profile["exchanges"] = int(profile.get("exchanges") or 0) + 1
    except (TypeError, ValueError):
        profile["exchanges"] = 1
    um = _squish(user_message, 200)
    if um:
        topic = um
        if pack_name:
            topic = f"[{pack_name}] {topic}"
        _bump_topic_ring(profile, topic)
        if pack_name.strip():
            append_pack_topic(pack_name.strip(), um)
    save_profile(profile)


def adaptation_context_for_prompt(max_chars: int = 1000) -> str:
    """Compact block for system/user context injection."""
    if max_chars < 80:
        return ""
    p = load_profile()
    parts: List[str] = []
    v = str(p.get("verbosity") or "normal").lower()
    if v not in ("brief", "normal", "detailed"):
        v = "normal"
    parts.append(f"User assist preference: reply with {v} detail unless the task demands otherwise.")

    notes = str(p.get("user_notes") or "").strip()
    if notes:
        parts.append(f"User-stated notes for assistants: {notes[:800]}")

    if p.get("skeptical_mode"):
        parts.append(
            "User enabled **skeptical assistant**: you may disagree when a proposed pack/launcher step is risky; "
            "give a short evidence-based objection and a safer path—avoid performative contrarianism."
        )

    tags = p.get("inferred_tags") or []
    if isinstance(tags, list) and tags:
        parts.append("Inferred recurring interests (heuristic): " + ", ".join(str(x) for x in tags[:12]))

    ring = p.get("topic_ring") or []
    if isinstance(ring, list) and ring:
        tail = ring[-8:]
        parts.append("Recent question topics (newest last):\n- " + "\n- ".join(_squish(str(x), 140) for x in tail))

    ex = p.get("exchanges")
    try:
        exchanges = int(ex)
    except (TypeError, ValueError):
        exchanges = 0
    if exchanges > 0:
        parts.append(f"Prior assist exchanges in Forager (approx): {min(exchanges, 9999)}.")

    blob = "\n\n".join(parts).strip()
    if len(blob) <= max_chars:
        return blob
    return blob[: max_chars - 1] + "…"


HUMAN_LIKE_COMMANDS = """
How to read user input (human-like):
- Treat instructions as a teammate would: infer goals behind short or messy wording; combine multiple asks when the user bundles them.
- Prefer concrete modpack/launcher actions (paths, versions, configs, logs) over generic Minecraft trivia unless they asked for trivia.
- If a detail is missing but a reasonable default exists for modded Forge packs, say the assumption in one short phrase and continue.
- If the request is unsafe or could delete work, slow down and spell out the risk first.
""".strip()


def merge_adaptation_into_lessons(base: str, budget: int) -> str:
    """Append adaptation summary to prior_lessons blob without duplicating council content."""
    ada = adaptation_context_for_prompt(min(1200, max(400, budget // 6)))
    if not ada.strip():
        return base[:budget]
    if not (base or "").strip():
        return ada[:budget]
    merged = f"{base.strip()}\n\n[User adaptation]\n{ada.strip()}"
    return merged[:budget]
