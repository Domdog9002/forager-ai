"""
Deep-merge JSON and dotted-key TOML patches for feature plans.

Uses ``tomllib`` on Python 3.11+ and ``tomli`` on 3.10; serializes with ``tomli_w``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, Mapping, MutableMapping


def deep_merge_json(base: Mapping[str, Any], overlay: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge dicts; lists and scalars from ``overlay`` replace."""
    out: Dict[str, Any] = dict(base)
    for key, val in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge_json(out[key], val)  # type: ignore[arg-type]
        else:
            out[key] = val
    return out


def _toml_loads(src: str) -> Dict[str, Any]:
    if sys.version_info >= (3, 11):
        import tomllib

        data = tomllib.loads(src)
    else:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError as exc:
            raise RuntimeError(
                "Reading TOML requires Python 3.11+ or the `tomli` package (install project dependencies)."
            ) from exc
        data = tomllib.loads(src)
    if not isinstance(data, dict):
        raise ValueError("TOML root must be a table (object).")
    return data


def _toml_dumps(data: Mapping[str, Any]) -> str:
    try:
        import tomli_w
    except ImportError as exc:
        raise RuntimeError("Writing TOML requires the `tomli-w` package (install project dependencies).") from exc
    return tomli_w.dumps(dict(data))


def _set_dotted(root: MutableMapping[str, Any], dotted: str, value: Any) -> None:
    parts = [p for p in str(dotted).strip().split(".") if p]
    if not parts:
        raise ValueError("Empty dotted key.")
    cur: MutableMapping[str, Any] = root
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt  # type: ignore[assignment]
    cur[parts[-1]] = value


def apply_toml_set_values(existing_text: str, set_values: Mapping[str, Any]) -> str:
    """
    Parse ``existing_text`` as TOML, apply ``set_values`` (dotted keys → JSON-like values), re-serialize.
    """
    tree = _toml_loads(existing_text or "")
    for k, v in set_values.items():
        key = str(k).strip()
        if not key:
            continue
        _set_dotted(tree, key, v)
    return _toml_dumps(tree)


def apply_json_merge(existing_text: str, merge: Mapping[str, Any]) -> str:
    base: Dict[str, Any] = {}
    raw = (existing_text or "").strip()
    if raw:
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("Existing JSON file is not valid JSON; refuse to patch.") from exc
        if not isinstance(loaded, dict):
            raise ValueError("JSON patch target must be a JSON object at the root.")
        base = loaded
    merged = deep_merge_json(base, merge)
    return json.dumps(merged, indent=2, ensure_ascii=True) + "\n"


def read_text(path: str) -> str:
    p = Path(path)
    if not p.is_file():
        return ""
    return p.read_text(encoding="utf-8", errors="replace")


def compute_patch_toml_content(pack_root: str, rel_path: str, set_values: Mapping[str, Any]) -> str:
    abs_path = str(Path(pack_root) / rel_path.replace("\\", "/").lstrip("/"))
    prior = read_text(abs_path)
    return apply_toml_set_values(prior, set_values)


def compute_patch_json_content(pack_root: str, rel_path: str, merge: Mapping[str, Any]) -> str:
    abs_path = str(Path(pack_root) / rel_path.replace("\\", "/").lstrip("/"))
    prior = read_text(abs_path)
    return apply_json_merge(prior, merge)


def validate_set_values_types(obj: Any, *, prefix: str = "$") -> str | None:
    """Return error message or None if ``obj`` is JSON-serializable (no custom types)."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            err = validate_set_values_types(v, prefix=f"{prefix}.{k}")
            if err:
                return err
        return None
    if isinstance(obj, list):
        for i, v in enumerate(obj):
            err = validate_set_values_types(v, prefix=f"{prefix}[{i}]")
            if err:
                return err
        return None
    if isinstance(obj, (str, int, float, bool)) or obj is None:
        return None
    return f"{prefix}: unsupported value type {type(obj).__name__}"
