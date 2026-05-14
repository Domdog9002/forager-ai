"""Zip support bundle: mod lock + install provenance tail + README."""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any, Optional

from ..ai.assistant_voice import load_interaction_memory_tail
from ..diagnostics.asset_audit import build_mods_asset_audit
from ..diagnostics.env_fingerprint import collect_env_fingerprint
from ..diagnostics.jvm_hints import suggest_jvm_args_lines
from ..diagnostics.log_tail import tail_latest_log


def build_support_bundle_zip_bytes(
    game_root: str,
    cache_dir: str,
    *,
    provenance_tail_bytes: int = 200_000,
    launcher: Optional[Any] = None,
    conflict_resolver: Optional[Any] = None,
) -> bytes:
    """Return a zip in memory for Discord/support threads."""
    root = Path(str(game_root or "").strip())
    cache = Path(str(cache_dir or "").strip())
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        lock = root / "forager_mods.lock.json"
        if lock.is_file():
            zf.write(lock, arcname="forager_mods.lock.json")
        prov = cache / "install_provenance.jsonl"
        if prov.is_file():
            try:
                raw = prov.read_bytes()
                if len(raw) > provenance_tail_bytes:
                    raw = raw[-provenance_tail_bytes:]
                zf.writestr("install_provenance_tail.jsonl", raw)
            except OSError:
                pass
        lt = tail_latest_log(str(root), max_chars=80_000)
        if lt.strip():
            zf.writestr("latest_log_tail.txt", lt.encode("utf-8", errors="replace"))
        try:
            env_blob = json.dumps(collect_env_fingerprint(timeout_s=6.0), indent=2, ensure_ascii=True)
            zf.writestr("env_fingerprint.json", env_blob.encode("utf-8", errors="replace"))
        except Exception:
            pass
        try:
            aud = build_mods_asset_audit(str(root), max_files=400)
            zf.writestr(
                "mods_asset_audit.json",
                json.dumps(aud, indent=2, ensure_ascii=True).encode("utf-8", errors="replace"),
            )
        except Exception:
            pass
        try:
            mem = 4096
            if launcher is not None:
                mem = int(launcher.config.get("default_memory") or 4096)
            jvm = "\n".join(suggest_jvm_args_lines(default_memory_mb=mem))
            zf.writestr("jvm_hints.txt", jvm.encode("utf-8", errors="replace"))
        except Exception:
            pass
        try:
            im = load_interaction_memory_tail(max_chars=12_000).strip()
            if im:
                zf.writestr("interaction_memory_tail.txt", im.encode("utf-8", errors="replace"))
        except Exception:
            pass
        if launcher is not None and conflict_resolver is not None and root.is_dir():
            try:
                from ..diagnostics.instance_preflight import build_launch_target_preflight_report

                rep = build_launch_target_preflight_report(
                    game_root=str(root),
                    label=root.name or "bundle",
                    minecraft_version="1.20.1",
                    loader="forge",
                    launcher=launcher,
                    conflict_resolver=conflict_resolver,
                    telemetry_enabled=bool(launcher.config.get("preflight_telemetry_enabled", False)),
                    telemetry_include_paths=bool(launcher.config.get("preflight_telemetry_include_paths", False)),
                )
                slim = {
                    "game_root": rep.get("game_root"),
                    "label": rep.get("label"),
                    "health_score": rep.get("health_score"),
                    "conflict_summary": (rep.get("conflict_scan") or {}).get("summary"),
                    "startup": rep.get("startup"),
                }
                zf.writestr(
                    "preflight_snapshot.json",
                    json.dumps(slim, indent=2, ensure_ascii=True).encode("utf-8", errors="replace"),
                )
            except Exception:
                pass
        readme = (
            "Forager AI support bundle\n"
            f"- game_root: {root}\n"
            "- forager_mods.lock.json — if present\n"
            "- install_provenance_tail.jsonl — last bytes of catalog install log\n"
            "- latest_log_tail.txt — tail of latest.log/debug.log when found under game_root\n"
            "- env_fingerprint.json — OS / Python / Java / git / Streamlit snapshot\n"
            "- mods_asset_audit.json — capped walk of mods/**/*.jar (+ .jar.disabled)\n"
            "- jvm_hints.txt — conservative JVM notes from Forager defaults\n"
            "- interaction_memory_tail.txt — recent Forager session notes (if any)\n"
            "- preflight_snapshot.json — ephemeral install-target scan (when launcher + resolver passed)\n"
        )
        zf.writestr("README.txt", readme.encode("utf-8"))
    return buf.getvalue()
