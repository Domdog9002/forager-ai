"""
Human-in-the-loop checklist for real compat work (not automatic fixes).
"""

from __future__ import annotations

COMPAT_WORKFLOW_GUIDE = """
### Compat mod workflow (Forge 1.20.1)

1. **Reproduce minimally** — test instance with only the two mods + dependencies + your bridge.
2. **Find the seam** — tags, events, recipes, damage attributes, or a single API call; avoid Mixins until necessary.
3. **Read upstream** — GitHub source or Javadoc for **public** APIs; do not rely on obfuscated private fields.
4. **Use Forager (B)** — merge datapack/KubeJS starters, then replace empty tag JSON with **real item ids** (`/kubejs hand`, creative tabs, or `/data get`).
5. **Use Forager (A)** — extract the Forge scaffold zip **outside** the pack; open in **IntelliJ**; set `gradle.properties`; run `gradlew runClient`.
6. **Verify in-game** — one behavior at a time; capture logs if something still crashes.
7. **Ship last** — only after `runClient` and a copy of the full pack both look good.

Forager does **not** infer cross-mod behavior automatically; it accelerates **scaffolding + review**.
""".strip()
