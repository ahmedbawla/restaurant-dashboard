"""
Desktop launcher for the Restaurant BI Dashboard.
- Finds a free port
- Starts Streamlit as a subprocess (headless, no browser auto-open)
- Polls until server is ready
- Opens the dashboard in the default browser
- Stays alive until the user closes the terminal / browser session
"""

import os
import socket
import subprocess
import sys
import time
import threading
import webbrowser
from pathlib import Path


def find_free_port(start: int = 8501) -> int:
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    raise RuntimeError("No free port found in range 8501–8600")


def wait_for_server(port: int, timeout: int = 60) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                return True
        except (ConnectionRefusedError, OSError):
            time.sleep(0.5)
    return False


def get_app_dir() -> Path:
    """
    Works both when running as script and when frozen by PyInstaller.
    PyInstaller sets sys._MEIPASS; scripts use __file__.
    """
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).parent


def run_sync_if_needed(app_dir: Path) -> None:
    """Run data/sync.py if the database doesn't exist yet."""
    db_path = app_dir / "data" / "restaurant.db"
    if not db_path.exists():
        print("[launcher] First run — populating database (this may take a few seconds)...")
        sync_script = app_dir / "data" / "sync.py"
        subprocess.run(
            [sys.executable, str(sync_script)],
            cwd=str(app_dir),
            check=True,
        )


def main() -> None:
    app_dir = get_app_dir()
    app_py = app_dir / "app.py"

    # Ensure DB is seeded on first run
    run_sync_if_needed(app_dir)

    port = find_free_port()
    url = f"http://localhost:{port}"

    print(f"[launcher] Starting Streamlit on port {port}...")

    env = os.environ.copy()
    env["PYTHONPATH"] = str(app_dir)

    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(app_py),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
            "--server.browserServerAddress",
            "localhost",
            "--browser.gatherUsageStats",
            "false",
        ],
        cwd=str(app_dir),
        env=env,
        # Suppress Streamlit console output for cleaner desktop experience
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    print(f"[launcher] Waiting for server at {url}...")
    if not wait_for_server(port, timeout=60):
        print("[launcher] ERROR: Streamlit server did not start in time.")
        proc.terminate()
        sys.exit(1)

    print(f"[launcher] Opening browser → {url}")
    webbrowser.open(url)

    try:
        proc.wait()
    except KeyboardInterrupt:
        print("\n[launcher] Shutting down...")
        proc.terminate()


if __name__ == "__main__":
    main()
