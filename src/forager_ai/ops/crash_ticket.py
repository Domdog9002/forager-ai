"""Markdown template for crash / support issue threads."""

from __future__ import annotations

from typing import Any, List, Optional


def build_crash_issue_markdown(
    *,
    summary: str,
    suspected_mods: Optional[List[Any]] = None,
    findings: Optional[List[Any]] = None,
    game_version: str = "1.20.1",
    loader: str = "forge",
    project_url: str = "",
    log_tail: str = "",
    lock_digest: str = "",
    mod_jar_count: Optional[int] = None,
    provenance_brief: str = "",
    jvm_hints_brief: str = "",
    asset_audit_brief: str = "",
    known_issue_hints: str = "",
) -> str:
    """GitHub/Discord-friendly body; may embed a short log tail when provided."""
    lines = [
        "## Environment",
        "",
        f"- Minecraft: **{game_version}**",
        f"- Loader: **{loader}**",
        "",
        "## Summary",
        "",
        (summary or "(no summary)").strip()[:4000],
        "",
    ]
    if project_url.strip():
        lines.extend(["## Related project", "", project_url.strip(), ""])
    if suspected_mods:
        lines.extend(["## Suspected mods", "", ", ".join(f"`{m}`" for m in suspected_mods[:40]), ""])
    if findings:
        lines.append("## Heuristic findings")
        lines.append("")
        for f in (findings or [])[:24]:
            lines.append(f"- {f}")
        lines.append("")
    lt = (log_tail or "").strip()
    if lt:
        safe = lt[:24_000]
        lines.extend(
            [
                "## latest.log tail (from selected pack folder, if found)",
                "",
                "```text",
                safe,
                "```",
                "",
            ]
        )
    ld = (lock_digest or "").strip()
    if ld:
        lines.extend(
            [
                "## Lockfile fingerprint",
                "",
                f"- `forager_mods.lock.json` SHA-256: `{ld}`",
                "",
            ]
        )
    if mod_jar_count is not None:
        lines.extend(
            [
                "## Mods folder",
                "",
                f"- Top-level `mods/*.jar` count: **{int(mod_jar_count)}**",
                "",
            ]
        )
    pb = (provenance_brief or "").strip()
    if pb:
        lines.extend(["## Recent catalog installs (provenance tail)", "", pb[:4000], ""])
    jv = (jvm_hints_brief or "").strip()
    if jv:
        lines.extend(["## JVM hints (Forager defaults, not auto-applied)", "", jv[:3000], ""])
    aa = (asset_audit_brief or "").strip()
    if aa:
        lines.extend(["## Mods asset scan (truncated)", "", aa[:3500], ""])
    ki = (known_issue_hints or "").strip()
    if ki:
        lines.extend(["## Known-issue database hits", "", ki[:3500], ""])
    lines.extend(
        [
            "## Attachments",
            "",
            "- Full `latest.log` / `debug.log` if the tail above is incomplete",
            "- Forager **support bundle** zip from Browse Modpacks → Exports",
            "- `forager_mods.lock.json` if you use lockfiles",
            "",
        ]
    )
    return "\n".join(lines)
