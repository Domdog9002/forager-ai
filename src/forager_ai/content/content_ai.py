from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List

from ..ai.openrouter_client import (
    chat_completion_text,
    chat_completion_text_stream,
    DEFAULT_MODEL,
    _extract_json,
)

RESOURCE_PACK_SYSTEM = """
You are Forager AI — Minecraft Java **resource pack** architect.
The user wants theme-consistent textures, block/item models, texture animations, and sound event hooks.

Return ONLY valid JSON (no markdown, no prose outside JSON) with this shape:
{
  "theme": {
    "title": "short name",
    "keywords": ["adj1", "adj2"],
    "palette": ["#RRGGBB", "#RRGGBB"],
    "namespace_filters": {
      "highlight": ["namespace ids to emphasize, often mod jars"],
      "mute": ["namespaces to leave vanilla unless needed"]
    }
  },
  "new_textures": [
    {
      "namespace": "minecraft or modid",
      "path": "block/foo or item/bar (no .png, use forward slashes)",
      "asset_kind": "block|ore|item|tool|armor|gui|particle|entity|model_texture|uv",
      "resolution": 16,
      "generation_mode": "local_procedural|external_image_optional",
      "shape_language": "short visual shape description",
      "material": "stone|wood|metal|cloth|magic|machine|organic|crystal|ui",
      "emissive_hint": false,
      "normal_depth_hint": "flat|low|medium|high",
      "model_type": "none|cube_all|item_generated|handheld|cross|simple_3d",
      "uv_template": "none|cube|item_layer|entity_sheet",
      "color_hint": "#RRGGBB optional solid placeholder",
      "inspired_by_mod": "modid or minecraft — logical source for labeling",
      "note": "one line"
    }
  ],
  "new_models": [
    {
      "namespace": "minecraft or modid",
      "path": "block/foo or item/bar (no .json)",
      "parent": "minecraft:block/cube_all | minecraft:item/generated | minecraft:item/handheld | minecraft:block/cross",
      "model_type": "cube_all|item_generated|handheld|cross|simple_3d",
      "texture_layer0": "namespace:textures/path_without_png_suffix",
      "uv_template": "cube|item_layer|cross|entity_sheet",
      "inspired_by_mod": "modid"
    }
  ],
  "animations": [
    {
      "namespace": "minecraft or modid",
      "texture_path": "block/foo (no .png)",
      "frames": 4,
      "frametime": 3,
      "interpolate": false
    }
  ],
  "sound_events": [
    {
      "namespace": "minecraft or modid",
      "event": "block.custom.pack_hit",
      "subtitle": "short subtitle",
      "sound_file": "custom/pack_hit (no .ogg; path under assets/ns/sounds/)",
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
      "target_texture_path": "item/foo or block/foo",
      "animation_kind": "idle_bob|spin|swing|pulse|walk_cycle",
      "name": "short animation name",
      "length": 2.0,
      "loop": true
    }
  ],
  "image_prompts": [
    {"path": "namespace:block/foo", "prompt": "English prompt for external image generator"}
  ],
  "consistency_rules": ["style rule that keeps the pack coherent"],
  "accessibility_notes": ["contrast/readability/colorblind-friendly note"],
  "application_plan": ["step to review/apply/test in-game"],
  "quality_notes": ["risk or follow-up note"]
}

Rules:
- Paths must be relative asset paths only (no .., no absolute).
- Prefer 16x16-style blocks; items can reference item/generated.
- Use `resolution` 16, 32, 64, or 128 only. Default to 16 or 32 unless the user asks for high resolution.
- Every `new_textures` entry must be directly renderable by a local procedural pixel-art engine; include asset_kind, material, shape_language, model_type, and uv_template.
- For 3D-looking assets, add both a `model_texture` or `uv` texture and a matching `new_models` entry.
- Tie each asset to **inspired_by_mod** or **namespace** so the pack can be filtered by mod source.
- Sound events should include local procedural sound specs. Generated local previews are WAV; Minecraft runtime still needs matching OGG files later unless an encoder/provider is configured.
- Blockbench animations are editable `.bbmodel` source timelines only; do not claim runtime entity animations unless the user has a mod animation system.
- Keep the pack coherent: palette, motif, target namespaces, animation rules, UI readability, and fallback placeholders must agree.
- Include a small application/test plan so the user knows how to verify the texture pack in-game.
""".strip()


def iter_resource_pack_plan_text(
    *,
    api_key: str,
    user_request: str,
    existing_assets_summary: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
) -> Iterator[str]:
    """SSE text deltas for a resource-pack blueprint (same contract as ``generate_resource_pack_plan``)."""
    if not (user_request or "").strip():
        raise ValueError("Describe the resource pack theme or goals.")
    blob = {
        "user_request": user_request.strip(),
        "existing_assets_by_namespace": _summarize_by_namespace(existing_assets_summary),
    }
    yield from chat_completion_text_stream(
        api_key=api_key,
        system_prompt=RESOURCE_PACK_SYSTEM,
        user_text=json.dumps(blob, ensure_ascii=True),
        model=model,
        temperature=0.35,
        timeout_s=120,
    )


def parse_resource_pack_plan_text(text: str) -> Dict[str, Any]:
    """Parse model output into a blueprint dict (raises ``ValueError`` if JSON is unusable)."""
    return _parse_plan_json(text)


def generate_resource_pack_plan(
    *,
    api_key: str,
    user_request: str,
    existing_assets_summary: List[Dict[str, Any]],
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    raw = "".join(
        iter_resource_pack_plan_text(
            api_key=api_key,
            user_request=user_request,
            existing_assets_summary=existing_assets_summary,
            model=model,
        )
    )
    return parse_resource_pack_plan_text(raw)


RESOURCE_PACK_STRATEGIST_SYSTEM = """
You are Forager AI's expert Minecraft resource-pack art director.
Return ONLY JSON:
{
  "strategy": {
    "art_direction": "one sentence",
    "palette_logic": ["string"],
    "namespace_priorities": ["string"],
    "readability_rules": ["string"],
    "animation_rules": ["string"],
    "asset_targets": ["string"],
    "builder_directive": "dense instruction for the resource-pack generator"
  }
}
Rules:
- Use supplied instance/modpack context and existing asset summary.
- Prefer coherent, testable texture/model/animation plans.
- Describe assets as renderable Minecraft pixel art, not vague concept art.
- Include local procedural render instructions: asset_kind, resolution, material, shape_language, model_type, uv_template, and emissive_hint.
- When the user asks for 3D textures, plan UV/model textures plus matching model JSON entries.
- Protect vanilla readability and accessibility unless the user explicitly asks otherwise.
- No markdown outside JSON.
""".strip()


RESOURCE_PACK_CRITIC_SYSTEM = """
You are a strict Minecraft resource-pack reviewer.
Return ONLY JSON:
{
  "score": 0,
  "verdict": "strong|repair|reject",
  "issues": ["string"],
  "repair_directive": "exact improvements needed",
  "test_plan": ["string"]
}
Rules:
- Score 0-100.
- Penalize incoherent palette, too many unrelated targets, missing accessibility notes, missing image prompts, or vague test steps.
- Penalize missing render fields, missing 3D model/UV pairings, invalid texture sizes, and texture plans that cannot become Minecraft PNG/model files.
- No markdown outside JSON.
""".strip()


def generate_deep_resource_pack_plan(
    *,
    api_key: str,
    user_request: str,
    existing_assets_summary: List[Dict[str, Any]],
    instance_context: Dict[str, Any],
    model: str = DEFAULT_MODEL,
) -> Dict[str, Any]:
    strategy_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=RESOURCE_PACK_STRATEGIST_SYSTEM,
        user_text=json.dumps(
            {
                "user_request": user_request,
                "existing_assets_by_namespace": _summarize_by_namespace(existing_assets_summary),
                "instance_context": instance_context,
            },
            ensure_ascii=True,
        ),
        model=model,
        temperature=0.18,
        timeout_s=120,
    )
    strategy = _parse_plan_json(strategy_raw)
    enhanced_request = (
        f"{user_request}\n\n"
        f"Art-director strategy JSON: {json.dumps(strategy, ensure_ascii=True)}\n"
        "Generate a coherent, accessible, mod-aware resource-pack blueprint with application/test notes."
    )
    first = generate_resource_pack_plan(
        api_key=api_key,
        user_request=enhanced_request,
        existing_assets_summary=existing_assets_summary,
        model=model,
    )
    critique_raw = chat_completion_text(
        api_key=api_key,
        system_prompt=RESOURCE_PACK_CRITIC_SYSTEM,
        user_text=json.dumps(
            {
                "request": user_request,
                "strategy": strategy,
                "candidate_blueprint": first,
                "instance_context": instance_context,
            },
            ensure_ascii=True,
        ),
        model=model,
        temperature=0.12,
        timeout_s=120,
    )
    critique = _parse_plan_json(critique_raw)
    try:
        score = int(critique.get("score", 0))
    except (TypeError, ValueError):
        score = 0
    final = first
    if score < 88:
        try:
            final = generate_resource_pack_plan(
                api_key=api_key,
                user_request=(
                    f"{enhanced_request}\n\nReviewer critique JSON: {json.dumps(critique, ensure_ascii=True)}\n"
                    "Repair the blueprint by addressing every issue. Return only the resource-pack JSON shape."
                ),
                existing_assets_summary=existing_assets_summary,
                model=model,
            )
            repair_error = ""
        except Exception as exc:
            repair_error = str(exc)[:500]
    else:
        repair_error = ""
    final["intelligence_report"] = {
        "pipeline": "art strategy -> blueprint -> critique -> repair",
        "strategy": strategy.get("strategy", strategy),
        "critique": critique,
        "repaired": final is not first,
        "repair_error": repair_error,
    }
    return final


def _summarize_by_namespace(entries: List[Dict[str, Any]]) -> Dict[str, Any]:
    by_ns: Dict[str, Dict[str, int]] = {}
    for e in entries:
        ns = str(e.get("namespace") or "?")
        cat = str(e.get("category") or "other")
        by_ns.setdefault(ns, {})
        by_ns[ns][cat] = by_ns[ns].get(cat, 0) + 1
    return {k: dict(sorted(v.items())) for k, v in sorted(by_ns.items())}


def _parse_plan_json(text: str) -> Dict[str, Any]:
    return _extract_json(text)
