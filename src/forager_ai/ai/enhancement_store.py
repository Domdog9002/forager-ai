"""
Local-only stores for Forager AI enhancements: facts, per-pack notes, RAG roots.

All paths under ~/.forager_ai/ (UTF-8, no BOM).
"""

from __future__ import annotations

import json
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any, Dict, List, Optional


def _base() -> Path:
    p = Path.home() / ".forager_ai"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _read_json(path: Path, default: Any) -> Any:
    if not path.is_file():
        return deepcopy(default)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, type(default)) else deepcopy(default)
    except (OSError, json.JSONDecodeError, TypeError):
        return deepcopy(default)


def _write_json(path: Path, obj: Any) -> None:
    try:
        path.write_text(json.dumps(obj, ensure_ascii=True, indent=2), encoding="utf-8")
    except OSError:
        pass


# --- Confirmed facts (user-approved one-liners, optional pack scope) ---
FACTS_PATH = _base() / "confirmed_facts.json"


def list_facts(*, pack_key: Optional[str] = None) -> List[Dict[str, Any]]:
    """If pack_key is None, return every fact. If str (possibly empty), return global-only (no pack) or scoped to that pack."""
    raw = _read_json(FACTS_PATH, {"facts": []})
    facts = raw.get("facts") if isinstance(raw, dict) else []
    if not isinstance(facts, list):
        return []
    out: List[Dict[str, Any]] = []
    for f in facts:
        if not isinstance(f, dict):
            continue
        if pack_key is None:
            out.append(f)
            continue
        fpk = str(f.get("pack_key") or "").strip()
        pk = (pack_key or "").strip()
        if not pk:
            if not fpk:
                out.append(f)
        elif fpk == pk:
            out.append(f)
    return out


def add_fact(text: str, *, pack_key: str = "") -> Optional[str]:
    t = " ".join((text or "").split()).strip()
    if len(t) < 3:
        return None
    raw = _read_json(FACTS_PATH, {"facts": []})
    facts = raw.setdefault("facts", [])
    if not isinstance(facts, list):
        facts = []
        raw["facts"] = facts
    fid = str(uuid.uuid4())[:12]
    facts.append(
        {
            "id": fid,
            "pack_key": (pack_key or "").strip()[:200],
            "text": t[:800],
        }
    )
    facts[:] = facts[-200:]
    _write_json(FACTS_PATH, raw)
    return fid


def delete_fact(fact_id: str) -> None:
    raw = _read_json(FACTS_PATH, {"facts": []})
    facts = raw.get("facts") if isinstance(raw, dict) else []
    if not isinstance(facts, list):
        return
    raw["facts"] = [f for f in facts if isinstance(f, dict) and str(f.get("id")) != str(fact_id)]
    _write_json(FACTS_PATH, raw)


def import_facts_from_lines(text: str, *, pack_key: str = "") -> int:
    """Append each non-empty line as a confirmed fact. Returns number added."""
    n = 0
    pk = (pack_key or "").strip()[:200]
    for line in (text or "").splitlines():
        t = " ".join(line.split()).strip()
        if len(t) < 3:
            continue
        if add_fact(t, pack_key=pk):
            n += 1
    return n


def facts_context_for_prompt(pack_key: str, max_chars: int = 1200) -> str:
    global_f = list_facts(pack_key="")
    scoped = list_facts(pack_key=pack_key) if (pack_key or "").strip() else []
    seen = set()
    lines = []
    for f in global_f + scoped:
        if not isinstance(f, dict):
            continue
        key = f.get("text", "")
        if key in seen:
            continue
        seen.add(key)
        pk = str(f.get("pack_key") or "").strip()
        tag = f"[{pk}] " if pk else "[global] "
        lines.append(tag + str(f.get("text") or "")[:400])
    blob = "\n".join(lines)
    return blob[:max_chars]


# --- Per-pack profiles (topics + notes ring) ---
PROFILES_PATH = _base() / "pack_profiles.json"


def _profiles() -> Dict[str, Any]:
    return _read_json(PROFILES_PATH, {"packs": {}})


def _save_profiles(data: Dict[str, Any]) -> None:
    _write_json(PROFILES_PATH, data)


def get_pack_profile(pack_key: str) -> Dict[str, Any]:
    pk = (pack_key or "").strip() or "default"
    packs = _profiles().get("packs")
    if not isinstance(packs, dict):
        packs = {}
    prof = packs.get(pk)
    if not isinstance(prof, dict):
        prof = {"topic_ring": [], "notes": ""}
    return {
        "topic_ring": list(prof.get("topic_ring") or [])[-30:],
        "notes": str(prof.get("notes") or "")[:4000],
    }


def append_pack_topic(pack_key: str, phrase: str) -> None:
    t = " ".join((phrase or "").split()).strip()
    if not t or len(t) < 4:
        return
    pk = (pack_key or "").strip() or "default"
    data = _profiles()
    packs = data.setdefault("packs", {})
    if not isinstance(packs, dict):
        packs = {}
        data["packs"] = packs
    prof = packs.get(pk)
    if not isinstance(prof, dict):
        prof = {"topic_ring": [], "notes": ""}
    ring = list(prof.get("topic_ring") or [])
    line = t[:200]
    if ring and ring[-1] == line:
        return
    ring.append(line)
    prof["topic_ring"] = ring[-25:]
    packs[pk] = prof
    _save_profiles(data)


def set_pack_notes(pack_key: str, notes: str) -> None:
    pk = (pack_key or "").strip() or "default"
    data = _profiles()
    packs = data.setdefault("packs", {})
    if not isinstance(packs, dict):
        packs = {}
        data["packs"] = packs
    prof = packs.get(pk)
    if not isinstance(prof, dict):
        prof = {"topic_ring": [], "notes": ""}
    prof["notes"] = notes.strip()[:4000]
    packs[pk] = prof
    _save_profiles(data)


def pack_profile_context(pack_key: str, max_chars: int = 800) -> str:
    p = get_pack_profile(pack_key)
    parts = []
    if str(p.get("notes") or "").strip():
        parts.append("Pack-specific notes: " + str(p["notes"]).strip()[:max_chars])
    ring = p.get("topic_ring") or []
    if ring:
        tail = ring[-10:]
        parts.append("Recent topics for this pack:\n- " + "\n- ".join(str(x)[:160] for x in tail))
    blob = "\n\n".join(parts).strip()
    return blob[:max_chars]


# --- RAG roots (user-selected directories to index for keyword retrieval) ---
RAG_ROOTS_PATH = _base() / "rag_roots.json"


def get_rag_roots() -> List[str]:
    raw = _read_json(RAG_ROOTS_PATH, {"roots": []})
    roots = raw.get("roots") if isinstance(raw, dict) else []
    if not isinstance(roots, list):
        return []
    out = []
    for r in roots:
        s = str(r).strip()
        if s and s not in out:
            out.append(s)
    return out[:40]


def set_rag_roots(roots: List[str]) -> None:
    cleaned = []
    for r in roots or []:
        s = str(r).strip()
        if s and s not in cleaned:
            cleaned.append(s)
    _write_json(RAG_ROOTS_PATH, {"roots": cleaned[:40]})


def build_pack_enrichment_for_ai(pack_key: str, max_chars: int = 2200) -> str:
    """Confirmed facts + per-pack profile notes for AI context."""
    fc = facts_context_for_prompt(pack_key, max(max_chars // 2, 400))
    pc = pack_profile_context(pack_key, max(max_chars // 2, 400))
    parts: List[str] = []
    if fc.strip():
        parts.append("[Confirmed facts]\n" + fc.strip())
    if pc.strip():
        parts.append("[Pack profile]\n" + pc.strip())
    blob = "\n\n".join(parts).strip()
    return blob[:max_chars]
