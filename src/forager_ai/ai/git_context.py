"""Optional git working-tree summary for pack folders (read-only)."""

from __future__ import annotations

import subprocess
from pathlib import Path
def pack_git_summary(repo_root: str, *, max_lines: int = 100) -> str:
    """
    Return a short status + diff --stat if ``repo_root`` is inside a git repo.
    Empty string if git is unavailable or not a repo.
    """
    root = Path(repo_root).resolve()
    if not root.is_dir():
        return ""
    cwd = root
    for base in [root] + list(root.parents)[:8]:
        if (base / ".git").exists():
            cwd = base
            break
    else:
        return ""

    try:
        st = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=20,
        )
        stat = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=25,
        )
    except (OSError, subprocess.SubprocessError):
        return ""

    if st.returncode != 0 and stat.returncode != 0:
        return ""

    lines: list[str] = [f"(git repo root: `{cwd}`)"]
    por = (st.stdout or "").strip()
    if por:
        lines.append("Status (porcelain):")
        lines.extend(por.splitlines()[:40])
    diffstat = (stat.stdout or "").strip()
    if diffstat:
        lines.append("Diff stat vs HEAD:")
        lines.extend(diffstat.splitlines()[: max_lines - len(lines)])
    out = "\n".join(lines).strip()
    return out[:8000]
