import os
import sys
import subprocess
import shutil

def run_command(command, shell=True):
    print(f"Running: {' '.join(command) if isinstance(command, list) else command}")
    process = subprocess.Popen(command, shell=shell)
    process.communicate()
    return process.returncode

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

def prepare_environment():
    app_root = _get_app_root()
    
    # When running as a frozen EXE, all dependencies are bundled inside.
    # Skip venv creation and dependency installation entirely.
    if not is_frozen_exe():
        # 1. Check for virtual environment
        venv_dir = os.path.join(app_root, ".venv")
        python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
        
        if not os.path.exists(venv_dir) or not os.path.exists(python_exe):
            print("\n[+] Creating virtual environment using uv...")
            if shutil.which("uv"):
                ret = run_command(["uv", "venv", ".venv"])
            else:
                print("[!] uv not found in PATH, falling back to standard venv module...")
                ret = run_command([sys.executable, "-m", "venv", ".venv"])
                
            if ret != 0:
                print("[-] Failed to create virtual environment. Exiting.")
                sys.exit(1)
                
        # 2. Check and install dependencies
        print("\n[+] Verifying and installing dependencies...")
        dependencies = ["discord.py[voice]", "fastapi", "uvicorn", "websockets", "yt-dlp", "PyNaCl", "pydantic", "davey"]
        if shutil.which("uv"):
            ret = run_command(["uv", "pip", "install"] + dependencies)
        else:
            pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
            ret = run_command([pip_exe, "install"] + dependencies)
            
        if ret != 0:
            print("[-] Dependency installation failed. Exiting.")
            sys.exit(1)
    else:
        print("\n[+] Running as compiled EXE — all dependencies are bundled.")
        # Set the working directory to the EXE's folder so config.json,
        # .env.enc, and other data files are read/written next to the EXE.
        os.chdir(app_root)
        
    # Check if FFmpeg is available
    if not shutil.which("ffmpeg"):
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            winget_packages = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages")
            if os.path.exists(winget_packages):
                for root, dirs, files in os.walk(winget_packages):
                    if "ffmpeg.exe" in files:
                        os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                        print(f"\n[+] Dynamically added FFmpeg to PATH from: {root}")
                        break

    if not shutil.which("ffmpeg"):
        print("\n[!] WARNING: FFmpeg was not found in your system PATH.")
        print("[!] Discord Voice/Music playback requires FFmpeg to be installed and added to PATH.")
        print("[!] You can download it from: https://ffmpeg.org/download.html")
        print("----------------------------------------------")

if __name__ == "__main__":
    prepare_environment()
    from aegis.__main__ import main
    sys.exit(main())
