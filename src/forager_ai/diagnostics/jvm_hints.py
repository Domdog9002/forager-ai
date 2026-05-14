"""Conservative JVM argument hints (no auto-apply)."""

from __future__ import annotations

from typing import List, Sequence, Tuple


def jvm_heap_preset_mb(tier: str, *, balanced_max_mb: int = 4096) -> Tuple[int, int]:
    """Return ``(memory_min_mb, memory_max_mb)`` for Forager instance fields (-Xms / -Xmx style targets)."""
    t = (tier or "").strip().lower()
    bal = max(1024, int(balanced_max_mb or 4096))
    if t == "light":
        return (1536, 3072)
    if t == "heavy":
        return (4096, min(12288, max(8192, bal)))
    # balanced — keep min below max, leave headroom under max
    mx = bal
    mn = max(512, min(2048, mx // 2))
    if mn >= mx:
        mn = max(512, mx - 512)
    return (mn, mx)


def java_args_preset(preset: str) -> List[str]:
    """Return JVM flags appended on launch after ``-Xms/-Xmx`` (launcher ``java_args`` JSON list).

    Presets are conservative — users can still override in ``launcher_config.json`` manually.
    """
    p = (preset or "").strip().lower()
    base = ["-XX:+UseG1GC", "-XX:+UnlockExperimentalVMOptions"]
    if p in ("minimal", "default", ""):
        return list(base)
    if p == "balanced":
        return base + ["-XX:MaxGCPauseMillis=200"]
    if p == "extended":
        return base + [
            "-XX:MaxGCPauseMillis=200",
            "-XX:+AlwaysPreTouch",
        ]
    return list(base)


def format_java_args_for_ui(args: Sequence[str]) -> str:
    """Single-line preview for settings / Power Center."""
    return " ".join(str(a) for a in args)


def suggest_jvm_args_lines(*, default_memory_mb: int = 4096) -> List[str]:
    """Human-readable suggestions; user copies into launcher or pack tooling."""
    mem = max(512, int(default_memory_mb or 4096))
    lines = [
        f"- Current Forager default heap target: **~{mem} MB** — align `-Xmx` with how much RAM you give Minecraft.",
        "- **G1GC** (common on Java 17): `-XX:+UseG1GC` `-XX:+UnlockExperimentalVMOptions` `-XX:MaxGCPauseMillis=200`",
        "- If you see **GC lag spikes**, try lowering render/simulation distance before raising `-Xmx` again.",
        "- **OutOfMemoryError** in logs: raise `-Xmx` modestly (e.g. +512M steps) and check oversized mod packs / HD resource packs.",
        "- Always leave **1–2 GB** for the OS + browser + Discord when setting total client RAM.",
    ]
    return lines
