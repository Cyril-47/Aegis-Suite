import os
import sys
import subprocess
import shutil
import importlib


def run_command(command, shell=True):
    print(f"Running: {' '.join(command) if isinstance(command, list) else command}")
    process = subprocess.Popen(command, shell=shell)
    process.communicate()
    return process.returncode


def is_headless_cloud() -> bool:
    """Returns True when running on a cloud host where webbrowser.open would fail or be useless."""
    return bool(os.getenv("RENDER"))


def is_frozen_exe() -> bool:
    """Returns True when running inside a PyInstaller --onefile bundle."""
    return getattr(sys, 'frozen', False)


def _get_app_root():
    """Return the directory where config/data files should live."""
    if is_frozen_exe():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


# Map of pip package names to their Python import names
_PACKAGE_IMPORT_MAP = {
    "discord.py[voice]": "discord",
    "fastapi": "fastapi",
    "uvicorn[standard]": "uvicorn",
    "websockets": "websockets",
    "yt-dlp": "yt_dlp",
    "PyNaCl": "nacl",
    "pydantic": "pydantic",
    "sqlalchemy": "sqlalchemy",
    "alembic": "alembic",
    "jinja2": "jinja2",
    "httpx": "httpx",
    "Pillow": "PIL",
    "PyJWT": "jwt",
}


def _check_missing_packages():
    """Returns a list of pip package names whose import modules are not available."""
    missing = []
    for pip_name, import_name in _PACKAGE_IMPORT_MAP.items():
        try:
            importlib.import_module(import_name)
        except ImportError:
            missing.append(pip_name)
    return missing


def _print_dependency_status():
    """Prints a pass/fail status for each critical dependency."""
    print("\n[+] Dependency status:")
    all_ok = True
    for pip_name, import_name in _PACKAGE_IMPORT_MAP.items():
        try:
            mod = importlib.import_module(import_name)
            version = getattr(mod, "__version__", getattr(mod, "VERSION", "installed"))
            print(f"    [OK] {pip_name} ({version})")
        except ImportError:
            print(f"    [MISSING] {pip_name} — required for full functionality")
            all_ok = False
    return all_ok


def prepare_environment():
    app_root = _get_app_root()

    if not is_frozen_exe():
        # 1. Check for virtual environment
        venv_dir = os.path.join(app_root, ".venv")
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")

        if not os.path.exists(venv_dir) or not os.path.exists(python_exe):
            print("\n[+] Creating virtual environment...")
            if shutil.which("uv"):
                ret = run_command(["uv", "venv", ".venv"])
            else:
                print("[!] uv not found, falling back to standard venv...")
                ret = run_command([sys.executable, "-m", "venv", ".venv"])

            if ret != 0:
                print("[-] Failed to create virtual environment. Exiting.")
                sys.exit(1)

        # 2. Only install missing dependencies or force install if requested
        force_install = "--install-deps" in sys.argv
        missing = _check_missing_packages()
        if force_install or missing:
            packages_to_install = list(_PACKAGE_IMPORT_MAP.keys()) if force_install else missing
            print(f"\n[+] Installing {len(packages_to_install)} package(s)...")
            if shutil.which("uv"):
                ret = run_command(["uv", "pip", "install"] + packages_to_install)
            else:
                pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
                ret = run_command([pip_exe, "install"] + packages_to_install)

            if ret != 0:
                print("[-] Dependency installation failed. Exiting.")
                sys.exit(1)
        else:
            print("\n[+] All dependencies are already installed.")
    else:
        print("\n[+] Running as compiled EXE — all dependencies are bundled.")
        os.chdir(app_root)

    # 3. Print dependency status summary
    _print_dependency_status()

    # 4. Check if FFmpeg is available
    if not shutil.which("ffmpeg"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            winget_packages = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages")
            if os.path.exists(winget_packages):
                for root, dirs, files in os.walk(winget_packages):
                    if "ffmpeg.exe" in files:
                        os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                        print(f"\n[+] Found FFmpeg at: {root}")
                        break

    if not shutil.which("ffmpeg"):
        print("\n" + "=" * 60)
        print("[!] WARNING: FFmpeg not found in PATH.")
        print("[!] Music playback and voice features require FFmpeg.")
        print("[!] Download: https://ffmpeg.org/download.html")
        print("[!] Then add the folder containing ffmpeg.exe to your system PATH.")
        print("=" * 60)
    else:
        print("\n[+] FFmpeg found in PATH.")


if __name__ == "__main__":
    prepare_environment()
    from aegis.__main__ import main
    sys.exit(main())
