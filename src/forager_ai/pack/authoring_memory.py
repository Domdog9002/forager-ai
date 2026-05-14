"""Per-pack authoring memory under ``.forager/`` — goals, decision log, optional hub feedback."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from ..fs.safe_writer import write_text_utf8_nobom

AUTHORING_BRIEF_FILE = "authoring_brief.json"
DECISION_LOG_FILE = "decision_log.jsonl"
HUB_FEEDBACK_FILE = "hub_feedback.jsonl"
GOLDEN_PROMPTS_FILE = "golden_prompts.json"


def _forager_dir(pack_root: str) -> Path:
    return Path(pack_root).expanduser().resolve() / ".forager"


def default_authoring_brief() -> Dict[str, str]:
    return {
        "goals": "",
        "non_goals": "",
        "target_audience": "",
        "today_focus": "",
    }


def load_authoring_brief(pack_root: str) -> Dict[str, str]:
    p = _forager_dir(pack_root) / AUTHORING_BRIEF_FILE
    if not p.is_file():
        return default_authoring_brief()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_authoring_brief()
    if not isinstance(raw, dict):
        return default_authoring_brief()
    out = default_authoring_brief()
    for k in out:
        v = raw.get(k)
        out[k] = str(v).strip()[:4000] if v is not None else ""
    return out


def save_authoring_brief(pack_root: str, brief: Dict[str, str]) -> None:
    d = _forager_dir(pack_root)
    d.mkdir(parents=True, exist_ok=True)
    base = default_authoring_brief()
    merged = {k: str(brief.get(k) or "").strip()[:4000] for k in base}
    path = d / AUTHORING_BRIEF_FILE
    write_text_utf8_nobom(str(path), json.dumps(merged, indent=2, ensure_ascii=False))


def format_authoring_brief_for_context(brief: Dict[str, str], *, max_chars: int = 2200) -> str:
    parts: List[str] = []
    if brief.get("goals"):
        parts.append(f"Goals:\n{brief['goals']}")
    if brief.get("non_goals"):
        parts.append(f"Non-goals / out of scope:\n{brief['non_goals']}")
    if brief.get("target_audience"):
        parts.append(f"Target audience:\n{brief['target_audience']}")
    if brief.get("today_focus"):
        parts.append(f"Today's focus:\n{brief['today_focus']}")
    blob = "\n\n".join(parts).strip()
    if len(blob) > max_chars:
        return blob[: max_chars - 24] + "\n… (authoring brief truncated)"
    return blob


def _read_jsonl_tail(path: Path, *, max_entries: int) -> List[Dict[str, Any]]:
    if not path.is_file() or max_entries <= 0:
        return []
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []
    tail = lines[-max_entries:]
    out: List[Dict[str, Any]] = []
    for ln in tail:
        ln = ln.strip()
        if not ln:
            continue
        try:
            row = json.loads(ln)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def load_recent_decisions(pack_root: str, *, max_entries: int = 18) -> List[Dict[str, Any]]:
    return _read_jsonl_tail(_forager_dir(pack_root) / DECISION_LOG_FILE, max_entries=max_entries)


def format_decision_log_for_context(
    entries: List[Dict[str, Any]],
    *,
    max_chars: int = 3200,
) -> str:
    if not entries:
        return ""
    lines: List[str] = ["Recent settled decisions (newest last; honor these unless user overrides):"]
    for e in entries:
        ts = str(e.get("ts") or "")[:32]
        who = str(e.get("confirmed_by") or "author")[:48]
        summ = str(e.get("summary") or "").strip().replace("\n", " ")[:420]
        if summ:
            lines.append(f"- [{ts}] ({who}) {summ}")
    blob = "\n".join(lines).strip()
    if len(blob) > max_chars:
        return blob[: max_chars - 24] + "\n… (decision log truncated)"
    return blob


def append_decision_log(pack_root: str, *, summary: str, confirmed_by: str = "author") -> None:
    s = str(summary or "").strip()
    if not s:
        return
    d = _forager_dir(pack_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / DECISION_LOG_FILE
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "summary": s[:2000],
        "confirmed_by": str(confirmed_by or "author")[:120],
    }
    line = json.dumps(row, ensure_ascii=True) + "\n"
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError:
        pass


def append_hub_feedback(
    pack_root: str,
    *,
    thumb: str,
    tag: str = "",
    note: str = "",
) -> None:
    d = _forager_dir(pack_root)
    d.mkdir(parents=True, exist_ok=True)
    path = d / HUB_FEEDBACK_FILE
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "thumb": str(thumb or "")[:24],
        "tag": str(tag or "")[:80],
        "note": str(note or "").strip()[:1200],
    }
    line = json.dumps(row, ensure_ascii=True) + "\n"
    try:
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)
    except OSError:
        pass


def default_golden_prompts() -> Dict[str, Any]:
    return {"prompts": []}


def load_golden_prompts(pack_root: str) -> Dict[str, Any]:
    p = _forager_dir(pack_root) / GOLDEN_PROMPTS_FILE
    if not p.is_file():
        return default_golden_prompts()
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default_golden_prompts()
    if not isinstance(raw, dict):
        return default_golden_prompts()
    pr = raw.get("prompts")
    if not isinstance(pr, list):
        return default_golden_prompts()
    clean: List[str] = []
    for it in pr[:48]:
        s = str(it).strip()
        if s and s not in clean:
            clean.append(s[:800])
    return {"prompts": clean}


def save_golden_prompts(pack_root: str, prompts: List[str]) -> None:
    d = _forager_dir(pack_root)
    d.mkdir(parents=True, exist_ok=True)
    clean: List[str] = []
    for it in prompts[:48]:
        s = str(it).strip()
        if s and s not in clean:
            clean.append(s[:800])
    path = d / GOLDEN_PROMPTS_FILE
    write_text_utf8_nobom(str(path), json.dumps({"prompts": clean}, indent=2, ensure_ascii=False))


def format_golden_prompts_for_context(prompts: List[str], *, max_chars: int = 3200) -> str:
    if not prompts:
        return ""
    lines = [
        "Golden / regression prompts (re-run after prompt or model changes; `.forager/golden_prompts.json`):",
        "",
    ]
    for i, p in enumerate(prompts[:36], 1):
        q = p.replace("\n", " ").strip()
        if q:
            lines.append(f"{i}. {q[:700]}")
    blob = "\n".join(lines).strip()
    if len(blob) > max_chars:
        return blob[: max_chars - 36] + "\n… (golden prompts truncated)"
    return blob
