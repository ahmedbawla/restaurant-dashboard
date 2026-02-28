"""
Build script — creates a single-file .exe using PyInstaller.
Usage: python build.py

Output: dist/Restaurant Dashboard.exe
"""

import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).parent
DIST_DIR = PROJECT_DIR / "dist"


def main():
    print("[build] Running PyInstaller...")

    # Collect all data files that need to be bundled into the executable
    data_args = [
        # Include the pages folder
        f"--add-data={PROJECT_DIR / 'pages'}{';' if sys.platform == 'win32' else ':'}pages",
        # Include components
        f"--add-data={PROJECT_DIR / 'components'}{';' if sys.platform == 'win32' else ':'}components",
        # Include data module
        f"--add-data={PROJECT_DIR / 'data'}{';' if sys.platform == 'win32' else ':'}data",
        # Include config
        f"--add-data={PROJECT_DIR / 'config.json'}{';' if sys.platform == 'win32' else ':'}.",
        # Include app.py (Streamlit entry point)
        f"--add-data={PROJECT_DIR / 'app.py'}{';' if sys.platform == 'win32' else ':'}.",
    ]

    # Hidden imports Streamlit needs that PyInstaller misses
    hidden_imports = [
        "--hidden-import=streamlit",
        "--hidden-import=streamlit.web.cli",
        "--hidden-import=streamlit.runtime.scriptrunner.magic_funcs",
        "--hidden-import=plotly",
        "--hidden-import=pandas",
        "--hidden-import=numpy",
        "--hidden-import=sqlite3",
        "--hidden-import=altair",
        "--hidden-import=pyarrow",
        "--collect-all=streamlit",
        "--collect-all=plotly",
    ]

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        str(PROJECT_DIR / "launcher.py"),
        "--onefile",
        "--noconsole",
        f"--name=Restaurant Dashboard",
        f"--distpath={DIST_DIR}",
        f"--workpath={PROJECT_DIR / 'build_tmp'}",
        f"--specpath={PROJECT_DIR}",
        *data_args,
        *hidden_imports,
        "--noconfirm",
    ]

    print("[build] Command:")
    print("  " + " ".join(str(c) for c in cmd))
    print()

    result = subprocess.run(cmd, cwd=str(PROJECT_DIR))

    if result.returncode == 0:
        exe = DIST_DIR / "Restaurant Dashboard.exe"
        print(f"\n[build] SUCCESS — executable at:\n  {exe}")
    else:
        print(f"\n[build] FAILED with exit code {result.returncode}")
        sys.exit(result.returncode)


if __name__ == "__main__":
    main()
