import os
import signal
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime
from http.client import RemoteDisconnected
import urllib.error
import urllib.request
import tempfile
import json

from streamlit.config import set_option

# PyInstaller extracts Streamlit outside site-packages, so Streamlit wrongly
# assumes "development mode" (Vite on :3000). That breaks frozen apps: the UI
# must use the same port as server.port.
set_option("global.developmentMode", False)
set_option("server.headless", True)
set_option("browser.gatherUsageStats", False)
try:
    set_option("server.enableStaticServing", True)
except Exception:
    pass

import streamlit.web.bootstrap as bootstrap


APP_PORT = 8501
APP_URL = ""
HEALTH_URL = ""
READY_APP_URL = ""
VALID_LAUNCH_MODES = {"embedded_only", "browser_only", "both"}

STREAMLIT_START_ERROR: str | None = None
LOG_PATH = os.path.join(tempfile.gettempdir(), "forager_launcher.log")


def _log(message: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(LOG_PATH, "a", encoding="utf-8") as fh:
            fh.write(f"[{ts}] {message}\n")
    except Exception:
        pass


def _launch_mode_from_config() -> str | None:
    cfg_path = os.path.join(os.path.expanduser("~"), ".forager_ai", "launcher_config.json")
    try:
        with open(cfg_path, "r", encoding="utf-8") as fh:
            cfg = json.load(fh)
        value = str(cfg.get("launch_mode", "")).strip().lower()
        return value or None
    except Exception:
        return None


def _resolve_launch_mode() -> str:
    env_mode = os.getenv("FORAGER_LAUNCH_MODE", "").strip().lower()
    chosen = env_mode or (_launch_mode_from_config() or "embedded_only")
    if chosen not in VALID_LAUNCH_MODES:
        _log(f"Invalid launch mode {chosen!r}; using embedded_only.")
        return "embedded_only"
    return chosen


def _safe_signal(_signum, _handler):
    # Packaged/threaded Streamlit bootstrap can attempt signal registration
    # from non-main threads. Silently no-op to avoid runtime failure.
    return None


def _reserve_port(preferred_port: int = 8501) -> int:
    # Prefer 8501, but fall back to a free ephemeral port.
    for candidate in (preferred_port, 0):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", candidate))
            _, port = sock.getsockname()
            return int(port)
    return preferred_port


def start_streamlit() -> None:
    global STREAMLIT_START_ERROR
    bundle_dir = getattr(sys, "_MEIPASS", os.path.abspath(os.path.dirname(__file__)))
    if getattr(sys, "frozen", False):
        try:
            os.chdir(bundle_dir)
        except OSError:
            pass
    dashboard_path = os.path.abspath(os.path.join(bundle_dir, "dashboard.py"))
    _log(f"Bundle dir: {bundle_dir}")
    _log(f"Dashboard path: {dashboard_path}")
    if not os.path.exists(dashboard_path):
        raise FileNotFoundError(f"dashboard.py not found at {dashboard_path}")
    try:
        _log("Starting Streamlit bootstrap.run()")
        bootstrap.run(dashboard_path, "", [], flag_options={})
    except Exception as exc:
        STREAMLIT_START_ERROR = str(exc)
        _log(f"Streamlit startup exception: {exc}")


def wait_for_streamlit(timeout_s: int = 180) -> bool:
    global READY_APP_URL
    deadline = time.time() + timeout_s
    _log(f"Waiting for Streamlit health: {HEALTH_URL}")
    while time.time() < deadline:
        if STREAMLIT_START_ERROR:
            _log("Startup error detected while waiting for health.")
            return False
        health_ok = False
        try:
            with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
                health_ok = response.status == 200
        except (
            urllib.error.URLError,
            urllib.error.HTTPError,
            TimeoutError,
            RemoteDisconnected,
            ConnectionResetError,
        ):
            health_ok = False

        # Prefer configured app URL (dev mode off => matches server.port).
        for url in (
            APP_URL,
            f"http://127.0.0.1:{APP_PORT}",
            "http://127.0.0.1:3000",
            "http://localhost:3000",
        ):
            try:
                with urllib.request.urlopen(url, timeout=2) as app_resp:
                    if app_resp.status == 200:
                        READY_APP_URL = url
                        _log(f"App route returned 200 at {url} (health_ok={health_ok}).")
                        return True
            except (
                urllib.error.URLError,
                urllib.error.HTTPError,
                TimeoutError,
                RemoteDisconnected,
                ConnectionResetError,
            ):
                continue
        time.sleep(0.5)
    _log("Timed out waiting for healthy app endpoint.")
    return False


def _alert_windows(title: str, message: str) -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, title, 0x40)
    except Exception:
        pass


def _open_ui(url: str) -> None:
    _log(f"Opening default browser: {url}")
    webbrowser.open(url, new=1, autoraise=True)


def _try_embedded_window(url: str) -> bool:
    try:
        import webview

        webview.create_window("Forager AI: Developer Suite", url)
        _log("Starting pywebview (embedded window).")
        webview.start()
        return True
    except Exception as exc:
        _log(f"pywebview failed: {exc}")
        return False


def main() -> None:
    global APP_PORT, APP_URL, HEALTH_URL, READY_APP_URL
    _log("Launcher starting.")
    APP_PORT = _reserve_port(8501)
    APP_URL = f"http://127.0.0.1:{APP_PORT}"
    HEALTH_URL = f"{APP_URL}/_stcore/health"
    READY_APP_URL = APP_URL
    _log(f"Assigned port: {APP_PORT}")
    set_option("server.port", APP_PORT)

    launch_mode = _resolve_launch_mode()
    _log(f"Launch mode: {launch_mode}")
    if launch_mode in {"embedded_only", "both"}:
        os.environ["FORAGER_EMBEDDED_WEBVIEW"] = "1"

    signal.signal = _safe_signal
    streamlit_thread = threading.Thread(target=start_streamlit, daemon=True)
    streamlit_thread.start()
    healthy = wait_for_streamlit()
    if not healthy:
        if STREAMLIT_START_ERROR:
            _log(f"Proceeding despite startup error: {STREAMLIT_START_ERROR}")
        else:
            _log("Proceeding despite health timeout.")

    open_url = READY_APP_URL if healthy else APP_URL
    _log(f"UI URL: {open_url}")

    if launch_mode in {"browser_only", "both"}:
        _open_ui(open_url)
        if not healthy:
            time.sleep(0.5)
            for extra in (f"http://127.0.0.1:{APP_PORT}", "http://127.0.0.1:3000"):
                if extra != open_url:
                    _open_ui(extra)

    if launch_mode in {"embedded_only", "both"}:
        embedded_ok = _try_embedded_window(open_url)
        # Keep embedded_only resilient by opening browser if webview fails.
        if not embedded_ok and launch_mode == "embedded_only":
            _open_ui(open_url)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        _log(f"Fatal: {exc}")
        msg = (
            f"{exc}\n\nLog: {LOG_PATH}\n\n"
            "The dashboard will also try: http://127.0.0.1:3000 and :8501 in your browser."
        )
        _alert_windows("Forager AI launcher", msg)
        try:
            webbrowser.open("http://127.0.0.1:3000", new=1)
            webbrowser.open("http://127.0.0.1:8501", new=1)
        except Exception:
            pass