from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Literal

from .structured_patch import validate_set_values_types


@dataclass(frozen=True)
class FeaturePlanValidationError:
    path: str
    message: str


FeaturePlanActionType = Literal[
    "edit_file",
    "add_file",
    "add_asset",
    "add_compat",
    "patch_toml",
    "patch_json",
]


def validate_feature_plan(pack_root: str, plan: Dict[str, Any]) -> List[FeaturePlanValidationError]:
    """
    Validate the minimal FeaturePlan structure.

    This milestone focuses on the apply engine scaffold, so validation is strict
    about structure and conservative about supported operations.
    """

    errors: List[FeaturePlanValidationError] = []

    if not isinstance(plan, dict):
        errors.append(FeaturePlanValidationError(path="$", message="FeaturePlan must be a JSON object/dict."))
        return errors

    feature_name = plan.get("feature_name")
    if not isinstance(feature_name, str) or not feature_name.strip():
        errors.append(FeaturePlanValidationError(path="feature_name", message="feature_name must be a non-empty string."))

    actions = plan.get("actions")
    if not isinstance(actions, list):
        errors.append(FeaturePlanValidationError(path="actions", message="actions must be an array."))
        return errors

    for i, action in enumerate(actions):
        a_path = f"actions[{i}]"
        if not isinstance(action, dict):
            errors.append(FeaturePlanValidationError(path=a_path, message="Action must be an object."))
            continue

        action_type = action.get("type")
        if action_type not in (
            "edit_file",
            "add_file",
            "add_asset",
            "add_compat",
            "patch_toml",
            "patch_json",
        ):
            errors.append(
                FeaturePlanValidationError(
                    path=f"{a_path}.type",
                    message=(
                        "type must be one of: edit_file, add_file, add_asset, add_compat, "
                        "patch_toml, patch_json."
                    ),
                )
            )
            continue

        rel_path = action.get("path") or action.get("dest_path") or action.get("target_path")
        if action_type in ("edit_file", "add_file", "add_asset", "patch_toml", "patch_json"):
            if not isinstance(rel_path, str) or not rel_path.strip():
                errors.append(FeaturePlanValidationError(path=f"{a_path}.path", message="path must be a non-empty string."))

        if action_type == "edit_file":
            # Supported now: new_content (replace whole file)
            if "new_content" not in action:
                errors.append(FeaturePlanValidationError(path=f"{a_path}.new_content", message="edit_file requires new_content."))
            elif not isinstance(action.get("new_content"), str):
                errors.append(FeaturePlanValidationError(path=f"{a_path}.new_content", message="new_content must be a string."))

        if action_type == "add_file":
            if "content" not in action:
                errors.append(FeaturePlanValidationError(path=f"{a_path}.content", message="add_file requires content."))
            elif not isinstance(action.get("content"), str):
                errors.append(FeaturePlanValidationError(path=f"{a_path}.content", message="content must be a string."))

        if action_type == "add_asset":
            # MVP: allow add_asset to behave like add_file with content.
            # Later milestones can add binary assets, archives, etc.
            if "content" not in action:
                errors.append(FeaturePlanValidationError(path=f"{a_path}.content", message="add_asset requires content (MVP text asset)."))
            elif not isinstance(action.get("content"), str):
                errors.append(FeaturePlanValidationError(path=f"{a_path}.content", message="content must be a string."))

        if action_type == "add_compat":
            if not isinstance(action.get("rule_name"), str) or not action.get("rule_name", "").strip():
                errors.append(FeaturePlanValidationError(path=f"{a_path}.rule_name", message="add_compat requires non-empty rule_name."))
            affected_mods = action.get("affected_mods")
            if not isinstance(affected_mods, list) or not all(isinstance(x, str) for x in affected_mods):
                errors.append(FeaturePlanValidationError(path=f"{a_path}.affected_mods", message="affected_mods must be a list of strings."))
            if not isinstance(action.get("description"), str) or not action.get("description", "").strip():
                errors.append(FeaturePlanValidationError(path=f"{a_path}.description", message="add_compat requires non-empty description."))

        if action_type == "patch_toml":
            if not str(rel_path).lower().endswith(".toml"):
                errors.append(
                    FeaturePlanValidationError(path=f"{a_path}.path", message="patch_toml requires a .toml path.")
                )
            sv = action.get("set_values")
            if not isinstance(sv, dict) or not sv:
                errors.append(
                    FeaturePlanValidationError(path=f"{a_path}.set_values", message="patch_toml requires non-empty set_values object.")
                )
            elif not all(isinstance(k, str) and k.strip() for k in sv.keys()):
                errors.append(
                    FeaturePlanValidationError(
                        path=f"{a_path}.set_values",
                        message="patch_toml set_values keys must be non-empty strings (dotted paths).",
                    )
                )
            else:
                bad = validate_set_values_types(sv)
                if bad:
                    errors.append(FeaturePlanValidationError(path=f"{a_path}.set_values", message=bad))

        if action_type == "patch_json":
            if not str(rel_path).lower().endswith(".json"):
                errors.append(
                    FeaturePlanValidationError(path=f"{a_path}.path", message="patch_json requires a .json path.")
                )
            mg = action.get("merge")
            if not isinstance(mg, dict):
                errors.append(
                    FeaturePlanValidationError(path=f"{a_path}.merge", message="patch_json requires merge object.")
                )
            elif not mg:
                errors.append(
                    FeaturePlanValidationError(path=f"{a_path}.merge", message="patch_json merge must be non-empty.")
                )
            else:
                bad = validate_set_values_types(mg)
                if bad:
                    errors.append(FeaturePlanValidationError(path=f"{a_path}.merge", message=bad))

    return errors

