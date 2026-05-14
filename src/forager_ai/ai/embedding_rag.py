"""
Embedding-based retrieval via OpenRouter /v1/embeddings. Caches vectors under ~/.forager_ai/embed_cache/.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

from .light_rag import list_scored_chunks, retrieve_keyword_context

OPENROUTER_EMBEDDINGS_URL = "https://openrouter.ai/api/v1/embeddings"
DEFAULT_EMBEDDING_MODEL = "openai/text-embedding-3-small"


def _cache_dir() -> Path:
    d = Path.home() / ".forager_ai" / "embed_cache"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _chunk_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", errors="ignore")).hexdigest()


def _load_vec(h: str) -> Optional[List[float]]:
    p = _cache_dir() / f"{h}.json"
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        vec = data.get("embedding")
        if isinstance(vec, list) and vec and isinstance(vec[0], (int, float)):
            return [float(x) for x in vec]
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return None


def _save_vec(h: str, vec: List[float]) -> None:
    try:
        (_cache_dir() / f"{h}.json").write_text(
            json.dumps({"embedding": vec}, ensure_ascii=True),
            encoding="utf-8",
        )
    except OSError:
        pass


def _cosine(a: List[float], b: List[float]) -> float:
    if len(a) != len(b) or not a:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na <= 0 or nb <= 0:
        return 0.0
    return dot / (na * nb)


def _embed_batch(texts: List[str], *, api_key: str, model: str, timeout_s: int = 75) -> List[List[float]]:
    if not api_key.strip() or not texts:
        return []
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body: Dict[str, Any] = {"model": model, "input": texts}
    resp = requests.post(OPENROUTER_EMBEDDINGS_URL, headers=headers, json=body, timeout=timeout_s)
    resp.raise_for_status()
    data = resp.json()
    rows = data.get("data") or []
    out: List[List[float]] = []
    for item in sorted(rows, key=lambda x: int(x.get("index", 0))):
        emb = item.get("embedding")
        if isinstance(emb, list):
            out.append([float(x) for x in emb])
    return out


def retrieve_embedding_rag(
    query: str,
    roots: List[str],
    *,
    api_key: str,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    max_chunks: int = 6,
    prefilter_limit: int = 96,
    chunk_chars: int = 1700,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    meta: Dict[str, Any] = {"mode": "embedding", "model": embedding_model}
    q = (query or "").strip()[:8000]
    if not q:
        return "", [], meta

    candidates = list_scored_chunks(q, roots, chunk_chars=chunk_chars, limit=prefilter_limit)
    if not candidates:
        return "", [], {**meta, "note": "no_prefilter_matches"}

    # --- query vector ---
    qh = _chunk_hash(q)
    q_vec = _load_vec(qh)
    if not q_vec:
        try:
            qv = _embed_batch([q], api_key=api_key, model=embedding_model)
            q_vec = qv[0] if qv else []
            if q_vec:
                _save_vec(qh, q_vec)
        except (requests.RequestException, IndexError, KeyError, ValueError, TypeError):
            meta["error"] = "query_embed_failed"
            return "", [], meta
    if not q_vec:
        return "", [], {**meta, "error": "empty_query_vector"}

    # --- chunk vectors (cache + batch) ---
    pending_text: List[str] = []
    pending_hashes: List[str] = []
    chunk_vecs: Dict[str, List[float]] = {}
    ranked_data: List[Tuple[float, str, str, float]] = []  # blend, path, chunk, kw_sc

    for kw_sc, path_str, chunk in candidates:
        ch = _chunk_hash(chunk)
        cv = _load_vec(ch)
        if cv:
            chunk_vecs[ch] = cv
        else:
            pending_text.append(chunk[:8000])
            pending_hashes.append(ch)

    batch_size = 24
    for off in range(0, len(pending_text), batch_size):
        batch = pending_text[off : off + batch_size]
        bh = pending_hashes[off : off + batch_size]
        try:
            vecs = _embed_batch(batch, api_key=api_key, model=embedding_model)
        except (requests.RequestException, KeyError, ValueError, TypeError):
            meta["error"] = "chunk_embed_failed"
            return "", [], meta
        for i, h in enumerate(bh):
            if i < len(vecs):
                chunk_vecs[h] = vecs[i]
                _save_vec(h, vecs[i])

    for kw_sc, path_str, chunk in candidates:
        ch = _chunk_hash(chunk)
        cv = chunk_vecs.get(ch)
        if not cv:
            continue
        sim = _cosine(q_vec, cv)
        blend = 0.55 * sim + 0.45 * min(1.0, float(kw_sc) / 8.0)
        ranked_data.append((blend, path_str, chunk, float(kw_sc)))

    ranked_data.sort(key=lambda x: -x[0])
    top = ranked_data[:max_chunks]
    cite: List[Dict[str, Any]] = []
    parts: List[str] = []
    for blend, path_str, chunk, kw_sc in top:
        cite.append({"path": path_str, "blended": round(blend, 4), "keyword_prefilter": round(kw_sc, 3)})
        parts.append(f"--- {path_str} (embedding match) ---\n{chunk[:chunk_chars]}")
    meta["chunks_used"] = len(top)
    return "\n\n".join(parts), cite, meta


def retrieve_for_assistant(
    query: str,
    roots: List[str],
    *,
    api_key: str,
    use_embedding_rag: bool = True,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> Tuple[str, List[Dict[str, Any]], Dict[str, Any]]:
    if use_embedding_rag and api_key.strip() and roots:
        try:
            text, cite, m = retrieve_embedding_rag(
                query,
                roots,
                api_key=api_key,
                embedding_model=embedding_model or DEFAULT_EMBEDDING_MODEL,
            )
            if text.strip():
                return text, cite, m
        except Exception:
            pass
    t2, c2 = retrieve_keyword_context(query, roots, max_chunks=6, chunk_chars=1700)
    return t2, c2, {"mode": "keyword", "fallback": True}
