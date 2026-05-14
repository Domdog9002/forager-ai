"""Human-readable repair hints from lock verify output."""

from __future__ import annotations

from typing import Any, Dict, List


def repair_hints_from_verify(report: Dict[str, Any]) -> List[str]:
    """Bullet lines for missing / extra / hash mismatch rows."""
    lines: List[str] = []
    if not isinstance(report, dict):
        return lines
    if not report.get("ok"):
        msg = str(report.get("message") or "Lock verify did not complete.")
        return [msg]
    for rel in report.get("missing_on_disk") or []:
        if rel:
            lines.append(f"Restore or re-download `{rel}` (missing vs lock).")
    for rel in report.get("extra_on_disk") or []:
        if rel:
            lines.append(f"Extra on disk vs lock: `{rel}` — remove, move aside, or refresh the lock.")
    for row in report.get("hash_mismatch") or []:
        if isinstance(row, dict) and row.get("rel"):
            lines.append(
                f"Hash mismatch for `{row.get('rel')}` — lock `{row.get('sha256_lock')}` vs disk `{row.get('sha256_disk')}`; re-fetch jar."
            )
    if not lines:
        lines.append("Lock matches disk for tracked jars.")
    return lines
