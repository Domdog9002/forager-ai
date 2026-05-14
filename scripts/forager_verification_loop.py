#!/usr/bin/env python3
"""
Run Forager verification (pytest + optional Playwright smoke) on a timer.

Designed for long unattended *monitoring* sessions: each cycle appends results to a
log file. It does not modify source code or your modpack.

Examples:
  py -3 scripts/forager_verification_loop.py --duration 4h --interval 5m
  py -3 scripts/forager_verification_loop.py --duration 30m --interval 2m --skip-playwright

Start Streamlit separately if you want Playwright smoke to exercise the live dashboard
(FORAGER_DASHBOARD_URL, default http://127.0.0.1:8501). If the app is down, smoke exits 0
with SKIP in output (same as the UI smoke button).

Interrupt with Ctrl+C; the log records the stop reason.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import re
import subprocess
import sys
import time
from pathlib import Path


def _parse_duration(s: str) -> float:
    s = (s or "").strip().lower()
    if not s:
        raise ValueError("empty duration")
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*([smh])?", s)
    if not m:
        return float(s)
    val, unit = float(m.group(1)), (m.group(2) or "s")
    mult = {"s": 1.0, "m": 60.0, "h": 3600.0}.get(unit, 1.0)
    return val * mult


def _utc_stamp() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def _run(cmd: list[str], *, cwd: Path, timeout: float | None) -> tuple[int, str]:
    try:
        p = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"(timeout after {timeout}s)\n{exc}"
    out = (p.stdout or "") + (p.stderr or "")
    return int(p.returncode), out


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description="Repeat Forager pytest + Playwright smoke for a bounded duration.")
    ap.add_argument("--duration", default="4h", help="Total wall time, e.g. 4h, 30m, 900 (seconds).")
    ap.add_argument("--interval", default="5m", help="Sleep between cycles, e.g. 5m, 120 (seconds).")
    ap.add_argument(
        "--log-file",
        default=str(root / "reports" / "forager_verify_loop.log"),
        help="Append-only log path (UTF-8).",
    )
    ap.add_argument("--skip-pytest", action="store_true", help="Only run Playwright smoke when not skipped.")
    ap.add_argument("--skip-playwright", action="store_true", help="Only run pytest.")
    ap.add_argument("--pytest-timeout", type=float, default=1200.0, help="Max seconds per pytest invocation.")
    ap.add_argument("--playwright-timeout", type=float, default=180.0, help="Max seconds per smoke script run.")
    args = ap.parse_args()

    total_s = _parse_duration(args.duration)
    interval_s = _parse_duration(args.interval)
    if total_s <= 0 or interval_s <= 0:
        print("duration and interval must be positive", file=sys.stderr)
        return 2

    log_path = Path(args.log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    def log(msg: str) -> None:
        line = f"[{_utc_stamp()}] {msg}\n"
        sys.stdout.write(line)
        sys.stdout.flush()
        with log_path.open("a", encoding="utf-8", newline="\n") as fh:
            fh.write(line)

    log(
        f"START cycle_monitor duration={total_s}s interval={interval_s}s "
        f"pytest={not args.skip_pytest} playwright={not args.skip_playwright} root={root}"
    )

    deadline = time.monotonic() + total_s
    cycle = 0
    rc = 0
    try:
        while time.monotonic() < deadline:
            cycle += 1
            log(f"--- cycle {cycle} ---")
            if not args.skip_pytest:
                code, out = _run(
                    [sys.executable, "-m", "pytest", "tests", "-q", "--tb=line"],
                    cwd=root,
                    timeout=args.pytest_timeout,
                )
                tail = out.strip()[-8000:] if out.strip() else "(no output)"
                log(f"pytest exit={code}\n{tail}")
                if code != 0:
                    rc = 1

            if not args.skip_playwright:
                script = root / "scripts" / "playwright_dashboard_smoke.js"
                if not script.is_file():
                    log("playwright SKIP script missing scripts/playwright_dashboard_smoke.js")
                else:
                    code, out = _run(
                        ["node", str(script)],
                        cwd=root,
                        timeout=args.playwright_timeout,
                    )
                    tail = out.strip()[-6000:] if out.strip() else "(no output)"
                    log(f"playwright_smoke exit={code}\n{tail}")
                    if code != 0:
                        rc = 1

            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            sleep_s = min(interval_s, remaining)
            log(f"sleep {sleep_s:.0f}s (remaining ~{remaining:.0f}s)")
            time.sleep(sleep_s)

        log("END completed full duration")
    except KeyboardInterrupt:
        log("END interrupted KeyboardInterrupt")
        rc = 130

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
