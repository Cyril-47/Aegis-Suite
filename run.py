import os
import sys

def is_headless_cloud() -> bool:
    """Returns True when running on a cloud host where webbrowser.open would fail or be useless."""
    return bool(os.getenv("RAILWAY_ENVIRONMENT")) or bool(os.getenv("RENDER"))

def is_frozen_exe() -> bool:
    """Returns True when running inside a PyInstaller --onefile bundle."""
    return getattr(sys, 'frozen', False)

def _get_app_root():
    """Return the directory where config/data files should live.
    
    For a frozen EXE, this is the directory containing the .exe itself
    (not the temp extraction folder). For source runs, it's the directory
    containing run.py.
    """
    if is_frozen_exe():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

from aegis.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
