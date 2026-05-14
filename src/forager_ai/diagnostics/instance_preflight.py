"""
Pre-launch style report for a game root (instance or pack folder).

Uses an **ephemeral** manifest (MC + loader only, no disk writes): conflict scan from
``mods/*.jar``, ``profile_pack`` for sizes, ``build_pack_health_score`` for a 0–100
score (or explicit **unknown**), ``run_startup_health`` for JVM / RAM hints, plus
auxiliary signals (logs, lockfile, launcher sidecar, jar semver sampling, dismissals).
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from ..analysis.health_score import build_pack_health_score, build_unknown_health_score
from ..backend.conflict_scan import build_conflict_scan_report
from ..ops.advanced_toolkit import run_startup_health
from ..ops.mod_lock_verify import verify_forager_mods_lock
from ..pack.scan_dismissals import load_dismissed_conflict_ids
from .jar_version_audit import audit_jar_version_and_env
from .launch_log_signals import analyze_launch_log_tail
from .launcher_provenance import read_sidecar_launcher_versions
from .performance import profile_pack
from .preflight_telemetry import maybe_enqueue_preflight_snapshot


def _compat_rule_count(pack_root: str) -> int:
    d = os.path.join(str(pack_root), "compats")
    if not os.path.isdir(d):
        return 0
    try:
        return sum(1 for n in os.listdir(d) if str(n).endswith(".json"))
    except OSError:
        return 0


def _count_jar_mod_files(pack_root: str) -> int:
    d = os.path.join(str(pack_root or "").strip(), "mods")
    if not os.path.isdir(d):
        return 0
    try:
        return sum(1 for n in os.listdir(d) if str(n).lower().endswith(".jar"))
    except OSError:
        return 0


def try_read_disk_manifest_versions(pack_root: str) -> Tuple[Optional[str], Optional[str], bool]:
    """Return (minecraft_version, loader, present) from ``pack.manifest.json`` when readable."""
    path = os.path.join(str(pack_root or "").strip(), "pack.manifest.json")
    if not os.path.isfile(path):
        return None, None, False
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return None, None, True
        mc = str(data.get("minecraft_version") or "").strip() or None
        lo = str(data.get("loader") or "").strip().lower() or None
        if lo == "vanilla":
            lo = "forge"
        return mc, lo, True
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None, None, True


def _confidence_floor(current: str, target: str) -> str:
    """Return the weaker (less trusting) of two confidence labels."""
    order = {"high": 3, "medium": 2, "low": 1}
    return target if order.get(target, 2) < order.get(current, 3) else current


def _build_version_provenance(
    *,
    hub_mc: str,
    hub_lo: str,
    disk_mc: Optional[str],
    disk_lo: Optional[str],
    disk_present: bool,
    launcher_pv: Dict[str, Any],
) -> Dict[str, Any]:
    lm = str(launcher_pv.get("minecraft_version") or "").strip()
    ll = str(launcher_pv.get("loader") or "").strip()
    disagreements: List[str] = []
    pairs = [
        ("hub_row", hub_mc, hub_lo),
        ("disk_manifest", str(disk_mc or ""), str(disk_lo or "")),
        ("launcher_sidecar", lm, ll),
    ]
    mcs = {p[1].lower() for p in pairs if p[1]}
    if len([x for x in mcs if x]) > 1:
        disagreements.append("Minecraft version differs between hub row, disk manifest, and/or launcher sidecar.")
    loaders = {p[2].lower() for p in pairs if p[2]}
    if len([x for x in loaders if x]) > 1:
        disagreements.append("Loader differs between hub row, disk manifest, and/or launcher sidecar.")
    return {
        "hub_row": {"minecraft_version": hub_mc, "loader": hub_lo},
        "disk_manifest": {
            "minecraft_version": str(disk_mc or ""),
            "loader": str(disk_lo or ""),
            "present": disk_present,
        },
        "launcher_sidecar": dict(launcher_pv),
        "disagreements": disagreements,
    }


def enrich_scan_fidelity(
    base: Dict[str, Any],
    *,
    launch_log: Optional[Dict[str, Any]] = None,
    lock_verify: Optional[Dict[str, Any]] = None,
    version_provenance: Optional[Dict[str, Any]] = None,
    jar_audit: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Merge auxiliary diagnostics into scan_fidelity (reasons + confidence floor)."""
    out = dict(base)
    reasons = list(out.get("reasons") or [])
    conf = str(out.get("confidence") or "high")

    if launch_log:
        sev = str(launch_log.get("overall_severity") or "none")
        hits = launch_log.get("hits") if isinstance(launch_log.get("hits"), list) else []
        if hits:
            reasons.append(
                f"Log tail ({sev}): {len(hits)} pattern hit(s) — {launch_log.get('note', '')}".strip()
            )
            if sev in ("critical", "high"):
                conf = _confidence_floor(conf, "low" if sev == "critical" else "medium")
        lp = str(launch_log.get("log_path") or "")
        if lp:
            out["launch_log_path"] = lp

    if lock_verify:
        if lock_verify.get("skipped"):
            reasons.append(f"Lock verify skipped: {lock_verify.get('reason', '')}".strip())
        elif lock_verify.get("ok") is False:
            reasons.append(str(lock_verify.get("message") or "Lock verify failed."))
            conf = _confidence_floor(conf, "low")
        else:
            miss = lock_verify.get("missing_on_disk") or []
            extra = lock_verify.get("extra_on_disk") or []
            bad = lock_verify.get("hash_mismatch") or []
            if miss or extra or bad:
                reasons.append(
                    f"Lockfile drift: missing {len(miss)}, extra {len(extra)}, hash mismatch {len(bad)}."
                )
                conf = _confidence_floor(conf, "low")
            else:
                reasons.append(
                    f"Lockfile matches disk ({lock_verify.get('hash_ok_count', 0)} jar row(s) verified)."
                )

    if version_provenance:
        for line in version_provenance.get("disagreements") or []:
            if isinstance(line, str) and line.strip():
                reasons.append(line.strip())
                conf = _confidence_floor(conf, "medium")

    if jar_audit:
        ur = float(jar_audit.get("unknown_ratio") or 0)
        mm = int(jar_audit.get("mismatch_count") or 0)
        if mm > 0:
            reasons.append(f"Jar metadata: {mm} sampled jar(s) may not list effective Minecraft {out.get('effective_minecraft_version', '')}.")
            conf = _confidence_floor(conf, "medium")
        if ur > 0.35:
            reasons.append(f"Many sampled jars lack parsable MC declarations (unknown_ratio={ur:.2f}).")
            conf = _confidence_floor(conf, "medium")
        co = int(jar_audit.get("client_only") or 0)
        so = int(jar_audit.get("server_only") or 0)
        if co or so:
            reasons.append(
                f"Fabric environment hints: {co} client-only, {so} server-only (sampled jars; heuristic only)."
            )

    out["confidence"] = conf
    out["reasons"] = reasons[:22]
    return out


def compute_scan_fidelity(
    *,
    pack_root: str,
    scan: Dict[str, Any],
    hub_mc: str,
    hub_loader: str,
    effective_mc: str,
    effective_loader: str,
    disk_mc: Optional[str],
    disk_loader: Optional[str],
    disk_present: bool,
) -> Dict[str, Any]:
    """Signals for how much to trust this preflight pass (heuristic, not gameplay truth)."""
    root = str(pack_root or "").strip()
    jar_n = _count_jar_mod_files(root)
    mods_list = scan.get("mods") if isinstance(scan.get("mods"), list) else []
    mods_n = len(mods_list)
    reasons: List[str] = []

    hub_mc_n = str(hub_mc or "").strip()
    hub_ld_n = str(hub_loader or "").strip()
    eff_mc_n = str(effective_mc or "").strip()
    eff_ld_n = str(effective_loader or "").strip()

    mc_from_disk = bool(disk_mc and disk_mc.strip())
    ld_from_disk = bool(disk_loader and disk_loader.strip())
    hub_mc_diverges = bool(
        mc_from_disk and hub_mc_n and disk_mc and hub_mc_n.lower() != str(disk_mc).strip().lower()
    )
    hub_ld_diverges = bool(
        ld_from_disk and hub_ld_n and disk_loader and hub_ld_n.lower() != str(disk_loader).strip().lower()
    )
    if hub_mc_diverges:
        reasons.append(
            f"Scan uses Minecraft {eff_mc_n} from pack.manifest.json (hub row was {hub_mc_n})."
        )
    if hub_ld_diverges:
        reasons.append(
            f"Scan uses loader {eff_ld_n} from pack.manifest.json (hub row was {hub_ld_n})."
        )

    mods_dir = os.path.join(root, "mods")
    if not os.path.isdir(mods_dir):
        reasons.append("mods/ is missing — jar-based scan sees no on-disk mods.")
    elif jar_n == 0:
        reasons.append("mods/ has no .jar files — resolver is not evaluating a real mod set from disk.")
    elif jar_n > mods_n:
        reasons.append(
            f"{jar_n} jar files but only {mods_n} unique mod ids after dedupe — "
            "duplicate ids, shadowed jars, or metadata collapse may hide edges."
        )
    elif jar_n < mods_n:
        reasons.append(
            f"Indexed {mods_n} mods but only {jar_n} jars — manifest entries may be counted without matching jars."
        )

    if not disk_present and jar_n > 0:
        reasons.append(
            "No readable pack.manifest.json — Minecraft/loader for the resolver come from the hub row only; "
            "confirm they match this install."
        )
    elif disk_present and not mc_from_disk and jar_n > 0:
        reasons.append(
            "pack.manifest.json exists but omits minecraft_version — hub row MC is still used for jar defaults."
        )

    confidence = "high"
    if not os.path.isdir(mods_dir):
        confidence = "low"
    elif jar_n > mods_n or jar_n < mods_n:
        confidence = "low"
    elif jar_n == 0 and os.path.isdir(mods_dir):
        confidence = "low"
    elif not disk_present and jar_n > 0:
        confidence = "medium"
    elif hub_mc_diverges or hub_ld_diverges:
        if confidence == "high":
            confidence = "medium"

    return {
        "jar_mod_files": jar_n,
        "mods_indexed": mods_n,
        "jar_mod_parity": jar_n == mods_n,
        "effective_minecraft_version": eff_mc_n,
        "effective_loader": eff_ld_n,
        "hub_row_minecraft_version": hub_mc_n,
        "hub_row_loader": hub_ld_n,
        "disk_manifest_present": disk_present,
        "disk_manifest_minecraft_version": str(disk_mc or "").strip(),
        "disk_manifest_loader": str(disk_loader or "").strip(),
        "minecraft_source": "pack.manifest.json" if mc_from_disk else "hub_row",
        "loader_source": "pack.manifest.json" if ld_from_disk else "hub_row",
        "hub_row_overridden": bool(hub_mc_diverges or hub_ld_diverges),
        "confidence": confidence,
        "confidence_note": "Heuristic scan — confirm against Pack Health, launch logs, and gameplay.",
        "reasons": reasons[:14],
    }


def build_launch_target_preflight_report(
    *,
    game_root: str,
    label: str,
    minecraft_version: str,
    loader: str,
    launcher: Any,
    conflict_resolver: Any,
    telemetry_enabled: bool = False,
    telemetry_include_paths: bool = False,
) -> Dict[str, Any]:
    """
    Build a dashboard-ready dict. Does **not** create ``pack.manifest.json`` or other files.
    """
    root = str(game_root or "").strip()
    hub_mc = (minecraft_version or "1.20.1").strip() or "1.20.1"
    hub_lo = (loader or "forge").strip().lower() or "forge"
    if hub_lo == "vanilla":
        hub_lo = "forge"

    disk_mc, disk_lo, disk_present = try_read_disk_manifest_versions(root)
    launcher_pv = read_sidecar_launcher_versions(root)
    launch_mc = str(launcher_pv.get("minecraft_version") or "").strip()
    launch_lo = str(launcher_pv.get("loader") or "").strip().lower()
    if launch_lo == "vanilla":
        launch_lo = "forge"

    mc = str(disk_mc or launch_mc or hub_mc).strip() or "1.20.1"
    lo = str(disk_lo or launch_lo or hub_lo).strip().lower() or "forge"
    if lo == "vanilla":
        lo = "forge"

    if launch_mc and disk_mc and launch_mc.lower() != str(disk_mc).lower():
        launcher_pv = {**launcher_pv, "note": "Launcher sidecar MC differs from disk manifest — disk wins for scan."}
    if launch_lo and disk_lo and launch_lo != str(disk_lo).lower():
        launcher_pv = {**launcher_pv, "loader_note": "Launcher sidecar loader differs from disk manifest — disk wins for scan."}

    version_provenance = _build_version_provenance(
        hub_mc=hub_mc,
        hub_lo=hub_lo,
        disk_mc=disk_mc,
        disk_lo=disk_lo,
        disk_present=disk_present,
        launcher_pv=launcher_pv,
    )

    manifest: Dict[str, Any] = {"minecraft_version": mc, "loader": lo, "mods": []}

    launch_log = analyze_launch_log_tail(root, max_chars=80_000)

    jar_n = _count_jar_mod_files(root)
    lock_path = os.path.join(root, "forager_mods.lock.json")
    lock_verify: Optional[Dict[str, Any]] = None
    if os.path.isfile(lock_path):
        if jar_n > 300:
            lock_verify = {
                "ok": False,
                "skipped": True,
                "reason": "Lock verify skipped — more than 300 mod jars (performance guard).",
            }
        else:
            lock_verify = verify_forager_mods_lock(root)

    jar_audit = audit_jar_version_and_env(root, mc, max_jars=48)

    dismissed = load_dismissed_conflict_ids(root)
    scan = build_conflict_scan_report(
        resolver=conflict_resolver,
        manifest=manifest,
        pack_root=root,
        pack_name=(label or os.path.basename(root) or "target"),
        auto_resolve=True,
        skip_conflict_ids=dismissed,
    )

    scan_fidelity = compute_scan_fidelity(
        pack_root=root,
        scan=scan,
        hub_mc=hub_mc,
        hub_loader=hub_lo,
        effective_mc=mc,
        effective_loader=lo,
        disk_mc=disk_mc,
        disk_loader=disk_lo,
        disk_present=disk_present,
    )
    scan_fidelity = enrich_scan_fidelity(
        scan_fidelity,
        launch_log=launch_log,
        lock_verify=lock_verify,
        version_provenance=version_provenance,
        jar_audit=jar_audit,
    )

    perf = profile_pack(root) if root and os.path.isdir(root) else {"findings": [], "section_stats": {}}

    jar_n_sf = int(scan_fidelity.get("jar_mod_files") or 0)
    unknown_health = float(jar_audit.get("unknown_ratio") or 0) > 0.55 or (
        str(scan_fidelity.get("confidence")) == "low" and jar_n_sf == 0
    )
    if unknown_health:
        health = build_unknown_health_score(
            reasons=list(scan_fidelity.get("reasons") or [])[:8]
            + ["Health score withheld until jar metadata and scan confidence improve."],
            inputs={
                "mods": 0,
                "conflicts": scan.get("summary") or {},
                "compat_rules_count": _compat_rule_count(root),
                "role_summary": {},
                "jar_audit": jar_audit,
            },
        )
    else:
        health = build_pack_health_score(
            manifest=manifest,
            conflict_summary=scan.get("summary") or {},
            performance_report=perf if isinstance(perf, dict) else {},
            compat_rules_count=_compat_rule_count(root),
            role_summary=None,
        )

    startup = run_startup_health(launcher)
    report: Dict[str, Any] = {
        "game_root": root,
        "label": label,
        "manifest_echo": manifest,
        "conflict_scan": scan,
        "performance": perf,
        "health_score": health,
        "startup": startup,
        "scan_fidelity": scan_fidelity,
        "launch_log_signals": launch_log,
        "lock_verify": lock_verify or {},
        "version_provenance": version_provenance,
        "jar_version_audit": jar_audit,
        "dismissed_conflict_ids": sorted(dismissed),
    }
    maybe_enqueue_preflight_snapshot(
        pack_root=root,
        enabled=bool(telemetry_enabled),
        report=report,
        include_paths=bool(telemetry_include_paths),
    )
    return report


def format_preflight_narrative(report: Dict[str, Any], *, max_chars: int = 1600) -> str:
    """Plain-text summary of ``build_launch_target_preflight_report`` for AI / tickets."""
    if not report:
        return ""
    label = str(report.get("label") or "").strip()
    root = str(report.get("game_root") or "").strip()
    hs = report.get("health_score") or {}
    score = hs.get("score")
    verdict = str(hs.get("verdict") or "")
    cs = (report.get("conflict_scan") or {}).get("summary") or {}
    tc = int(cs.get("total_conflicts") or 0)
    lines = ["[Install-target preflight (ephemeral manifest)]"]
    if label:
        lines.append(f"Label: {label}")
    if root:
        lines.append(f"Path: {root}")
    if score is not None:
        lines.append(f"Ephemeral health score: {score}/100 ({verdict or 'unknown'})")
    else:
        lines.append(f"Health score: withheld ({verdict or 'unknown'})")
    lines.append(f"Ephemeral conflict findings: {tc}")
    sf = report.get("scan_fidelity") if isinstance(report.get("scan_fidelity"), dict) else {}
    if sf:
        lines.append(
            f"Scan confidence: {sf.get('confidence', '?')} "
            f"(MC {sf.get('effective_minecraft_version', '?')} from {sf.get('minecraft_source', '?')}; "
            f"loader {sf.get('effective_loader', '?')} from {sf.get('loader_source', '?')})"
        )
        for r in (sf.get("reasons") or [])[:6]:
            if isinstance(r, str) and r.strip():
                lines.append(f"- {r.strip()}")
    ll = report.get("launch_log_signals") if isinstance(report.get("launch_log_signals"), dict) else {}
    if ll.get("hits"):
        lines.append(f"Log tail severity: {ll.get('overall_severity', '?')} ({len(ll.get('hits') or [])} hit(s))")
    st = report.get("startup") or {}
    for chk in (st.get("checks") or [])[:8]:
        if isinstance(chk, dict):
            lines.append(f"- [{chk.get('status')}] {chk.get('id')}: {chk.get('detail')}")
    text = "\n".join(lines).strip()
    return text[:max_chars] if text else ""
