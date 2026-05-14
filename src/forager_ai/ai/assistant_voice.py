"""
Shared assistant persona and lightweight session memory for pack-aware AI calls.

Session notes are stored under ~/.forager_ai/interaction_memory.jsonl (short summaries only).
Council synthesis continues to use council_memory.jsonl via load_recent_lessons().
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

COMMUNICATION_VOICE = (
    "Tone: supportive and **direct**. Acknowledge frustration when the user hits crashes, conflicts, or confusing errors — "
    "then stay factual. **Do not flatter or agree blindly** when the evidence says otherwise; respectful disagreement beats "
    "performative reassurance. Praise briefly when justified. "
    "You do not have human emotions — do not roleplay intimacy or therapy. "
    "Stay focused on Minecraft, modpacks, and launcher workflows."
)


def augment_user_facing_system(*instruction_blocks: str) -> str:
    """Prefix system prompts for answers the user reads directly (not strict JSON-only pipelines)."""
    body = "\n\n".join(b.strip() for b in instruction_blocks if b and str(b).strip())
    return f"{COMMUNICATION_VOICE}\n\n{body}".strip()


SOURCE_CITATION = (
    "When you cite pack facts, tag the source briefly when possible, e.g. [manifest], [conflict_scan], "
    "[retrieved_docs], [confirmed_facts], [inference]. Keep tags short."
)

ASSUMPTION_LINE = (
    "If you must guess beyond supplied context, add one line starting with **Assumptions:** listing what you inferred."
)

REASONING_DISCIPLINE = (
    "Reasoning discipline: Tie technical claims to the supplied context (mod lists, scan summaries, [retrieved_docs], citations). "
    "When the user's issue could have several causes, list ranked hypotheses with evidence vs. gaps, then give concrete next steps "
    "(which logs or configs to open, safe isolation order). Prefer reversible pack changes; call out Forge 1.20.1 / loader mismatches when relevant. "
    "If the user insists on a risky shortcut, **say so** and steer them to a safer sequence — do not soften just to preserve rapport. "
    "Aim for answers an expert modpack author would accept: complete, ordered, actionable — no filler or cheerleading."
)

SKEPTICAL_ASSIST_LINE = (
    "The user prefers **direct technical pushback** when a plan is likely to harm stability, security, or reproducibility "
    "(wrong loader, skipping backups, bulk-disabling mods, pasting unreviewed scripts). State disagreement briefly with "
    "reasons tied to supplied context, then suggest a safer approach."
)


def augment_interactive_assistant_system(*instruction_blocks: str) -> str:
    """Persona + human-like commands + optional citation/assumption toggles."""
    from .user_adaptation import HUMAN_LIKE_COMMANDS, load_profile

    p = load_profile()
    bundles = [HUMAN_LIKE_COMMANDS, REASONING_DISCIPLINE]
    if p.get("skeptical_mode"):
        bundles.append(SKEPTICAL_ASSIST_LINE)
    if p.get("cite_sources", True):
        bundles.append(SOURCE_CITATION)
    if p.get("state_assumptions", True):
        bundles.append(ASSUMPTION_LINE)
    parts = tuple(bundles) + instruction_blocks
    return augment_user_facing_system(*parts)


def _squish(text: str, max_len: int) -> str:
    t = " ".join((text or "").split())
    if len(t) > max_len:
        return t[: max_len - 1] + "…"
    return t


def _interaction_path() -> Path:
    base = Path.home() / ".forager_ai"
    base.mkdir(parents=True, exist_ok=True)
    return base / "interaction_memory.jsonl"


def append_interaction_memory(
    *,
    source: str,
    summary: str,
    pack_name: str = "",
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Record one short line of context for future AI calls (crash summaries, install outcomes, assistant asks)."""
    text = _squish(summary, 480)
    if not text:
        return
    entry: Dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": (source or "unknown")[:48],
        "pack": (pack_name or "")[:120],
        "summary": text,
    }
    if extra:
        entry["meta"] = {str(k)[:60]: str(v)[:200] for k, v in list(extra.items())[:8]}
    path = _interaction_path()
    try:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=True) + "\n")
    except OSError:
        pass


def _council_lessons(max_chars: int) -> str:
    from .council import load_recent_lessons

    return load_recent_lessons(max_chars)


def load_interaction_memory_tail(max_chars: int = 2000) -> str:
    path = _interaction_path()
    if not path.is_file():
        return ""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    picked: list[str] = []
    total = 0
    for line in reversed(lines[-120:]):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        s = str(obj.get("summary") or "").strip()
        src = str(obj.get("source") or "")
        pk = str(obj.get("pack") or "")
        if not s:
            continue
        chunk = f"- [{src}] {pk + ': ' if pk else ''}{s}"[:620]
        if total + len(chunk) > max_chars:
            break
        picked.append(chunk)
        total += len(chunk)
    return "\n".join(reversed(picked))


def build_retained_context_for_ai(max_chars: int = 4000) -> str:
    """Council lessons, session notes, and per-user adaptation for pack_context / assistant UI."""
    if max_chars < 400:
        max_chars = 400
    from .user_adaptation import adaptation_context_for_prompt

    c_budget = max(200, int(max_chars * 0.38))
    n_budget = max(200, int(max_chars * 0.33))
    a_budget = max(180, max_chars - c_budget - n_budget - 10)
    council = _council_lessons(c_budget)
    notes = load_interaction_memory_tail(n_budget)
    ada = adaptation_context_for_prompt(a_budget)
    parts: list[str] = []
    if council.strip():
        parts.append("[Council synthesis]\n" + council.strip())
    if notes.strip():
        parts.append("[Recent Forager activity]\n" + notes.strip())
    if ada.strip():
        parts.append("[User adaptation]\n" + ada.strip())
    joined = "\n\n".join(parts).strip()
    if len(joined) <= max_chars:
        return joined
    return joined[: max_chars - 1] + "…"


def merged_lessons_for_generation(prior_lessons: str = "", budget: int = 7000) -> str:
    """
    Merge caller-provided lessons (often council-only) with interaction memory without duplicating council.

    If prior_lessons is empty, use full build_retained_context_for_ai (council + notes).
    If prior_lessons is set, treat it as authoritative for council text and append notes only.
    """
    from .user_adaptation import merge_adaptation_into_lessons

    b = max(800, min(int(budget), 12000))
    base = (prior_lessons or "").strip()
    notes = load_interaction_memory_tail(min(b // 3, 2800))
    if not base:
        return build_retained_context_for_ai(b)
    if not notes:
        return merge_adaptation_into_lessons(base, b)
    extra = f"{base}\n\n[Recent Forager activity]\n{notes}".strip()
    return merge_adaptation_into_lessons(extra, b)


def has_any_retained_memory() -> bool:
    from .user_adaptation import load_profile

    if bool(_council_lessons(300).strip()) or bool(load_interaction_memory_tail(300).strip()):
        return True
    try:
        return int(load_profile().get("exchanges") or 0) > 0
    except (TypeError, ValueError):
        return False
