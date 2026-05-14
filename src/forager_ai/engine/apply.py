from __future__ import annotations

import json
import os
import shutil
from datetime import datetime, timezone
from dataclasses import dataclass
from difflib import unified_diff
from typing import Any, Dict, List, Sequence

from .feature_plan import validate_feature_plan
from .structured_patch import compute_patch_json_content, compute_patch_toml_content
from ..trace.change_log import append_change_trace
from ..fs.safe_writer import ensure_allowed_extension, resolve_under_root, write_text_utf8_nobom
from ..pack.manifest import init_pack_manifest, record_feature_applied, register_compat_in_manifest
from ..pack.compat_registry import add_compat_rule


DEFAULT_TEXT_EXTENSIONS = [
    ".txt",
    ".json",
    ".toml",
    ".js",
    ".kjs",
    ".mcmeta",
    ".yml",
    ".yaml",
    ".cfg",
    ".properties",
]


@dataclass(frozen=True)
class ApplyResult:
    feature_name: str
    files_written: List[str]
    actions_executed: int
    checkpoint_id: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _checkpoints_dir(pack_root: str) -> str:
    path = os.path.join(pack_root, ".forager", "checkpoints")
    os.makedirs(path, exist_ok=True)
    return path


def _create_checkpoint(
    pack_root: str,
    feature_name: str,
    files_to_snapshot: List[str],
) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    safe_name = "".join(ch if ch.isalnum() else "_" for ch in feature_name.lower()).strip("_") or "feature"
    checkpoint_id = f"{stamp}_{safe_name}"
    cp_root = os.path.join(_checkpoints_dir(pack_root), checkpoint_id)
    os.makedirs(cp_root, exist_ok=True)

    meta = {
        "checkpoint_id": checkpoint_id,
        "feature_name": feature_name,
        "created_at": _utc_now_iso(),
        "files": [],
    }
    for rel in sorted(set(files_to_snapshot)):
        src = os.path.join(pack_root, rel)
        rel_norm = rel.replace("\\", "/")
        backup = os.path.join(cp_root, rel_norm)
        exists_before = os.path.exists(src)
        meta["files"].append({"path": rel_norm, "existed_before": exists_before})
        if exists_before:
            os.makedirs(os.path.dirname(backup), exist_ok=True)
            shutil.copy2(src, backup)

    write_text_utf8_nobom(
        os.path.join(cp_root, "checkpoint.meta.json"),
        json.dumps(meta, indent=2, ensure_ascii=True),
    )
    return checkpoint_id


def list_checkpoints(pack_root: str) -> List[Dict[str, Any]]:
    cp_dir = _checkpoints_dir(pack_root)
    rows: List[Dict[str, Any]] = []
    for name in sorted(os.listdir(cp_dir), reverse=True):
        meta_path = os.path.join(cp_dir, name, "checkpoint.meta.json")
        if not os.path.exists(meta_path):
            continue
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                rows.append(json.load(f))
        except Exception:
            continue
    return rows


def rollback_checkpoint(pack_root: str, checkpoint_id: str) -> Dict[str, Any]:
    cp_root = os.path.join(_checkpoints_dir(pack_root), checkpoint_id)
    meta_path = os.path.join(cp_root, "checkpoint.meta.json")
    if not os.path.exists(meta_path):
        raise FileNotFoundError(f"Checkpoint not found: {checkpoint_id}")
    with open(meta_path, "r", encoding="utf-8") as f:
        meta = json.load(f)

    restored: List[str] = []
    deleted: List[str] = []

    for entry in meta.get("files", []):
        rel = entry["path"]
        existed_before = bool(entry.get("existed_before"))
        target = os.path.join(pack_root, rel)
        backup = os.path.join(cp_root, rel)
        if existed_before:
            os.makedirs(os.path.dirname(target), exist_ok=True)
            shutil.copy2(backup, target)
            restored.append(rel)
        else:
            if os.path.exists(target):
                os.remove(target)
                deleted.append(rel)

    return {"checkpoint_id": checkpoint_id, "restored": restored, "deleted": deleted}


def save_feature_plan(pack_root: str, payload: Dict[str, Any], *, prefix: str = "generated_plan") -> str:
    plans_dir = os.path.join(pack_root, "plans")
    os.makedirs(plans_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    filename = f"{prefix}_{stamp}.json"
    path = os.path.join(plans_dir, filename)
    write_text_utf8_nobom(path, json.dumps(payload, indent=2, ensure_ascii=True))
    return path


def _compute_diff(pack_root: str, rel_path: str, new_content: str) -> str:
    abs_path = os.path.join(pack_root, rel_path)
    old = ""
    if os.path.exists(abs_path):
        with open(abs_path, "r", encoding="utf-8", errors="replace") as f:
            old = f.read()
    old_lines = old.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff = unified_diff(old_lines, new_lines, fromfile=f"a/{rel_path}", tofile=f"b/{rel_path}")
    return "".join(diff)


def _ensure_pack_root_exists(pack_root: str) -> None:
    if not os.path.isdir(pack_root):
        raise FileNotFoundError(f"pack_root does not exist or is not a directory: {pack_root!r}")


def preview_feature_plan(pack_root: str, plan: Dict[str, Any], *, allowed_extensions: Sequence[str] = DEFAULT_TEXT_EXTENSIONS) -> Dict[str, Any]:
    """
    Validate and simulate the FeaturePlan application.

    This does not write files; it only computes a change summary.
    """
    _ensure_pack_root_exists(pack_root)

    errors = validate_feature_plan(pack_root, plan)
    if errors:
        return {
            "ok": False,
            "errors": [{"path": e.path, "message": e.message} for e in errors],
        }

    actions = plan.get("actions", [])
    files_to_write: List[str] = []
    feature_name = plan.get("feature_name", "")
    diffs: List[Dict[str, str]] = []
    compat_actions: List[Dict[str, Any]] = []

    for action in actions:
        action_type = action.get("type")
        if action_type in ("edit_file", "add_file", "add_asset", "patch_toml", "patch_json"):
            rel_path = action.get("path") or action.get("dest_path") or action.get("target_path")
            # Containment check
            resolved = resolve_under_root(pack_root, rel_path)
            ensure_allowed_extension(resolved.rel_path, allowed_extensions)
            files_to_write.append(resolved.rel_path)
            if action_type == "edit_file":
                next_content = action.get("new_content", "")
            elif action_type in ("add_file", "add_asset"):
                next_content = action.get("content", "")
            elif action_type == "patch_toml":
                next_content = compute_patch_toml_content(
                    pack_root, resolved.rel_path, action.get("set_values") or {}
                )
            else:
                next_content = compute_patch_json_content(
                    pack_root, resolved.rel_path, action.get("merge") or {}
                )
            diffs.append({"path": resolved.rel_path, "diff": _compute_diff(pack_root, resolved.rel_path, next_content)})
        elif action_type == "add_compat":
            compat_actions.append(
                {
                    "rule_name": action.get("rule_name", ""),
                    "affected_mods": action.get("affected_mods", []),
                    "description": action.get("description", ""),
                }
            )

    return {
        "ok": True,
        "feature_name": feature_name,
        "actions_executed": len(actions),
        "files_to_write": files_to_write,
        "compat_actions": compat_actions,
        "diffs": diffs,
    }


def apply_feature_plan(
    pack_root: str,
    plan: Dict[str, Any],
    *,
    update_manifest: bool = True,
    allowed_extensions: Sequence[str] = DEFAULT_TEXT_EXTENSIONS,
) -> ApplyResult:
    _ensure_pack_root_exists(pack_root)

    errors = validate_feature_plan(pack_root, plan)
    if errors:
        msg = "\n".join([f"- {e.path}: {e.message}" for e in errors])
        raise ValueError(f"FeaturePlan validation failed:\n{msg}")

    feature_name = str(plan.get("feature_name", "")).strip()
    actions = plan.get("actions", [])

    written: List[str] = []
    compat_written: List[str] = []

    files_for_checkpoint: List[str] = []
    for action in actions:
        if action.get("type") in ("edit_file", "add_file", "add_asset", "patch_toml", "patch_json"):
            rel_path = action.get("path") or action.get("dest_path") or action.get("target_path")
            resolved = resolve_under_root(pack_root, rel_path)
            files_for_checkpoint.append(resolved.rel_path)

    checkpoint_id = _create_checkpoint(pack_root, feature_name, files_for_checkpoint)

    for action in actions:
        action_type = action.get("type")
        if action_type in ("edit_file", "add_file", "add_asset", "patch_toml", "patch_json"):
            rel_path = action.get("path") or action.get("dest_path") or action.get("target_path")
            resolved = resolve_under_root(pack_root, rel_path)
            ensure_allowed_extension(resolved.rel_path, allowed_extensions)

            if action_type == "edit_file":
                content = action["new_content"]
            elif action_type in ("add_file", "add_asset"):
                content = action["content"]
            elif action_type == "patch_toml":
                content = compute_patch_toml_content(
                    pack_root, resolved.rel_path, action.get("set_values") or {}
                )
            else:
                content = compute_patch_json_content(
                    pack_root, resolved.rel_path, action.get("merge") or {}
                )
            write_text_utf8_nobom(resolved.resolved_path, content)
            written.append(resolved.rel_path)
        elif action_type == "add_compat":
            entry = add_compat_rule(
                pack_root,
                rule_name=action["rule_name"],
                affected_mods=action["affected_mods"],
                description=action["description"],
                source="ai",
            )
            register_compat_in_manifest(
                pack_root,
                rule_id=entry["rule_id"],
                rule_name=entry["rule_name"],
                affected_mods=entry["affected_mods"],
                description=entry["description"],
            )
            compat_written.append(entry["rule_id"])
        else:
            # Should not happen because validator checks type.
            raise ValueError(f"Unsupported action type: {action_type!r}")

    if update_manifest:
        try:
            record_feature_applied(
                pack_root,
                feature_name=feature_name,
                actions_count=len(actions),
                changes={
                    "files_written": written,
                    "compat_rules_written": compat_written,
                    "checkpoint_id": checkpoint_id,
                },
            )
        except FileNotFoundError:
            # Scaffold-friendly behavior: if pack.manifest.json is missing, create it first.
            init_pack_manifest(pack_root)
            record_feature_applied(
                pack_root,
                feature_name=feature_name,
                actions_count=len(actions),
                changes={
                    "files_written": written,
                    "compat_rules_written": compat_written,
                    "checkpoint_id": checkpoint_id,
                },
            )

    append_change_trace(
        pack_root,
        feature_name=feature_name,
        checkpoint_id=checkpoint_id,
        files_written=written,
        compat_written=compat_written,
        actions_executed=len(actions),
    )

    return ApplyResult(
        feature_name=feature_name,
        files_written=written,
        actions_executed=len(actions),
        checkpoint_id=checkpoint_id,
    )


def apply_feature_plan_from_json_file(
    pack_root: str,
    plan_json_path: str,
    *,
    update_manifest: bool = True,
) -> ApplyResult:
    with open(plan_json_path, "r", encoding="utf-8") as f:
        plan = json.load(f)

    return apply_feature_plan(pack_root, plan, update_manifest=update_manifest)

