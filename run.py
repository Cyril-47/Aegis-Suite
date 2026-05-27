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

def main():
    print("==============================================")
    print("   Discord Server Optimizer Bot & Dashboard")
    print("==============================================")
    
    # 1. Check for virtual environment
    venv_dir = os.path.join(os.path.dirname(__file__), ".venv")
    python_exe = os.path.join(venv_dir, "Scripts", "python.exe")
    
    if not os.path.exists(venv_dir) or not os.path.exists(python_exe):
        print("\n[+] Creating virtual environment using uv...")
        # Check if uv is in PATH
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
    dependencies = ["discord.py", "fastapi", "uvicorn", "websockets", "yt-dlp", "PyNaCl", "pydantic"]
    if shutil.which("uv"):
        ret = run_command(["uv", "pip", "install"] + dependencies)
    else:
        # Fallback to standard pip in the venv
        pip_exe = os.path.join(venv_dir, "Scripts", "pip.exe")
        ret = run_command([pip_exe, "install"] + dependencies)
        
    if ret != 0:
        print("[-] Dependency installation failed. Exiting.")
        sys.exit(1)
        
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
        
    # 3. Start the FastAPI web server
    print("\n[+] Launching FastAPI Web Server...")
    print("[+] Dashboard will be available at: http://localhost:8000")
    print("[+] Press Ctrl+C to stop the server.")
    print("----------------------------------------------")
    
    # Automatically open browser once server starts (skipped on headless cloud hosts)
    if not is_headless_cloud():
        import threading
        import webbrowser
        import time

        def open_browser():
            time.sleep(1.5)
            print("[+] Automatically opening the Dashboard in your browser...")
            try:
                webbrowser.open("http://127.0.0.1:8000")
            except Exception as exc:
                print(f"[!] webbrowser.open failed: {exc}. Continuing without opening a browser.")

        threading.Thread(target=open_browser, daemon=True).start()
    else:
        print("[+] Headless cloud environment detected (RAILWAY_ENVIRONMENT or RENDER set). "
              "Skipping webbrowser.open.")
    
    # Run uvicorn inside the virtual environment python
    uvicorn_cmd = [python_exe, "-m", "uvicorn", "web_server:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "info"]
    try:
        run_command(uvicorn_cmd, shell=False)
    except KeyboardInterrupt:
        print("\n[+] Web server stopped. Goodbye!")

if __name__ == "__main__":
    main()
