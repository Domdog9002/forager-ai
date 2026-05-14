from __future__ import annotations

import base64
import json
import re
from typing import Any, Dict, Iterator, List

import requests

from .assistant_voice import merged_lessons_for_generation

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-4o"
DEFAULT_CHAT_MAX_TOKENS = 16384


SYSTEM_PROMPT = """
You are Forager AI, an assistant for Minecraft modpack/launcher workflows.
Return ONLY JSON with this shape:
{
  "explanation": "short plain-language explanation",
  "feature_plan": {
    "feature_name": "string",
    "actions": [
      {
        "type": "edit_file|add_file|add_asset|add_compat|patch_toml|patch_json",
        "path": "relative/path/inside/pack",
        "new_content": "string (for edit_file only)",
        "content": "string (for add_file/add_asset only)",
        "set_values": {"dotted.toml.key": "scalar or nested JSON-like value (patch_toml only)"},
        "merge": {"nested": "objects merged into existing JSON root (patch_json only)"},
        "rule_name": "string (for add_compat only)",
        "affected_mods": ["string", "string"],
        "description": "string (for add_compat only)"
      }
    ]
  }
}

Hard constraints:
- All file paths must be relative and must stay inside the pack.
- Generate text files only.
- For small config edits, prefer **patch_toml** (dotted keys in set_values) or **patch_json** (deep merge object) over replacing entire files.
- No markdown, no backticks, no prose outside JSON.
- In "explanation", be concise. If the request involves crashes, risky edits, or data loss, acknowledge stress briefly—stay factual.
- Users may phrase requests informally or combine several goals; infer intent and prefer safe pack-local actions.
""".strip()


def _extract_json(text: str) -> Dict[str, Any]:
    text = text.strip()
    # Best case: valid JSON as-is.
    try:
        value = json.loads(text)
        if isinstance(value, dict):
            return value
    except json.JSONDecodeError:
        pass

    # Fallback: try every balanced JSON object in the response. This avoids the
    # greedy "{...}" trap when a model emits notes before/after multiple objects.
    valid_objects = []
    for extracted in _json_object_candidates(text):
        try:
            value = json.loads(extracted)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            valid_objects.append(value)
    if valid_objects:
        preferred_keys = {
            "feature_plan",
            "explanation",
            "theme",
            "strategy",
            "score",
            "final_verdict",
            "markdown",
            "description",
        }
        for obj in reversed(valid_objects):
            if preferred_keys & set(obj):
                return obj
        return valid_objects[-1]
    raise ValueError("Model response did not contain a valid JSON object.")


def _json_object_candidates(text: str):
    start = -1
    depth = 0
    in_string = False
    escaped = False
    for idx, ch in enumerate(text):
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
            if depth == 0 and start >= 0:
                yield text[start : idx + 1]
                start = -1


def chat_completion_text(
    *,
    api_key: str,
    system_prompt: str,
    user_text: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.25,
    timeout_s: int = 120,
    max_tokens: int | None = DEFAULT_CHAT_MAX_TOKENS,
) -> str:
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


def sse_delta_content_chunks(*, line: str) -> List[str]:
    """
    Yield content fragments from one SSE ``data:`` JSON line from OpenRouter / OpenAI-style chat completions.
    Returns a list so callers aggregate without managing generator edge cases.
    """
    stripped = (line or "").strip()
    if not stripped.startswith("data:"):
        return []
    payload = stripped[5:].strip()
    if not payload or payload == "[DONE]":
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []
    choices = data.get("choices") or []
    if not isinstance(choices, list) or not choices:
        return []
    first = choices[0] if isinstance(choices[0], dict) else {}
    delta = first.get("delta") if isinstance(first, dict) else None
    if not isinstance(delta, dict):
        return []
    chunk = delta.get("content")
    if isinstance(chunk, str) and chunk:
        return [chunk]
    parts = delta.get("content_parts") or delta.get("parts")
    if isinstance(parts, list):
        out = []
        for p in parts:
            if isinstance(p, str):
                out.append(p)
            elif isinstance(p, dict):
                txt = str(p.get("text") or p.get("content") or "")
                if txt:
                    out.append(txt)
        return out
    return []


def chat_completion_text_stream(
    *,
    api_key: str,
    system_prompt: str,
    user_text: str,
    model: str = DEFAULT_MODEL,
    temperature: float = 0.25,
    timeout_s: int = 120,
    max_tokens: int | None = DEFAULT_CHAT_MAX_TOKENS,
) -> Iterator[str]:
    """Stream assistant text deltas (SSE). For UI use with Streamlit ``st.write_stream``."""
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        "temperature": temperature,
        "stream": True,
    }
    if max_tokens is not None and max_tokens > 0:
        body["max_tokens"] = max_tokens
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    with requests.post(
        OPENROUTER_URL,
        headers=headers,
        json=body,
        stream=True,
        timeout=timeout_s,
    ) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = raw if isinstance(raw, str) else str(raw)
            chunks = sse_delta_content_chunks(line=line)
            for fragment in chunks:
                yield fragment


def chat_completion_with_images(
    *,
    api_key: str,
    system_prompt: str,
    user_text: str,
    images_png: List[bytes],
    model: str = DEFAULT_MODEL,
    temperature: float = 0.25,
    timeout_s: int = 120,
    max_tokens: int | None = 16384,
) -> str:
    """
    OpenAI-compatible multimodal message (OpenRouter). ``images_png`` are raw PNG or JPEG bytes.
    Use a vision-capable ``model`` id (e.g. ``openai/gpt-4o`` or ``google/gemini-2.0-flash-001``).
    """
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    if not images_png:
        return chat_completion_text(
            api_key=api_key,
            system_prompt=system_prompt,
            user_text=user_text,
            model=model,
            temperature=temperature,
            timeout_s=timeout_s,
        )

    content: List[Dict[str, Any]] = [{"type": "text", "text": user_text}]
    for raw in images_png[:6]:
        if not raw:
            continue
        b64 = base64.b64encode(raw).decode("ascii")
        mime = "image/jpeg" if raw[:2] == b"\xff\xd8" else "image/png"
        content.append({"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}})

    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": content},
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


MOD_LIBRARY_DESC_SYSTEM = """
You write short Minecraft mod blurbs for a launcher list UI.
Return ONLY valid JSON: {"description":"your sentence here"}
Rules:
- One plain-text sentence, max 240 characters, no markdown, no quotes inside the string.
- Use only facts supported by the provided metadata; if details are missing, say what the mod might add in cautious wording.
- Do not invent download counts, authors, or version numbers not present in the metadata.
""".strip()


def generate_mod_library_description(
    *,
    api_key: str,
    context: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    timeout_s: int = 55,
) -> str:
    """Single-sentence blurb from jar/remote/OpenRouter metadata context."""
    if not api_key.strip():
        return ""
    payload = json.dumps(context, ensure_ascii=True)
    try:
        raw = chat_completion_text(
            api_key=api_key,
            system_prompt=MOD_LIBRARY_DESC_SYSTEM,
            user_text=payload,
            model=model,
            temperature=0.28,
            timeout_s=timeout_s,
        )
        parsed = _extract_json(raw)
        desc = parsed.get("description")
        if isinstance(desc, str):
            line = re.sub(r"\s+", " ", desc).strip()
            return line[:500] if line else ""
    except (ValueError, json.JSONDecodeError, requests.RequestException, KeyError, OSError):
        pass
    return ""


def generate_feature_payload(
    *,
    api_key: str,
    user_request: str,
    pack_context: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    timeout_s: int = 90,
    prior_lessons: str = "",
) -> Dict[str, Any]:
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    if not user_request.strip():
        raise ValueError("Feature request is required.")

    user_blob: Dict[str, Any] = {
        "feature_request": user_request,
        "pack_context": pack_context,
    }
    merged = merged_lessons_for_generation(prior_lessons, 9600)
    if merged.strip():
        user_blob["lessons_from_prior_ai_reviews"] = merged.strip()

    body: Dict[str, Any] = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": json.dumps(user_blob, ensure_ascii=True),
            },
        ],
        "temperature": 0.2,
        "max_tokens": DEFAULT_CHAT_MAX_TOKENS,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(OPENROUTER_URL, headers=headers, json=body, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()

    content = data["choices"][0]["message"]["content"]
    parsed = _extract_json(content)
    if "feature_plan" not in parsed:
        raise ValueError("Model response JSON missing feature_plan.")
    if "explanation" not in parsed:
        parsed["explanation"] = "Feature plan generated."
    return parsed


FEATURE_STRATEGIST_SYSTEM = """
You are Forager AI's senior Minecraft modpack systems architect.
Return ONLY JSON:
{
  "strategy": {
    "core_goal": "one sentence",
    "implementation_style": "kubejs|datapack|resourcepack|forge_scaffold|mixed",
    "vertical_slice": ["small playable steps"],
    "compatibility_targets": ["mods/systems to respect"],
    "risk_controls": ["specific guardrails"],
    "test_plan": ["in-game or file-level checks"],
    "builder_directive": "dense instruction for a feature-plan generator"
  }
}
Rules:
- Use only supplied pack context.
- Prefer reversible, text-only pack-local changes.
- Minecraft modpack design must account for missing optional mods, server/client impact, progression balance, and rollback.
- No markdown outside JSON.
""".strip()


FEATURE_CRITIC_SYSTEM = """
You are Forager AI's strict implementation reviewer.
Return ONLY JSON:
{
  "score": 0,
  "verdict": "strong|repair|reject",
  "strengths": ["string"],
  "issues": ["string"],
  "repair_directive": "exact instruction to improve the plan",
  "test_plan": ["string"]
}
Rules:
- Score 0-100.
- Reject unsafe paths, vague file actions, missing tests, risky config edits without backups, or plans that ignore compatibility.
- No markdown outside JSON.
""".strip()


def generate_deep_feature_payload(
    *,
    api_key: str,
    user_request: str,
    pack_context: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    timeout_s: int = 120,
    prior_lessons: str = "",
    repair: bool = True,
) -> Dict[str, Any]:
    """Strategy -> plan -> critique -> optional repair for higher quality feature plans."""
    strategy_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=FEATURE_STRATEGIST_SYSTEM,
        user_text=json.dumps(
            {
                "feature_request": user_request,
                "pack_context": pack_context,
                "lessons_from_prior_ai_reviews": merged_lessons_for_generation(prior_lessons, 9200),
            },
            ensure_ascii=True,
        ),
        model=model,
        temperature=0.16,
        timeout_s=timeout_s,
    )
    strategy = _extract_json(strategy_raw)
    directive = ((strategy.get("strategy") or {}).get("builder_directive") or "").strip()
    enhanced_request = (
        f"{user_request}\n\n"
        "Deep architect strategy JSON:\n"
        f"{json.dumps(strategy, ensure_ascii=True)}\n\n"
        f"Builder directive: {directive}\n"
        "Generate the strongest safe FeaturePlan possible. Include docs/test notes and compatibility fallbacks."
    )
    first = generate_feature_payload(
        api_key=api_key,
        user_request=enhanced_request,
        pack_context=pack_context,
        model=model,
        timeout_s=timeout_s,
        prior_lessons=prior_lessons,
    )
    critique_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=FEATURE_CRITIC_SYSTEM,
        user_text=json.dumps(
            {
                "original_request": user_request,
                "strategy": strategy,
                "candidate_payload": first,
                "pack_context": pack_context,
            },
            ensure_ascii=True,
        ),
        model=model,
        temperature=0.12,
        timeout_s=timeout_s,
    )
    critique = _extract_json(critique_raw)
    final_payload = first
    try:
        score = int(critique.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    if repair and score < 88:
        repair_request = (
            f"{enhanced_request}\n\n"
            "Strict reviewer critique JSON:\n"
            f"{json.dumps(critique, ensure_ascii=True)}\n\n"
            "Repair the plan now. Address every issue, keep paths safe, add tests/docs/fallbacks, and return only the required JSON shape."
        )
        try:
            final_payload = generate_feature_payload(
                api_key=api_key,
                user_request=repair_request,
                pack_context=pack_context,
                model=model,
                timeout_s=timeout_s,
                prior_lessons=prior_lessons,
            )
            repair_error = ""
        except (ValueError, json.JSONDecodeError, requests.RequestException, KeyError) as exc:
            repair_error = str(exc)[:500]
    else:
        repair_error = ""
    final_payload["intelligence_report"] = {
        "pipeline": "strategy -> build -> critique -> repair",
        "strategy": strategy.get("strategy", strategy),
        "critique": critique,
        "repaired": final_payload is not first,
        "repair_error": repair_error,
    }
    return final_payload


MOD_FOUNDRY_SYSTEM = """
You are Forager AI Mod Foundry, a senior Minecraft Forge 1.20.1 mod team compressed into a careful planning assistant.
Return ONLY JSON:
{
  "explanation": "short plain-language summary",
  "feature_plan": {
    "feature_name": "string",
    "actions": [
      {
        "type": "edit_file|add_file|add_asset|add_compat|patch_toml|patch_json",
        "path": "relative/path/inside/pack",
        "new_content": "string for edit_file",
        "content": "string for add_file/add_asset",
        "set_values": {"dotted.toml.key": "value"},
        "merge": {"nested": "json_merge_into_existing_root"},
        "rule_name": "string for add_compat",
        "affected_mods": ["string"],
        "description": "string"
      }
    ]
  },
  "asset_requests": [
    {
      "id": "string",
      "namespace": "lowercase_namespace",
      "path": "item/name or block/name or entity/name",
      "asset_kind": "item|tool|block|ore|gui|entity|model_texture",
      "resolution": "16x16|32x32|64x64",
      "shape_language": "visual design direction",
      "material": "visual material",
      "model_type": "item_generated|handheld|cube_all|slab|pillar|crossed_plant|entity_box|armor_display|decorative_object",
      "uv_template": "item_layer|cube|entity_sheet"
    }
  ],
  "sound_requests": [
    {
      "namespace": "lowercase_namespace",
      "event": "item.example.cast",
      "subtitle": "short subtitle",
      "sound_file": "custom/example_cast",
      "sound_kind": "click|ui_blip|magic_chime|spell_cast|hit|impact|pickup|machine_hum|ambient_loop",
      "duration_ms": 700,
      "pitch": 1.0,
      "volume": 0.7,
      "loop": false,
      "generation_mode": "local_procedural|external_ai_optional",
      "ai_audio_prompt": "optional prompt for future AI audio provider"
    }
  ],
  "blockbench_animations": [
    {
      "target_texture_path": "item/name or block/name",
      "animation_kind": "idle_bob|spin|swing|pulse|walk_cycle",
      "name": "short name",
      "length": 2.0,
      "loop": true
    }
  ],
  "compatibility_notes": ["string"],
  "performance_notes": ["string"],
  "stability_notes": ["string"],
  "mini_change_suggestions": ["string"],
  "test_plan": ["string"],
  "rollback_plan": ["string"]
}
Rules:
- All paths must be relative and pack-local.
- Prefer safe content first: kubejs/, data/, resourcepacks/, docs/, and .forager/ai_mods/.
- Do not edit jars or generate binaries.
- Do not edit existing .toml/.ini; if Forge scaffold is requested, only generate isolated source project notes.
- Include generated texture/model requests for any new item, block, entity, GUI, or custom visual feature.
- Include sound_requests for features that need UI, magic, hit, machine, ambient, pickup, or impact feedback.
- Include blockbench_animations for generated 3D source models that should have editable Blockbench timelines.
- Be explicit about optional mod fallbacks, server/client split, performance budget, and in-game verification.
- No markdown outside JSON.
""".strip()


MOD_FOUNDRY_STRATEGIST_SYSTEM = """
You are Forager AI's lead mod architect.
Return ONLY JSON:
{
  "strategy": {
    "quality_target": "professional prototype|release candidate|compiled mod scaffold",
    "vertical_slice": ["string"],
    "logic_layers": ["scripts/datapacks/resources/docs/build steps"],
    "compatibility_targets": ["string"],
    "performance_budget": ["string"],
    "asset_direction": ["string"],
    "mini_change_plan": ["string"],
    "council_focus": ["string"],
    "builder_directive": "dense directive for Mod Foundry generator"
  }
}
Rules:
- Use only supplied pack context and filters.
- Keep the first output reversible and testable.
- No markdown outside JSON.
""".strip()


MOD_FOUNDRY_CRITIC_SYSTEM = """
You are Forager AI's professional mod QA lead.
Return ONLY JSON:
{
  "score": 0,
  "verdict": "strong|repair|reject",
  "issues": ["string"],
  "missing_assets": ["string"],
  "performance_risks": ["string"],
  "compatibility_risks": ["string"],
  "repair_directive": "exact instruction to improve the generated bundle",
  "test_plan": ["string"]
}
Rules:
- Score against professional mod-team expectations: logic, stability, compatibility, performance, assets, tests, rollback.
- Reject unsafe paths, vague changes, untestable features, missing visuals for new visible content, or unsupported compiled mod claims.
- No markdown outside JSON.
""".strip()


def generate_mod_foundry_bundle(
    *,
    api_key: str,
    user_request: str,
    pack_context: Dict[str, Any],
    filters: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    timeout_s: int = 120,
    prior_lessons: str = "",
    repair: bool = True,
) -> Dict[str, Any]:
    """Strategy -> bundle -> critique -> optional repair for richer AI Mod Foundry output."""
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    user_blob = {
        "mod_request": user_request,
        "pack_context": pack_context,
        "foundry_filters": filters,
        "lessons_from_prior_ai_reviews": merged_lessons_for_generation(prior_lessons, 9200),
    }
    strategy_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=MOD_FOUNDRY_STRATEGIST_SYSTEM,
        user_text=json.dumps(user_blob, ensure_ascii=True),
        model=model,
        temperature=0.14,
        timeout_s=timeout_s,
    )
    strategy = _extract_json(strategy_raw)
    directive = ((strategy.get("strategy") or {}).get("builder_directive") or "").strip()
    build_blob = dict(user_blob)
    build_blob["strategy"] = strategy
    build_blob["builder_directive"] = directive
    first_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=MOD_FOUNDRY_SYSTEM,
        user_text=json.dumps(build_blob, ensure_ascii=True),
        model=model,
        temperature=0.18,
        timeout_s=timeout_s,
    )
    first = _extract_json(first_raw)
    critique_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=MOD_FOUNDRY_CRITIC_SYSTEM,
        user_text=json.dumps({"candidate_bundle": first, "strategy": strategy, **user_blob}, ensure_ascii=True),
        model=model,
        temperature=0.1,
        timeout_s=timeout_s,
    )
    critique = _extract_json(critique_raw)
    final = first
    try:
        score = int(critique.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    if repair and score < 90:
        repair_blob = dict(build_blob)
        repair_blob["candidate_bundle"] = first
        repair_blob["critic_report"] = critique
        repair_blob["repair_instruction"] = "Repair every issue and return the full required Mod Foundry JSON shape."
        try:
            repaired_raw = chat_completion_text(
                api_key=api_key,
                system_prompt=MOD_FOUNDRY_SYSTEM,
                user_text=json.dumps(repair_blob, ensure_ascii=True),
                model=model,
                temperature=0.14,
                timeout_s=timeout_s,
            )
            final = _extract_json(repaired_raw)
            repair_error = ""
        except (ValueError, json.JSONDecodeError, requests.RequestException, KeyError) as exc:
            repair_error = str(exc)[:500]
    else:
        repair_error = ""
    final.setdefault("feature_plan", {"feature_name": "AI Mod Foundry Feature", "actions": []})
    final.setdefault("asset_requests", [])
    final["intelligence_report"] = {
        "pipeline": "foundry_strategy -> bundle -> qa_critic -> repair",
        "strategy": strategy.get("strategy", strategy),
        "critique": critique,
        "repaired": final is not first,
        "repair_error": repair_error,
    }
    return final


PACK_ARCHITECT_SYSTEM = """
You are Forager AI Pack Architect for Minecraft Forge 1.20.1 modpacks.
Return ONLY JSON:
{
  "vision": "short pack direction",
  "pillars": ["string"],
  "progression_stages": [{"stage":"early|mid|late|endgame","goals":["string"],"risks":["string"]}],
  "suggested_mods": [{"name":"string","reason":"string","risk":"low|medium|high"}],
  "config_goals": ["string"],
  "compat_rules": [{"rule_name":"string","affected_mods":["string"],"description":"string"}],
  "feature_plan": {"feature_name":"string","actions":[{"type":"add_file|add_compat|patch_toml|patch_json|edit_file|add_asset","path":"string","content":"string","set_values":{"dotted.key":"value"},"merge":{"nested":"object"},"rule_name":"string","affected_mods":["string"],"description":"string"}]}
}
Rules:
- Use only the supplied context.
- Keep file actions text-only and inside docs/, kubejs/, scripts/, config/, or resourcepacks/.
- Prefer **patch_toml** / **patch_json** for small config edits when you know keys; use add_file for new docs; add_compat for cross-mod notes.
- No markdown outside JSON.
""".strip()


def generate_pack_architecture(
    *,
    api_key: str,
    user_request: str,
    pack_context: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    timeout_s: int = 120,
) -> Dict[str, Any]:
    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    if not user_request.strip():
        raise ValueError("Architecture request is required.")
    raw = chat_completion_text(
        api_key=api_key,
        system_prompt=PACK_ARCHITECT_SYSTEM,
        user_text=json.dumps({"request": user_request, "pack_context": pack_context}, ensure_ascii=True),
        model=model,
        temperature=0.18,
        timeout_s=timeout_s,
    )
    parsed = _extract_json(raw)
    parsed.setdefault("feature_plan", {"feature_name": "pack_architecture_plan", "actions": []})
    return parsed


PACK_GUIDE_SYSTEM = """
You write concise player-facing Minecraft modpack guides.
Return ONLY JSON:
{
  "title": "string",
  "summary": "string",
  "markdown": "complete markdown guide",
  "sections": [{"title":"string","bullets":["string"]}],
  "artifact": {"guide_type":"progression|install|compat","notes":["string"]}
}
Rules:
- Use only provided pack context.
- Highlight Create, Ars Nouveau, Iron's Spells, Origins, compatibility risks, and progression stages when present.
- No prose outside JSON.
""".strip()


def generate_pack_guide(
    *,
    api_key: str,
    guide_request: str,
    pack_context: Dict[str, Any],
    model: str = DEFAULT_MODEL,
    timeout_s: int = 120,
) -> Dict[str, Any]:
    from .assistant_voice import augment_user_facing_system

    if not api_key.strip():
        raise ValueError("OpenRouter API key is required.")
    raw = chat_completion_text(
        api_key=api_key,
        system_prompt=augment_user_facing_system(PACK_GUIDE_SYSTEM),
        user_text=json.dumps({"request": guide_request, "pack_context": pack_context}, ensure_ascii=True),
        model=model,
        temperature=0.22,
        timeout_s=timeout_s,
    )
    parsed = _extract_json(raw)
    if "markdown" not in parsed:
        raise ValueError("Guide response missing markdown.")
    return parsed

