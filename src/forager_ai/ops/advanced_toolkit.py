from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List

from ..analysis.mod_graph import build_graph
from ..sync.drift import compare_pack_roots
from ..diagnostics.performance import profile_pack


def suggest_dependency_resolution(manifest: Dict[str, Any]) -> Dict[str, Any]:
    graph = build_graph(manifest)
    suggestions: List[str] = []
    hard = [e for e in graph.get("edges", []) if e.get("relation") == "hard_conflict"]
    for e in hard:
        a, b = e.get("src"), e.get("dst")
        suggestions.append(f"Hard conflict `{a}` vs `{b}`: remove or replace one mod; document choice in compat rules.")
    soft = [e for e in graph.get("edges", []) if e.get("relation") == "soft_conflict"]
    for e in soft[:12]:
        suggestions.append(f"Soft conflict `{e.get('src')}` vs `{e.get('dst')}`: tune configs/progression or add guidance rule.")
    return {
        "hard_edges": hard,
        "soft_edges": soft,
        "suggestions": suggestions[:24],
    }


def score_mod_update_risk(old_version: str, new_version: str) -> Dict[str, Any]:
    o = (old_version or "").strip()
    n = (new_version or "").strip()
    risk = "low"
    notes: List[str] = []
    if not o or not n:
        return {"risk": "unknown", "score": 0, "notes": ["Need both versions to score."]}
    o_m = re.match(r"^(\d+)", o)
    n_m = re.match(r"^(\d+)", n)
    if o_m and n_m and o_m.group(1) != n_m.group(1):
        risk = "high"
        notes.append("Major Minecraft-style major version jump — expect breaking changes.")
    elif o != n and o.split(".")[:2] != n.split(".")[:2]:
        risk = "medium"
        notes.append("Minor/patch change — still verify against compat matrix.")
    else:
        notes.append("Small change — lower risk, still test launch + critical mods.")
    score = {"low": 1, "medium": 2, "high": 3}.get(risk, 0)
    return {"risk": risk, "score": score, "notes": notes}


def write_pack_lockfile(pack_root: str, manifest: Dict[str, Any]) -> str:
    mods = manifest.get("mods") if isinstance(manifest.get("mods"), list) else []
    entries: List[Dict[str, Any]] = []
    for m in mods:
        if not isinstance(m, dict):
            continue
        mid = str(m.get("id") or m.get("mod_id") or m.get("name") or "").strip()
        ver = str(m.get("version") or "").strip()
        if mid:
            entries.append({"id": mid.lower(), "version": ver})
    lock = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pack_root": os.path.basename(pack_root.rstrip("/\\")),
        "mods": sorted(entries, key=lambda x: x["id"]),
    }
    path = os.path.join(pack_root, "pack.lock.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(lock, fh, indent=2, ensure_ascii=True)
    return path


def run_startup_health(launcher) -> Dict[str, Any]:
    sysinfo = launcher.get_system_info()
    checks: List[Dict[str, str]] = []
    java_n = len(sysinfo.get("java_installations", []))
    if java_n == 0:
        checks.append({"id": "java", "status": "fail", "detail": "No Java installs detected."})
    else:
        checks.append({"id": "java", "status": "ok", "detail": f"{java_n} Java install(s)."})
    mem = int(sysinfo.get("config", {}).get("default_memory", 4096))
    if mem < 3072:
        checks.append({"id": "memory", "status": "warn", "detail": f"Default memory {mem} MB is tight for modded."})
    else:
        checks.append({"id": "memory", "status": "ok", "detail": f"Default memory {mem} MB."})
    inst = sysinfo.get("instances_count", 0)
    checks.append({"id": "instances", "status": "ok" if inst else "warn", "detail": f"{inst} instance(s)."})
    return {"checks": checks, "raw": sysinfo}


def _is_script_rel(rel: str) -> bool:
    parts = rel.replace("\\", "/").lower().split("/")
    return "kubejs" in parts or "scripts" in parts


def diff_recipe_trees(pack_a: str, pack_b: str) -> Dict[str, Any]:
    def collect(root: str) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if not os.path.isdir(root):
            return out
        for base, _, files in os.walk(root):
            for name in files:
                if not name.lower().endswith((".js", ".ts", ".zs", ".txt", ".json")):
                    continue
                full = os.path.join(base, name)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if not _is_script_rel(rel):
                    continue
                try:
                    with open(full, "r", encoding="utf-8", errors="replace") as fh:
                        out[rel] = fh.read()
                except OSError:
                    pass
        return out

    a_files = collect(pack_a)
    b_files = collect(pack_b)
    only_a = sorted(set(a_files) - set(b_files))
    only_b = sorted(set(b_files) - set(a_files))
    changed: List[str] = []
    for rel in sorted(set(a_files) & set(b_files)):
        if a_files[rel] != b_files[rel]:
            changed.append(rel)
    return {"only_a": only_a[:200], "only_b": only_b[:200], "changed": changed[:200], "stats": {"a": len(a_files), "b": len(b_files)}}


def sync_plan_summary(client_root: str, server_root: str) -> Dict[str, Any]:
    drift = compare_pack_roots(client_root, server_root)
    s = drift.get("summary", {})
    return {
        "in_sync": s.get("in_sync", False),
        "high_sections": s.get("high_sections", 0),
        "medium_sections": s.get("medium_sections", 0),
        "report": drift,
    }


def perf_baseline_path(launcher_dir: str, pack_key: str) -> str:
    d = os.path.join(launcher_dir, "perf_baselines")
    os.makedirs(d, exist_ok=True)
    safe = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in pack_key)[:80]
    return os.path.join(d, f"{safe}.json")


def save_perf_baseline(launcher_dir: str, pack_key: str, report: Dict[str, Any]) -> str:
    path = perf_baseline_path(launcher_dir, pack_key)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(
            {"saved_at": datetime.now(timezone.utc).isoformat(), "summary": report.get("summary"), "findings": report.get("findings")},
            fh,
            indent=2,
            ensure_ascii=True,
        )
    return path


def compare_perf_baseline(launcher_dir: str, pack_key: str, current: Dict[str, Any]) -> Dict[str, Any]:
    path = perf_baseline_path(launcher_dir, pack_key)
    if not os.path.exists(path):
        return {"ok": False, "message": "No baseline saved yet for this pack."}
    with open(path, "r", encoding="utf-8") as fh:
        base = json.load(fh)
    cur_mb = current.get("summary", {}).get("total_size_mb", 0)
    old_mb = base.get("summary", {}).get("total_size_mb", 0)
    delta = round(float(cur_mb) - float(old_mb), 2)
    cur_find = len(current.get("findings", []))
    old_find = len(base.get("findings", []))
    regress = []
    if delta > 120:
        regress.append(f"Pack footprint grew by ~{delta} MB vs baseline.")
    if cur_find > old_find:
        regress.append(f"More profiler findings than baseline ({cur_find} vs {old_find}).")
    return {
        "ok": True,
        "delta_size_mb": delta,
        "regressions": regress,
        "baseline_path": path,
    }


def suggest_checkpoint_prune(pack_root: str, keep: int = 10) -> Dict[str, Any]:
    from ..engine.apply import list_checkpoints

    cps = list_checkpoints(pack_root)
    if len(cps) <= keep:
        return {"remove": [], "kept": len(cps), "note": "Nothing to prune."}
    remove = cps[keep:]
    return {
        "remove": [c.get("checkpoint_id") for c in remove],
        "kept": keep,
        "note": "Delete old checkpoint folders under `.forager/checkpoints` if you need disk space (manual or future auto).",
    }


def explain_last_change_summary(pack_root: str) -> Dict[str, Any]:
    from ..trace.change_log import read_recent_traces

    rows = read_recent_traces(pack_root, limit=5)
    if not rows:
        return {"summary": "No traced applies yet for this pack.", "rows": []}
    last = rows[-1]
    summary = (
        f"Last apply `{last.get('feature_name')}` touched {len(last.get('files_written', []))} file(s)"
        f" and {len(last.get('compat_rules', []))} compat rule(s); checkpoint `{last.get('checkpoint_id')}`."
    )
    return {"summary": summary, "rows": rows}


def sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def fingerprint_mods_dir(pack_root: str, limit: int = 400) -> Dict[str, Any]:
    mods = os.path.join(pack_root, "mods")
    rows: List[Dict[str, Any]] = []
    if not os.path.isdir(mods):
        return {"mods": [], "note": "No mods folder."}
    for name in sorted(os.listdir(mods))[:limit]:
        if not name.lower().endswith(".jar"):
            continue
        p = os.path.join(mods, name)
        try:
            rows.append({"file": name, "sha256": sha256_file(p), "size": os.path.getsize(p)})
        except OSError:
            continue
    return {"mods": rows, "truncated": len(os.listdir(mods)) > limit}
