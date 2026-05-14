from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SafePathResult:
    """Result of resolving a user-provided relative path inside a pack root."""

    resolved_path: str
    rel_path: str


def _normalize_rel_path(rel_path: str) -> str:
    # Keep this strict: callers must provide a relative path, no drive letters.
    rel_path = rel_path.replace("\\", "/").lstrip("/")
    if rel_path.startswith("../") or rel_path.startswith(".."):
        raise ValueError(f"Path traversal detected: {rel_path!r}")
    if ":" in rel_path:
        raise ValueError(f"Absolute/drive path not allowed: {rel_path!r}")
    return rel_path


def resolve_under_root(pack_root: str, rel_path: str) -> SafePathResult:
    pack_root_abs = os.path.realpath(pack_root)
    rel_path_norm = _normalize_rel_path(rel_path)

    resolved_path = os.path.realpath(os.path.join(pack_root_abs, rel_path_norm))
    # Ensure sandbox containment after realpath normalization.
    common = os.path.commonpath([pack_root_abs, resolved_path])
    if common != pack_root_abs:
        raise ValueError(f"Resolved path escapes pack root: {rel_path!r}")

    return SafePathResult(resolved_path=resolved_path, rel_path=rel_path_norm)


def write_text_utf8_nobom(path: str, content: str) -> None:
    """
    Write UTF-8 content with NO BOM.

    Python's encoding="utf-8" does not emit a BOM by default, but we still
    remove a leading BOM from the provided content to avoid preserving it.
    """

    if "\x00" in content:
        raise ValueError("NUL byte detected in content; refusing to write.")

    # Strip UTF-8 BOM if the caller included it.
    if content.startswith("\ufeff"):
        content = content.lstrip("\ufeff")

    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(content)


def ensure_allowed_extension(rel_path: str, allowed_extensions: Iterable[str]) -> None:
    """
    Extension allow-list check for AI-generated operations.

    allowed_extensions must include dot-prefixed extensions (e.g. ".json").
    """

    _, ext = os.path.splitext(rel_path)
    allowed = {e.lower() for e in allowed_extensions}
    if ext.lower() not in allowed:
        raise ValueError(f"Disallowed file extension for {rel_path!r}: {ext!r}")

