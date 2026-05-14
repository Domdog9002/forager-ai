from __future__ import annotations

from typing import Any, Dict, List, Optional


def build_unknown_health_score(*, reasons: List[str], inputs: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Explicit unknown state when metadata or gates are too weak for a numeric score."""
    findings = [{"severity": "low", "message": r} for r in (reasons or [])[:12] if str(r).strip()]
    if not findings:
        findings = [{"severity": "low", "message": "Insufficient reliable inputs for a numeric health score."}]
    return {
        "score": None,
        "verdict": "unknown",
        "findings": findings,
        "inputs": dict(inputs or {}),
    }


def build_pack_health_score(
    *,
    manifest: Dict[str, Any],
    conflict_summary: Dict[str, Any],
    performance_report: Dict[str, Any] | None = None,
    compat_rules_count: int = 0,
    role_summary: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Return a 0-100 pack health score with explainable deductions."""
    score = 100
    findings: List[Dict[str, Any]] = []
    severity_counts = conflict_summary.get("severity_counts") or {}

    deductions = {
        "critical": 25,
        "high": 12,
        "medium": 6,
        "low": 2,
    }
    for severity, penalty in deductions.items():
        count = int(severity_counts.get(severity, 0) or 0)
        if count:
            loss = min(45, count * penalty)
            score -= loss
            findings.append(
                {
                    "severity": severity,
                    "message": f"{count} {severity} conflict finding(s) reduce confidence by {loss}.",
                }
            )

    perf_findings = (performance_report or {}).get("findings") or []
    if perf_findings:
        loss = min(18, len(perf_findings) * 4)
        score -= loss
        findings.append({"severity": "medium", "message": f"{len(perf_findings)} performance finding(s)."})

    mods = manifest.get("mods") if isinstance(manifest.get("mods"), list) else []
    if not mods:
        score -= 8
        findings.append({"severity": "low", "message": "Manifest has no registered mods yet."})

    if compat_rules_count == 0 and int(conflict_summary.get("total_conflicts", 0) or 0) > 0:
        score -= 8
        findings.append({"severity": "medium", "message": "Conflicts exist but no compat rules are saved."})

    risk_counts = (role_summary or {}).get("risk_counts") or {}
    medium_risk = int(risk_counts.get("medium", 0) or 0)
    if medium_risk:
        loss = min(10, medium_risk * 2)
        score -= loss
        findings.append({"severity": "medium", "message": f"{medium_risk} mod(s) have medium risk role hints."})

    score = max(0, min(100, score))
    if score >= 85:
        verdict = "healthy"
    elif score >= 65:
        verdict = "watch"
    elif score >= 40:
        verdict = "risky"
    else:
        verdict = "critical"
    return {
        "score": score,
        "verdict": verdict,
        "findings": findings,
        "inputs": {
            "mods": len(mods),
            "conflicts": conflict_summary,
            "compat_rules_count": compat_rules_count,
            "role_summary": role_summary or {},
        },
    }


def format_health_narrative(
    health: Dict[str, Any],
    conflict_summary: Dict[str, Any],
    *,
    max_chars: int = 1200,
) -> str:
    """Plain-language, copy-friendly summary for launcher UI (not markdown-heavy)."""
    score = health.get("score")
    verdict = str(health.get("verdict") or "unknown")
    tc = int((conflict_summary or {}).get("total_conflicts") or 0)
    lines: List[str] = []
    if score is not None:
        lines.append(
            f"Pack health score is {score} out of 100 ({verdict}) from Forager's launcher-side audit."
        )
    if tc:
        lines.append(
            f"Conflict scan lists {tc} finding(s); treat these as hypotheses until validated against logs and gameplay."
        )
    for f in (health.get("findings") or [])[:6]:
        if isinstance(f, dict) and f.get("message"):
            sev = str(f.get("severity") or "").strip()
            msg = str(f["message"]).strip()
            lines.append(f"- [{sev}] {msg}" if sev else f"- {msg}")
    text = "\n".join(lines).strip()
    if not text:
        return ""
    return text[:max_chars]
