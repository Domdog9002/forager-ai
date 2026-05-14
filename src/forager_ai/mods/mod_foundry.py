from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from ..ai.artifacts import make_ai_artifact, save_ai_artifact
from ..ai.council import run_council_review
from ..engine.feature_plan import validate_feature_plan
from ..engine.gradle_bundle import copy_wrapper_into_directory
from ..fs.safe_writer import write_text_utf8_nobom


SAFE_TEXT_EXTENSIONS = {
    ".json",
    ".js",
    ".kjs",
    ".mcmeta",
    ".txt",
    ".md",
    ".yml",
    ".yaml",
    ".properties",
    ".cfg",
}
FORBIDDEN_EXTENSIONS = {".jar", ".exe", ".dll", ".bat", ".cmd", ".ps1", ".class"}
NAMESPACE_RE = re.compile(r"^[a-z0-9_.-]+$")
SOUND_KIND_ALLOWLIST = {
    "click",
    "ui_blip",
    "magic_chime",
    "spell_cast",
    "hit",
    "impact",
    "pickup",
    "machine_hum",
    "ambient_loop",
}
BLOCKBENCH_ANIMATION_ALLOWLIST = {"idle_bob", "spin", "swing", "pulse", "walk_cycle"}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_unsafe_relative_path(path: str) -> bool:
    normalized = str(path or "").replace("\\", "/").strip()
    if not normalized:
        return True
    if os.path.isabs(normalized):
        return True
    parts = [part for part in normalized.split("/") if part]
    return any(part == ".." for part in parts)


def foundry_dir(instance_root: str | Path) -> Path:
    path = Path(instance_root) / ".forager" / "ai_mod_foundry"
    path.mkdir(parents=True, exist_ok=True)
    return path


def project_file(instance_root: str | Path) -> Path:
    return foundry_dir(instance_root) / "project.json"


def default_project(instance_root: str | Path, *, name: str = "AI Mod Foundry Project") -> Dict[str, Any]:
    return {
        "schema_version": 1,
        "name": name,
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "filters": {},
        "drafts": [],
        "mini_changes": [],
        "asset_requests": [],
        "sound_requests": [],
        "blockbench_animations": [],
        "reviews": [],
        "gate_history": [],
        "compiled_projects": [],
    }


def load_project(instance_root: str | Path) -> Dict[str, Any]:
    path = project_file(instance_root)
    if not path.is_file():
        return default_project(instance_root)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            base = default_project(instance_root, name=str(data.get("name") or "AI Mod Foundry Project"))
            base.update(data)
            for key in ("drafts", "mini_changes", "asset_requests", "sound_requests", "blockbench_animations", "reviews", "gate_history", "compiled_projects"):
                base.setdefault(key, [])
            base.setdefault("filters", {})
            return base
    except (json.JSONDecodeError, OSError):
        pass
    return default_project(instance_root)


def save_project(instance_root: str | Path, project: Dict[str, Any]) -> str:
    project["updated_at"] = utc_now_iso()
    path = project_file(instance_root)
    write_text_utf8_nobom(str(path), json.dumps(project, indent=2, ensure_ascii=False))
    return str(path)


def append_draft(
    instance_root: str | Path,
    project: Dict[str, Any],
    *,
    plan: Dict[str, Any],
    bundle: Optional[Dict[str, Any]] = None,
    filters: Optional[Dict[str, Any]] = None,
    gates: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    draft_id = f"draft_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{len(project.get('drafts') or []) + 1}"
    draft = {
        "id": draft_id,
        "created_at": utc_now_iso(),
        "feature_name": plan.get("feature_name") or "AI mod feature",
        "plan": plan,
        "bundle": bundle or {},
        "filters": filters or {},
        "gates": gates or {},
        "status": "draft",
    }
    project.setdefault("drafts", []).append(draft)
    project["filters"] = filters or project.get("filters") or {}
    project["asset_requests"] = extract_asset_requests(bundle or {}, plan)
    project["sound_requests"] = extract_sound_requests(bundle or {}, plan)
    project["blockbench_animations"] = extract_blockbench_animation_requests(bundle or {}, plan)
    save_project(instance_root, project)
    return draft


def append_mini_change(
    instance_root: str | Path,
    project: Dict[str, Any],
    *,
    request: str,
    result_plan: Optional[Dict[str, Any]] = None,
    status: str = "queued",
) -> Dict[str, Any]:
    change = {
        "id": f"change_{len(project.get('mini_changes') or []) + 1}",
        "created_at": utc_now_iso(),
        "request": request.strip(),
        "status": status,
        "result_plan": result_plan or {},
    }
    project.setdefault("mini_changes", []).append(change)
    save_project(instance_root, project)
    return change


def latest_draft(project: Dict[str, Any]) -> Dict[str, Any]:
    drafts = project.get("drafts") if isinstance(project.get("drafts"), list) else []
    return drafts[-1] if drafts else {}


def feature_plan_from_bundle(bundle: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(bundle.get("feature_plan"), dict):
        return bundle["feature_plan"]
    if isinstance(bundle.get("plan"), dict):
        return bundle["plan"]
    return {"feature_name": str(bundle.get("feature_name") or "AI Mod Foundry Feature"), "actions": []}


def normalize_asset_request(raw: Dict[str, Any], *, index: int = 0) -> Dict[str, Any]:
    namespace = str(raw.get("namespace") or raw.get("mod_id") or "forager_ai").lower()
    namespace = re.sub(r"[^a-z0-9_.-]+", "_", namespace).strip("_") or "forager_ai"
    path = str(raw.get("path") or raw.get("texture_path") or raw.get("id") or f"item/foundry_asset_{index}")
    path = path.replace("\\", "/").replace(":", "/").strip("/")
    path = re.sub(r"[^a-zA-Z0-9_./-]+", "_", path)
    if "/" not in path:
        path = f"item/{path}"
    asset_kind = str(raw.get("asset_kind") or raw.get("kind") or raw.get("type") or "item")
    model_type = str(raw.get("model_type") or ("handheld" if "tool" in asset_kind else "item_generated"))
    return {
        "id": str(raw.get("id") or raw.get("name") or path),
        "namespace": namespace,
        "path": path,
        "asset_kind": asset_kind,
        "resolution": raw.get("resolution") or "32x32",
        "shape_language": raw.get("shape_language") or raw.get("description") or f"Texture for {path}",
        "material": raw.get("material") or "minecraft material",
        "model_type": model_type,
        "uv_template": raw.get("uv_template") or ("cube" if "block" in path else "item_layer"),
        "color_hint": raw.get("color_hint") or raw.get("primary_color"),
        "note": raw.get("note") or raw.get("description") or "Generated by AI Mod Foundry.",
    }


def extract_asset_requests(bundle: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for key in ("asset_requests", "assets", "texture_requests", "blockbench_requests"):
        value = bundle.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    if plan:
        for action in plan.get("actions") or []:
            if not isinstance(action, dict):
                continue
            path = str(action.get("path") or "")
            if any(part in path for part in ("textures/", "models/", "resourcepacks/")):
                candidates.append(
                    {
                        "id": Path(path).stem,
                        "path": f"item/{Path(path).stem}",
                        "asset_kind": "item",
                        "description": action.get("description") or action.get("content", "")[:200],
                    }
                )
    seen: set[str] = set()
    normalized: List[Dict[str, Any]] = []
    for idx, raw in enumerate(candidates[:48]):
        item = normalize_asset_request(raw, index=idx)
        key = f"{item['namespace']}:{item['path']}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append(item)
    return normalized


def extract_sound_requests(bundle: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for key in ("sound_requests", "sound_events", "sounds"):
        value = bundle.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    if plan:
        for action in plan.get("actions") or []:
            if not isinstance(action, dict):
                continue
            content = f"{action.get('content') or ''}\n{action.get('new_content') or ''}".lower()
            if any(word in content for word in ("soundevent", "playsound", "sound_event", "sound")):
                stem = Path(str(action.get("path") or "foundry_sound")).stem
                candidates.append({"namespace": "forager_ai", "event": f"item.{stem}.use", "sound_file": f"custom/{stem}", "sound_kind": "ui_blip"})
    normalized: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for idx, raw in enumerate(candidates[:32]):
        namespace = re.sub(r"[^a-z0-9_.-]+", "_", str(raw.get("namespace") or "forager_ai").lower()).strip("_") or "forager_ai"
        event = str(raw.get("event") or f"item.foundry_sound_{idx}").replace(" ", "_").lower()
        sound_file = str(raw.get("sound_file") or f"custom/foundry_sound_{idx}").replace("\\", "/").replace(":", "/").strip("/")
        key = f"{namespace}:{event}:{sound_file}"
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "namespace": namespace,
                "event": event,
                "subtitle": str(raw.get("subtitle") or event.replace(".", " ").title()),
                "sound_file": sound_file,
                "sound_kind": str(raw.get("sound_kind") or raw.get("kind") or "magic_chime"),
                "duration_ms": raw.get("duration_ms") or 700,
                "pitch": raw.get("pitch") or 1.0,
                "volume": raw.get("volume") or 0.7,
                "loop": bool(raw.get("loop", False)),
                "generation_mode": str(raw.get("generation_mode") or "local_procedural"),
                "ai_audio_prompt": str(raw.get("ai_audio_prompt") or raw.get("prompt") or ""),
            }
        )
    return normalized


def extract_blockbench_animation_requests(bundle: Dict[str, Any], plan: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for key in ("blockbench_animations", "animation_requests", "model_animations"):
        value = bundle.get(key)
        if isinstance(value, list):
            candidates.extend([item for item in value if isinstance(item, dict)])
    normalized: List[Dict[str, Any]] = []
    for idx, raw in enumerate(candidates[:32]):
        normalized.append(
            {
                "target_texture_path": str(raw.get("target_texture_path") or raw.get("path") or f"item/foundry_asset_{idx}").replace("\\", "/").strip("/"),
                "animation_kind": str(raw.get("animation_kind") or raw.get("kind") or "idle_bob"),
                "name": str(raw.get("name") or f"foundry_animation_{idx}"),
                "length": raw.get("length") or raw.get("length_s") or 2.0,
                "loop": bool(raw.get("loop", True)),
            }
        )
    return normalized


def texture_blueprint_from_assets(asset_requests: Iterable[Dict[str, Any]], *, theme: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    textures: List[Dict[str, Any]] = []
    models: List[Dict[str, Any]] = []
    for idx, request in enumerate(asset_requests):
        spec = normalize_asset_request(request, index=idx)
        textures.append(spec)
        if spec.get("model_type") != "none":
            models.append(
                {
                    "namespace": spec["namespace"],
                    "path": spec["path"],
                    "model_type": spec["model_type"],
                    "texture_layer0": f"{spec['namespace']}:textures/{spec['path']}",
                    "uv_template": spec.get("uv_template"),
                }
            )
    return {
        "theme": theme or {"title": "AI Mod Foundry Assets", "palette": ["#44d7e8", "#7c3aed", "#1e293b"]},
        "new_textures": textures,
        "new_models": models,
        "application_plan": ["Generate assets after mod draft approval.", "Keep Blockbench sources under .forager/blockbench."],
    }


def evaluate_quality_gates(
    instance_root: str | Path,
    plan: Dict[str, Any],
    *,
    asset_requests: Optional[List[Dict[str, Any]]] = None,
    sound_requests: Optional[List[Dict[str, Any]]] = None,
    blockbench_animations: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    gates: List[Dict[str, Any]] = []
    hard_fail = False

    def add(name: str, status: str, message: str, *, severity: str = "low") -> None:
        nonlocal hard_fail
        if status == "fail":
            hard_fail = True
        gates.append({"name": name, "status": status, "severity": severity, "message": message})

    validation_errors = validate_feature_plan(str(instance_root), plan)
    if validation_errors:
        for error in validation_errors[:12]:
            add("feature_plan_schema", "fail", f"{error.path}: {error.message}", severity="high")
    else:
        add("feature_plan_schema", "pass", "FeaturePlan schema is valid.")

    paths: List[str] = []
    content_chars = 0
    for idx, action in enumerate(plan.get("actions") or []):
        if not isinstance(action, dict):
            continue
        rel = str(action.get("path") or action.get("dest_path") or action.get("target_path") or "")
        if rel:
            paths.append(rel.replace("\\", "/"))
        at = str(action.get("type") or "")
        if at in ("patch_toml", "patch_json"):
            blob = action.get("set_values") if at == "patch_toml" else action.get("merge")
            try:
                content_chars += len(json.dumps(blob, ensure_ascii=True)) if isinstance(blob, dict) else 0
            except (TypeError, ValueError):
                pass
            continue
        content = str(action.get("new_content") if at == "edit_file" else action.get("content") or "")
        content_chars += len(content)
        if re.search(r"\bwhile\s*\(\s*true\s*\)|setInterval|onTick|server\.tick|world\.tick", content, re.I):
            add("performance_budget", "warn", f"Action {idx + 1} may add tick-loop or interval logic.", severity="medium")
        if len(content) > 40000:
            add("performance_budget", "warn", f"Action {idx + 1} is very large; split into smaller files.", severity="medium")

    for rel in paths:
        pure = rel.split("?", 1)[0]
        suffix = Path(pure).suffix.lower()
        if os.path.isabs(rel) or ".." in Path(rel).parts:
            add("path_safety", "fail", f"Unsafe path: {rel}", severity="high")
        elif suffix in FORBIDDEN_EXTENSIONS:
            add("path_safety", "fail", f"Forbidden generated extension: {rel}", severity="high")
        elif suffix and suffix not in SAFE_TEXT_EXTENSIONS and suffix not in {".toml", ".ini"}:
            add("path_safety", "warn", f"Unusual generated extension: {rel}", severity="medium")
        if suffix in {".toml", ".ini"}:
            add("config_backup", "warn", f"{rel} requires backup/manual review before apply.", severity="medium")

    for action in plan.get("actions") or []:
        if not isinstance(action, dict):
            continue
        rel = str(action.get("path") or action.get("dest_path") or action.get("target_path") or "").replace("\\", "/")
        if not rel:
            continue
        at = str(action.get("type") or "")
        if at == "patch_toml":
            add("config_backup", "warn", f"{rel} TOML patch — review diff before apply.", severity="medium")
        elif at == "patch_json":
            add("config_backup", "warn", f"{rel} JSON merge — review diff before apply.", severity="low")
    if paths:
        add("path_safety", "pass", f"Reviewed {len(paths)} path(s) for containment and risky extensions.")
    else:
        add("implementation_depth", "warn", "No file actions were generated yet.", severity="medium")

    duplicate_paths = sorted({p for p in paths if paths.count(p) > 1})
    if duplicate_paths:
        add("duplicate_outputs", "warn", f"Duplicate output paths: {', '.join(duplicate_paths[:5])}", severity="medium")
    else:
        add("duplicate_outputs", "pass", "No duplicate output paths detected.")

    assets = asset_requests or []
    for asset in assets:
        ns = str(asset.get("namespace") or "")
        if not NAMESPACE_RE.match(ns):
            add("asset_namespace", "fail", f"Invalid namespace: {ns}", severity="high")
        asset_path = str(asset.get("path") or "").strip()
        if not asset_path:
            add("asset_path", "fail", f"Asset request missing path: {asset}", severity="high")
        elif _is_unsafe_relative_path(asset_path):
            add("asset_path", "fail", f"Unsafe asset path: {asset_path}", severity="high")
        elif Path(asset_path).suffix.lower() in FORBIDDEN_EXTENSIONS:
            add("asset_path", "fail", f"Forbidden asset extension: {asset_path}", severity="high")
        if str(asset.get("asset_kind") or "").lower() in {"item", "tool", "block", "ore", "entity"} and not str(asset.get("shape_language") or "").strip():
            add("asset_completeness", "warn", f"Asset request needs shape_language for {ns}:{asset_path}", severity="medium")
    if assets:
        add("asset_requests", "pass", f"Validated {len(assets)} generated texture/model request(s).")
    else:
        add("asset_requests", "warn", "No generated texture/model requests are attached.", severity="low")

    sounds = sound_requests or []
    for sound in sounds:
        ns = str(sound.get("namespace") or "")
        if not NAMESPACE_RE.match(ns):
            add("sound_namespace", "fail", f"Invalid sound namespace: {ns}", severity="high")
        event = str(sound.get("event") or "").strip()
        sound_file = str(sound.get("sound_file") or "").strip()
        if not event or not sound_file:
            add("sound_request", "fail", f"Sound request missing event or sound_file: {sound}", severity="high")
        if event and not NAMESPACE_RE.match(event):
            add("sound_event", "fail", f"Invalid sound event id: {event}", severity="high")
        if sound_file and _is_unsafe_relative_path(sound_file):
            add("sound_file", "fail", f"Unsafe sound file path: {sound_file}", severity="high")
        kind = str(sound.get("sound_kind") or "").strip()
        if kind and kind not in SOUND_KIND_ALLOWLIST:
            add("sound_kind", "warn", f"Unrecognized sound_kind '{kind}'.", severity="medium")
    if sounds:
        add("sound_requests", "pass", f"Validated {len(sounds)} sound request(s).")
    else:
        text_blob = json.dumps(plan, ensure_ascii=True).lower()
        if any(word in text_blob for word in ("sound", "audio", "chime", "cast", "hit", "impact")):
            add("sound_requests", "warn", "Plan mentions sound/audio but has no structured sound requests.", severity="medium")

    bb_anims = blockbench_animations or []
    for anim in bb_anims:
        target = str(anim.get("target_texture_path") or "").strip()
        if not target:
            add("blockbench_animation_target", "fail", f"Animation request missing target texture path: {anim}", severity="high")
        elif _is_unsafe_relative_path(target):
            add("blockbench_animation_target", "fail", f"Unsafe animation target path: {target}", severity="high")
        kind = str(anim.get("animation_kind") or "").strip()
        if kind and kind not in BLOCKBENCH_ANIMATION_ALLOWLIST:
            add("blockbench_animation_kind", "warn", f"Unrecognized Blockbench animation kind '{kind}'.", severity="medium")
        try:
            length = float(anim.get("length") or 0)
        except (TypeError, ValueError):
            length = 0
        if length <= 0 or length > 30:
            add("blockbench_animation_length", "warn", f"Animation length should be between 0 and 30 seconds for {target or 'unknown target'}.", severity="medium")
    if bb_anims:
        add("blockbench_animations", "pass", f"Validated {len(bb_anims)} Blockbench animation request(s).")

    if content_chars > 120000:
        add("complexity_budget", "warn", "Generated content is very large; prefer multiple mini-changes.", severity="medium")
    else:
        add("complexity_budget", "pass", f"Generated text size is within the review budget ({content_chars} chars).")

    score = 100
    for gate in gates:
        if gate["status"] == "fail":
            score -= 30
        elif gate["status"] == "warn":
            score -= 8
    return {
        "ok": not hard_fail,
        "score": max(0, min(100, score)),
        "verdict": "block" if hard_fail else "revise" if score < 80 else "pass",
        "gates": gates,
        "checked_at": utc_now_iso(),
    }


def build_foundry_artifact(
    *,
    instance_name: str,
    project: Dict[str, Any],
    draft: Dict[str, Any],
    gates: Dict[str, Any],
    texture_blueprint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return make_ai_artifact(
        artifact_type="forager_ai_mod_foundry_draft",
        pack_name=instance_name,
        title=f"AI Mod Foundry review: {draft.get('feature_name') or project.get('name')}",
        summary="Review generated mod logic, assets, compatibility, performance, stability, and mini-change readiness.",
        source="ai_mod_foundry",
        payload={
            "project": {k: v for k, v in project.items() if k not in {"drafts"}},
            "draft": draft,
            "quality_gates": gates,
            "texture_blueprint": texture_blueprint or {},
            "sound_requests": project.get("sound_requests") or [],
            "blockbench_animations": project.get("blockbench_animations") or [],
            "council_instructions": [
                "Evaluate the mod feature like a professional Minecraft Forge 1.20.1 pack team.",
                "Check stability, optional mod compatibility, performance risk, progression balance, asset completeness, and user testability.",
                "Block unsafe writes or plans that cannot be tested or rolled back.",
            ],
        },
    )


def save_review(instance_root: str | Path, project: Dict[str, Any], review: Dict[str, Any], *, label: str = "review") -> str:
    rdir = foundry_dir(instance_root) / "reviews"
    rdir.mkdir(parents=True, exist_ok=True)
    path = rdir / f"{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}_{label}.json"
    write_text_utf8_nobom(str(path), json.dumps(review, indent=2, ensure_ascii=False))
    project.setdefault("reviews", []).append(
        {
            "saved_at": utc_now_iso(),
            "path": path.relative_to(Path(instance_root)).as_posix(),
            "verdict": (review.get("final") or review).get("final_verdict"),
        }
    )
    save_project(instance_root, project)
    return str(path)


def maybe_run_continuous_review(
    *,
    instance_root: str | Path,
    instance_name: str,
    project: Dict[str, Any],
    draft: Dict[str, Any],
    gates: Dict[str, Any],
    texture_blueprint: Optional[Dict[str, Any]],
    api_key: str,
    model: str,
    label: str,
) -> Dict[str, Any]:
    artifact = build_foundry_artifact(
        instance_name=instance_name,
        project=project,
        draft=draft,
        gates=gates,
        texture_blueprint=texture_blueprint,
    )
    save_ai_artifact(str(instance_root), artifact, folder=".forager/ai_mod_foundry/artifacts")
    if not api_key.strip():
        review = {"final_verdict": "skipped", "issues": [], "recommended_actions": ["Set an API key to enable continuous Council review."]}
        save_review(instance_root, project, review, label=f"{label}_skipped")
        return review
    try:
        review = run_council_review(
            api_key=api_key,
            subject=f"AI Mod Foundry {label}: {instance_name}",
            artifact=artifact,
            model=model,
            timeout_s_per_call=90,
        )
        save_review(instance_root, project, review, label=label)
        return review
    except Exception as exc:
        review = {
            "final_verdict": "error",
            "issues": [{"severity": "medium", "detail": f"Council review failed: {exc}", "owner": "chair"}],
            "recommended_actions": ["Retry Council review after checking API/network settings."],
        }
        save_review(instance_root, project, review, label=f"{label}_error")
        return review


def scaffold_compiled_forge_project(
    instance_root: str | Path,
    *,
    project_name: str,
    mod_id: str,
    package: str,
    mc_version: str = "1.20.1",
) -> Dict[str, Any]:
    safe_mod_id = re.sub(r"[^a-z0-9_]+", "_", mod_id.lower()).strip("_") or "forager_generated"
    safe_name = re.sub(r"[^A-Za-z0-9_. -]+", "_", project_name).strip() or "ForagerGeneratedMod"
    package = re.sub(r"[^a-zA-Z0-9_.]+", "", package or f"com.forager.{safe_mod_id}") or f"com.forager.{safe_mod_id}"
    root = foundry_dir(instance_root) / "forge_projects" / safe_mod_id
    if root.exists():
        backup = foundry_dir(instance_root) / "backups" / "forge_projects" / f"{safe_mod_id}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(root, backup)
    java_dir = root / "src" / "main" / "java" / Path(package.replace(".", "/"))
    resource_dir = root / "src" / "main" / "resources"
    meta_dir = resource_dir / "META-INF"
    java_dir.mkdir(parents=True, exist_ok=True)
    meta_dir.mkdir(parents=True, exist_ok=True)
    write_text_utf8_nobom(str(root / "settings.gradle"), f"pluginManagement {{ repositories {{ gradlePluginPortal(); maven {{ url = 'https://maven.minecraftforge.net/' }} }} }}\nrootProject.name = '{safe_mod_id}'\n")
    write_text_utf8_nobom(
        str(root / "build.gradle"),
        "\n".join(
            [
                "plugins {",
                "    id 'java'",
                "    id 'net.minecraftforge.gradle' version '[6.0,6.2)'",
                "}",
                "",
                "group = '" + package + "'",
                "version = '0.1.0'",
                "java.toolchain.languageVersion = JavaLanguageVersion.of(17)",
                "",
                "minecraft { mappings channel: 'official', version: '" + mc_version + "' }",
                "repositories { mavenCentral(); maven { url = 'https://maven.minecraftforge.net/' } }",
                "dependencies { minecraft 'net.minecraftforge:forge:" + mc_version + "-47.2.0' }",
                "",
            ]
        ),
    )
    write_text_utf8_nobom(
        str(java_dir / f"{safe_name.replace(' ', '')}.java"),
        "\n".join(
            [
                f"package {package};",
                "",
                "import net.minecraftforge.fml.common.Mod;",
                "",
                f'@Mod("{safe_mod_id}")',
                f"public class {safe_name.replace(' ', '')} {{",
                f"    public static final String MOD_ID = \"{safe_mod_id}\";",
                "",
                f"    public {safe_name.replace(' ', '')}() {{",
                "        // Forager AI scaffold: add registries, events, and common setup after Council review.",
                "    }",
                "}",
                "",
            ]
        ),
    )
    write_text_utf8_nobom(
        str(meta_dir / "mods.toml"),
        "\n".join(
            [
                'modLoader="javafml"',
                'loaderVersion="[47,)"',
                'license="All Rights Reserved"',
                f'[[mods]]\nmodId="{safe_mod_id}"\nversion="${{file.jarVersion}}"\ndisplayName="{safe_name}"\ndescription="Generated Forge scaffold from Forager AI Mod Foundry."',
                "",
            ]
        ),
    )
    write_text_utf8_nobom(
        str(root / "README.md"),
        f"# {safe_name}\n\nGenerated by Forager AI Mod Foundry for Minecraft Forge {mc_version}.\n\n"
        "Run `gradlew build` or `gradlew runClient` after review. A Gradle wrapper is copied from Forager when available.\n",
    )
    wrapper_info: Dict[str, Any] = {}
    try:
        wrapper_info = copy_wrapper_into_directory(root)
    except FileNotFoundError as exc:
        wrapper_info = {"error": str(exc)}
    return {
        "project_root": str(root),
        "relative_root": root.relative_to(Path(instance_root)).as_posix(),
        "mod_id": safe_mod_id,
        "package": package,
        "build_ready": (root / "build.gradle").is_file() and (meta_dir / "mods.toml").is_file(),
        "warnings": ["Compiled Forge mode is advanced. Review and build in isolation before installing the jar."],
        "gradle_wrapper": wrapper_info,
    }
