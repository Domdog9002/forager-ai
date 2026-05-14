from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import requests

from .openrouter_client import DEFAULT_MODEL, OPENROUTER_URL, _extract_json


def chat_completion_text(
    *,
    api_key: str,
    system_prompt: str,
    user_text: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.25,
    timeout_s: int = 120,
    max_tokens: int | None = 16384,
) -> str:
    """Single chat completion (plain text). Defined here so council works even if an older openrouter_client lacks this helper."""
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
    }
    if max_tokens is not None and max_tokens > 0:
        body["max_tokens"] = max_tokens
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    resp = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"])


def _memory_file() -> Path:
    base = Path.home() / ".forager_ai"
    base.mkdir(parents=True, exist_ok=True)
    return base / "council_memory.jsonl"


def append_memory(entry: Dict[str, Any]) -> None:
    path = _memory_file()
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=True) + "\n")


def load_recent_lessons(max_chars: int = 6000) -> str:
    path = _memory_file()
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8", errors="replace").strip().splitlines()
    picked: List[str] = []
    total = 0
    for line in reversed(lines[-40:]):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        lesson = str(obj.get("synthesized_lessons") or obj.get("chair_summary") or "").strip()
        if lesson:
            chunk = lesson[:900]
            if total + len(chunk) > max_chars:
                break
            picked.append(f"- {chunk}")
            total += len(chunk)
    return "\n".join(reversed(picked))


_FORAGER_PRODUCT_DEFAULTS = (
    "Product defaults unless the artifact clearly overrides them: target Minecraft 1.20.x Forge-style modpack workflows, "
    "UTF-8 text, paths stay pack-local relative (no writes outside the instance/pack)."
)


def _council_instruction_snippet(artifact: Any) -> str:
    """Pull optional reviewer hints from standardized artifacts or raw dicts."""
    raw: Any = None
    if isinstance(artifact, dict):
        raw = artifact.get("council_instructions")
        if raw is None and isinstance(artifact.get("payload"), dict):
            raw = artifact["payload"].get("council_instructions")
    if raw is None:
        return ""
    if isinstance(raw, str) and raw.strip():
        return raw.strip()[:4000]
    if isinstance(raw, list):
        lines = []
        for item in raw:
            s = str(item).strip()
            if s:
                lines.append(f"- {s}")
        joined = "\n".join(lines)
        return joined[:4000] if joined else ""
    return ""


def _reviewer_preamble(*, artifact: Any) -> str:
    lessons = load_recent_lessons(max_chars=4800).strip()
    extra = _council_instruction_snippet(artifact).strip()
    parts: List[str] = [_FORAGER_PRODUCT_DEFAULTS]
    if lessons:
        parts.append(
            "Recent Council memory (patterns to honor or avoid):\n" + lessons
        )
    if extra:
        parts.append("Stakeholder instructions for THIS review:\n" + extra)
    return "\n\n".join(parts).strip()


CHAIR_SYSTEM = """
You are the Chair model. Merge reviewer outputs (safety, accuracy, polish, compat_progression, mod_ship) into one actionable quality report for Forager AI.
Give extra weight to compat_progression on modded Minecraft packs: version/loader fit, conflict risk, and progression coherence.
Treat mod_ship as authoritative when the artifact is about building or shipping a mod or Foundry feature plan; block or revise if ship blockers are high severity.
Return JSON ONLY with this shape:
{
  "final_verdict": "pass|revise|block",
  "issues": [{"severity":"high|medium|low","detail":"string","owner":"safety|accuracy|polish|compat|mod_ship|chair"}],
  "polish": [{"detail":"string"}],
  "recommended_actions": ["string"],
  "synthesized_lessons": "2-6 short bullet sentences the app should remember for future generations"
}
No markdown.
""".strip()


REVIEWERS: List[tuple[str, str]] = [
    (
        "safety",
        "You are Reviewer A (Safety). Inspect the artifact for risky file paths, destructive edits, "
        "secret leakage, or instructions that could break a Minecraft pack. "
        'Return JSON ONLY: {"issues":[{"severity":"high|medium|low","detail":"..."}],"summary":"..."} ',
    ),
    (
        "accuracy",
        "You are Reviewer B (Accuracy). Check Minecraft/modding factual plausibility and internal consistency. "
        'Return JSON ONLY: {"issues":[{"severity":"high|medium|low","detail":"..."}],"summary":"..."} ',
    ),
    (
        "polish",
        "You are Reviewer C (Polish). Improve clarity, structure, missing steps, and user-facing quality. "
        'Return JSON ONLY: {"polish":[{"detail":"..."}],"summary":"..."} ',
    ),
    (
        "compat_progression",
        "You are Reviewer D (Mod Compatibility & Progression). Evaluate the artifact specifically for: "
        "(1) Mod compatibility — Minecraft version and loader fit (Forge/Fabric/NeoForge/Quilt), "
        "declared dependencies, duplicate or overlapping mods (two minimaps, two worldgens, conflicting render stacks), "
        "API/version skew, client-only vs server-required splits, and mixins/datapack load order risks. "
        "(2) Progression compatibility — whether changes preserve a coherent early/mid/late curve: "
        "gating (materials, quests, tech tiers), power scaling vs vanilla and other major mods, "
        "recipe cost sanity, avoid skipping whole mod chapters or bricking pack goals, "
        "and tension between tech/magic/exploration pillars if both appear. "
        "Flag cross-mod exploits or dead-end paths when the plan adds or rewrites content. "
        'Return JSON ONLY: {'
        '"issues":[{"severity":"high|medium|low","detail":"string"}],'
        '"progression_notes":[{"detail":"string"}],'
        '"compat_notes":[{"detail":"string"}],'
        '"summary":"string"}',
    ),
    (
        "mod_ship",
        "You are Reviewer E (Mod authoring & shipping quality). When the artifact includes mod development, "
        "Foundry bundles, Gradle/mods.toml, mixins/access transformers, registrations, datapack/kubejs hints, assets, "
        "or redistribution plans — evaluate readiness to ship testable quality: "
        "mod id + Maven coordinates sanity, versioning and dependency/version ranges on Forge/Minecraft, "
        "client vs dedicated server splits, sane package namespaces, mixin/transformer blast radius and ordering risk, "
        "resource locations/registry ids, datapack/load order assumptions, attribution/licensing placeholders, "
        "no contradictory build steps, obvious security/redistribution issues (credential leakage, shady downloads), "
        "and gaps that would block compiling or smoke-testing on 1.20.1-ish Forge workflows. "
        "If nothing here is relevant, state that briefly with low severity. "
        'Return JSON ONLY: {"issues":[{"severity":"high|medium|low","detail":"..."}],"mod_notes":[{"detail":"..."}],"summary":"..."}',
    ),
]


def _artifact_fingerprint(subject: str, artifact: Any) -> str:
    raw = json.dumps({"s": subject, "a": artifact}, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _append_council_memory(*, fp: str, subject: str, final: Dict[str, Any], model: str) -> None:
    memory_entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "fingerprint": fp,
        "subject": subject[:500],
        "final_verdict": final.get("final_verdict"),
        "synthesized_lessons": final.get("synthesized_lessons", ""),
        "issues_count": len(final.get("issues") or []),
        "model": model,
    }
    append_memory(memory_entry)


def _council_aborted_result(fp: str, reviews: Dict[str, Any], *, stage: str) -> Dict[str, Any]:
    names = ", ".join(sorted(reviews.keys())) if reviews else "(none)"
    chair: Dict[str, Any] = {
        "final_verdict": "revise",
        "issues": [
            {
                "severity": "low",
                "detail": f"Council stopped early ({stage}). Completed reviewers: {names}.",
                "owner": "chair",
            }
        ],
        "polish": [],
        "recommended_actions": [
            "Re-run with **Stepwise Council** in the dashboard to pause between API calls.",
            "Inspect partial reviewer JSON for any signals captured before stop.",
        ],
        "synthesized_lessons": "",
        "council_aborted_stub": True,
    }
    return {
        "fingerprint": fp,
        "reviews": reviews,
        "chair": chair,
        "memory_stored": False,
        "council_aborted": True,
        "council_abort_stage": stage,
    }


def council_wip_start(
    *,
    api_key: str,
    subject: str,
    artifact: Any,
    model: str = DEFAULT_MODEL,
    timeout_s_per_call: int = 90,
    pack_context_overlay: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Mutable work-in-progress dict for stepwise Council (one reviewer HTTP call per UI step)."""
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    fp = _artifact_fingerprint(subject, artifact)
    preamble = _reviewer_preamble(artifact=artifact)
    user_obj: Dict[str, Any] = {
        "subject": subject,
        "reviewer_context": preamble,
        "artifact": artifact,
    }
    if pack_context_overlay:
        user_obj["pack_context_overlay"] = pack_context_overlay
    return {
        "fingerprint": fp,
        "api_key": api_key,
        "model": model,
        "timeout_s_per_call": int(timeout_s_per_call),
        "user_common": json.dumps(user_obj, ensure_ascii=True),
        "preamble": preamble,
        "subject": subject[:800],
        "reviews": {},
        "step": 0,
    }


def council_wip_run_next_reviewer(wip: Dict[str, Any]) -> Dict[str, Any]:
    """Run the next reviewer in ``wip``; mutates ``wip`` in place."""
    i = int(wip["step"])
    if i >= len(REVIEWERS):
        raise ValueError("All reviewers already finished — run the chair step.")
    key, system = REVIEWERS[i]
    raw = chat_completion_text(
        api_key=str(wip["api_key"]),
        system_prompt=system + " No markdown. No code fences.",
        user_text=str(wip["user_common"]),
        model=str(wip["model"]),
        temperature=0.15,
        timeout_s=int(wip.get("timeout_s_per_call") or 90),
    )
    try:
        wip["reviews"][key] = _extract_json(raw)
    except Exception:
        wip["reviews"][key] = {"parse_error": True, "raw": raw[:4000]}
    wip["step"] = i + 1
    return wip


def council_wip_run_chair_and_finish(wip: Dict[str, Any]) -> Dict[str, Any]:
    """Chair merge + memory append; returns the same shape as ``run_council_review``."""
    if int(wip["step"]) < len(REVIEWERS):
        raise ValueError("Finish all reviewers before running the chair.")
    reviews = wip["reviews"]
    subject = str(wip["subject"])
    preamble = str(wip["preamble"])
    fp = str(wip["fingerprint"])
    api_key = str(wip["api_key"])
    model = str(wip["model"])
    timeout = int(wip.get("timeout_s_per_call") or 90)
    chair_user = json.dumps(
        {"subject": subject, "reviewer_context": preamble, "reviews": reviews},
        ensure_ascii=True,
    )
    chair_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=CHAIR_SYSTEM,
        user_text=chair_user,
        model=model,
        temperature=0.2,
        timeout_s=timeout,
    )
    try:
        final = _extract_json(chair_raw)
    except Exception:
        final = {
            "final_verdict": "revise",
            "issues": [{"severity": "medium", "detail": "Chair model returned non-JSON.", "owner": "chair"}],
            "polish": [],
            "recommended_actions": ["Re-run council review.", "Inspect raw reviewer output."],
            "synthesized_lessons": "",
            "chair_parse_error": True,
            "chair_raw": chair_raw[:4000],
        }
    _append_council_memory(fp=fp, subject=subject, final=final, model=model)
    return {
        "fingerprint": fp,
        "reviews": reviews,
        "chair": final,
        "memory_stored": True,
    }


def run_council_review(
    *,
    api_key: str,
    subject: str,
    artifact: Any,
    model: str = DEFAULT_MODEL,
    timeout_s_per_call: int = 90,
    pack_context_overlay: Optional[Dict[str, Any]] = None,
    should_abort: Optional[Callable[[], bool]] = None,
) -> Dict[str, Any]:
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")

    fp = _artifact_fingerprint(subject, artifact)
    preamble = _reviewer_preamble(artifact=artifact)
    user_obj: Dict[str, Any] = {
        "subject": subject,
        "reviewer_context": preamble,
        "artifact": artifact,
    }
    if pack_context_overlay:
        user_obj["pack_context_overlay"] = pack_context_overlay
    user_common = json.dumps(user_obj, ensure_ascii=True)

    reviews: Dict[str, Any] = {}
    for key, system in REVIEWERS:
        if should_abort and should_abort():
            return _council_aborted_result(fp, reviews, stage=f"before_{key}")
        raw = chat_completion_text(
            api_key=api_key,
            system_prompt=system + " No markdown. No code fences.",
            user_text=user_common,
            model=model,
            temperature=0.15,
            timeout_s=timeout_s_per_call,
        )
        try:
            reviews[key] = _extract_json(raw)
        except Exception:
            reviews[key] = {"parse_error": True, "raw": raw[:4000]}

    if should_abort and should_abort():
        return _council_aborted_result(fp, reviews, stage="before_chair")

    chair_user = json.dumps(
        {"subject": subject, "reviewer_context": preamble, "reviews": reviews},
        ensure_ascii=True,
    )
    chair_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=CHAIR_SYSTEM,
        user_text=chair_user,
        model=model,
        temperature=0.2,
        timeout_s=timeout_s_per_call,
    )
    try:
        final = _extract_json(chair_raw)
    except Exception:
        final = {
            "final_verdict": "revise",
            "issues": [{"severity": "medium", "detail": "Chair model returned non-JSON.", "owner": "chair"}],
            "polish": [],
            "recommended_actions": ["Re-run council review.", "Inspect raw reviewer output."],
            "synthesized_lessons": "",
            "chair_parse_error": True,
            "chair_raw": chair_raw[:4000],
        }

    _append_council_memory(fp=fp, subject=subject, final=final, model=model)

    return {
        "fingerprint": fp,
        "reviews": reviews,
        "chair": final,
        "memory_stored": True,
    }


def council_followup_checklist(chair: Dict[str, Any]) -> List[str]:
    """Deterministic next steps after a chair report."""
    verdict = str((chair or {}).get("final_verdict") or "").strip().lower()
    steps: List[str] = [
        "Skim reviewer summaries for anything marked high severity before editing files.",
        "Convert **recommended_actions** into a short ordered checklist in your notes.",
    ]
    if verdict == "block":
        steps.append("Do not ship automated file edits until issues are resolved or explicitly waived.")
    elif verdict == "revise":
        steps.append("Address chair issues, then re-run Council or spot-check with a smaller artifact.")
    else:
        steps.append("Spot-check the highest-severity note once in-game or in a test world.")
    steps.append("Persist durable compat rules via Compat Writer or `.forager` docs if reviewers flagged mod pairs.")
    ra = (chair or {}).get("recommended_actions") or []
    if isinstance(ra, list) and len(ra) >= 3:
        steps.append("Triage the first three recommended actions today; defer the rest behind a checkpoint.")
    return steps

