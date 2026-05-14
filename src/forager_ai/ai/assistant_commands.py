"""
Parse slash-style commands, navigation, and safe local actions before sending text to the LLM.

Returns None if the message should be handled only by the model.
"""

from __future__ import annotations

import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


@dataclass
class AssistantCommandResult:
    kind: str  # help | open_folder | navigate | noop
    message: str
    paths: Optional[List[str]] = None
    nav_route: Optional[str] = None


_NAV_ALIASES = {
    "forager": "forager_hub",
    "forager hub": "forager_hub",
    "heart": "forager_hub",
    "command": "forager_hub",
    "command center": "forager_hub",
    "instances": "instances",
    "packs": "instances",
    "my packs": "instances",
    "mods": "mods",
    "home": "home",
    "settings": "settings",
    "council": "ai_council",
    "crashes": "ai_crash",
    "crash": "ai_crash",
    "assistant": "forager_hub",
    "ai": "forager_hub",
    "atlas": "ai_atlas",
    "power": "power_center",
    "power center": "power_center",
    "architect": "ai_architect",
    "plans": "ai_plans",
    "approvals": "approvals_inbox",
    "inbox": "approvals_inbox",
    "content": "content",
    "hub": "hub",
    "forge studio": "forge_studio",
    "forgestudio": "forge_studio",
}


_HELP_TEXT = """
**Forager assistant quick commands** (start with `/` on the first line):

**Navigation**
- `/go forager` — unified pack-brain assistant (recommended)
- `/go settings` · `/go mods` (**Browse Modpacks** — modpack catalog) · `/go instances` · `/go council` · `/go crashes` · `/go assistant` (same as **Forager** hub) · `/go home` · `/go atlas`
- Also: `/go power` · `/go architect` · `/go plans` · `/go approvals` · `/go content` · `/go hub` · `/go forge_studio`

**Folders**
- `/open pack` — pack root  
- `/open config` · `/open mods` · `/open kubejs` · `/open scripts` · `/open resourcepacks`  
- `/open logs` — system temp (logs often nearby)  

Natural phrases like *go to settings* or *open mods* work without `/`.
""".strip()


def _resolve_nav(token: str) -> Optional[str]:
    k = (token or "").strip().lower().replace("_", " ")
    return _NAV_ALIASES.get(k)


def _norm(path: str) -> str:
    return os.path.normpath(os.path.expanduser(path or ""))


def parse_assistant_command(
    text: str,
    *,
    pack_root: str,
    pack_name: str = "",
) -> Optional[AssistantCommandResult]:
    raw = (text or "").strip()
    if not raw:
        return None

    if raw.lower().startswith("/help") or raw.lower() in ("/?", "?"):
        return AssistantCommandResult(kind="help", message=_HELP_TEXT)

    mgo = re.match(r"^/go\s+([\w\s-]+)\s*$", raw, re.I)
    if mgo:
        nav = _resolve_nav(mgo.group(1).strip())
        if nav:
            return AssistantCommandResult(
                kind="navigate",
                message=f"Opening **{nav.replace('_', ' ')}**…",
                nav_route=nav,
            )
        return AssistantCommandResult(
            kind="noop",
            message=f"Unknown page `{mgo.group(1).strip()}`. Try `/help` for `/go` targets.",
        )

    pr = Path(_norm(pack_root))

    m = re.match(r"^/open\s+(\S+)\s*$", raw.strip(), re.I)
    if m:
        target = m.group(1).strip().lower()
        if target == "logs":
            td = tempfile.gettempdir()
            return AssistantCommandResult(
                kind="open_folder",
                message="Opening the **system temp** folder.",
                paths=[td],
            )
        if target == "pack":
            cand = pr
        elif target in ("config", "mods", "kubejs", "defaultconfigs", "scripts", "resourcepacks"):
            cand = pr / target
        else:
            return AssistantCommandResult(
                kind="noop",
                message=f"Unknown `/open` target `{target}`. Try `/help`.",
            )
        if cand.is_dir():
            return AssistantCommandResult(
                kind="open_folder",
                message=f"Opening `{cand}`",
                paths=[str(cand.resolve())],
            )
        return AssistantCommandResult(kind="noop", message=f"Folder not found: `{cand}`")

    low = raw.lower()
    if re.search(r"\bgo\s+to\s+the\s+([\w\s-]+)\s*(page)?\b", low) or re.search(
        r"\bnavigate\s+to\s+([\w\s-]+)\b", low
    ):
        m2 = re.search(r"\bgo\s+to\s+(?:the\s+)?([\w\s-]+)", low) or re.search(
            r"\bnavigate\s+to\s+([\w\s-]+)", low
        )
        if m2:
            nav = _resolve_nav(m2.group(1).strip())
            if nav:
                return AssistantCommandResult(
                    kind="navigate",
                    message=f"Switching to **{nav}**…",
                    nav_route=nav,
                )

    if re.search(r"\bopen\s+(the\s+)?(mods\s*folder|mods)\b", low):
        cand = pr / "mods"
        if cand.is_dir():
            return AssistantCommandResult(kind="open_folder", message="Opening **mods**.", paths=[str(cand.resolve())])
    if re.search(r"\bopen\s+(the\s+)?config\b", low):
        cand = pr / "config"
        if cand.is_dir():
            return AssistantCommandResult(kind="open_folder", message="Opening **config**.", paths=[str(cand.resolve())])
    if re.search(r"\bopen\s+(the\s+)?(kube\s*js|kubejs)\b", low):
        cand = pr / "kubejs"
        if cand.is_dir():
            return AssistantCommandResult(kind="open_folder", message="Opening **kubejs**.", paths=[str(cand.resolve())])
    if "open" in low and "pack" in low and "folder" in low and pr.is_dir():
        return AssistantCommandResult(kind="open_folder", message="Opening pack root.", paths=[str(pr.resolve())])

    return None
