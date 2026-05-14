"""Keyword overlap 'RAG' over user-allowed roots — no embeddings, no network."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

_MAX_FILE = 180_000
_MAX_TOTAL_FILES = 500
_ALLOWED_EXT = {
    ".md",
    ".txt",
    ".toml",
    ".json",
    ".properties",
    ".cfg",
    ".zs",
    ".js",
}


def _tokenize(q: str) -> Set[str]:
    return {t.lower() for t in re.findall(r"[A-Za-z0-9_]{3,24}", q or "")}


def _score_chunk(query_tokens: Set[str], chunk: str) -> float:
    words = re.findall(r"[A-Za-z0-9_]{3,24}", chunk.lower())
    if not words:
        return 0.0
    bag = set(words)
    inter = len(query_tokens & bag)
    if not inter:
        return 0.0
    return inter / (len(bag) ** 0.5)


def _iter_files(roots: List[str]) -> List[Path]:
    out: List[Path] = []
    seen_dirs: Set[str] = set()
    for raw in roots:
        root = Path(os.path.normpath(os.path.expanduser(raw or "")))
        if not root.is_dir():
            continue
        try:
            rk = str(root.resolve())
        except OSError:
            rk = str(root)
        if rk in seen_dirs:
            continue
        seen_dirs.add(rk)
        for dirpath, dirnames, filenames in os.walk(root):
            # prune heavy trees
            dp = Path(dirpath)
            rel = ""
            try:
                rel = dp.relative_to(root).as_posix().lower()
            except ValueError:
                pass
            if any(
                x in rel for x in (".git", "node_modules", "build", "run", "saves", "screenshots", ".gradle")
            ):
                dirnames[:] = []
                continue
            for fn in filenames:
                suf = Path(fn).suffix.lower()
                if suf not in _ALLOWED_EXT:
                    continue
                fp = dp / fn
                out.append(fp)
                if len(out) >= _MAX_TOTAL_FILES:
                    return out
    return out


def retrieve_keyword_context(
    query: str,
    roots: List[str],
    *,
    max_chunks: int = 4,
    chunk_chars: int = 1400,
) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Return concatenated snippets plus citation list for the assistant payload.
    """
    q_tokens = _tokenize(query)
    if not q_tokens or not roots:
        return "", []

    files = _iter_files(roots)
    scored: List[Tuple[float, Path, str]] = []
    for fp in files:
        try:
            if fp.stat().st_size > _MAX_FILE:
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) < 40:
            continue
        for i in range(0, len(text), chunk_chars):
            chunk = text[i : i + chunk_chars]
            sc = _score_chunk(q_tokens, chunk)
            if sc > 0:
                scored.append((sc, fp, chunk.strip()))
    scored.sort(key=lambda x: -x[0])
    top = scored[: max_chunks * 3]
    # dedupe by path, keep best chunk per file
    best_by_file: Dict[str, Tuple[float, Path, str]] = {}
    for sc, fp, chunk in top:
        key = str(fp)
        if key not in best_by_file or sc > best_by_file[key][0]:
            best_by_file[key] = (sc, fp, chunk)

    picks = sorted(best_by_file.values(), key=lambda x: -x[0])[:max_chunks]
    cite: List[Dict[str, Any]] = []
    parts: List[str] = []
    for sc, fp, chunk in picks:
        try:
            rel = fp.as_posix()
        except OSError:
            rel = str(fp)
        cite.append({"path": rel, "score": round(sc, 3)})
        parts.append(f"--- {rel} (keyword Snippet) ---\n{chunk[:chunk_chars]}")

    return "\n\n".join(parts), cite


def list_scored_chunks(
    query: str,
    roots: List[str],
    *,
    chunk_chars: int = 1400,
    limit: int = 100,
) -> List[Tuple[float, str, str]]:
    """
    Candidate (score, path string, chunk) tuples for embedding reranking.
    Sorted by keyword score descending; may include multiple chunks per file.
    """
    q_tokens = _tokenize(query)
    if not q_tokens or not roots:
        return []

    files = _iter_files(roots)
    scored: List[Tuple[float, Path, str]] = []
    for fp in files:
        try:
            if fp.stat().st_size > _MAX_FILE:
                continue
            text = fp.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if len(text) < 40:
            continue
        for i in range(0, len(text), chunk_chars):
            chunk = text[i : i + chunk_chars].strip()
            if len(chunk) < 40:
                continue
            sc = _score_chunk(q_tokens, chunk)
            if sc > 0:
                scored.append((sc, fp, chunk))
    scored.sort(key=lambda x: -x[0])
    out: List[Tuple[float, str, str]] = []
    for sc, fp, chunk in scored[:limit]:
        try:
            rel = fp.as_posix()
        except OSError:
            rel = str(fp)
        out.append((sc, rel, chunk[:chunk_chars]))
    return out
