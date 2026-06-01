import os
import sys
import subprocess
import time
import shutil
import json
import urllib.request
from pathlib import Path
import pytest

@pytest.mark.skipif(sys.platform != "win32", reason="PyInstaller EXE and smoke tests are Windows-only")
def test_pyinstaller_build_and_boot(tmp_path):
    """Verify that build_exe.py builds AegisOptimizer.exe, and it boots cleanly in a new env."""
    print("[*] Running build_exe.py to compile executable...")
    # Execute build script in a clean process
    res = subprocess.run(
        [sys.executable, "build_exe.py"],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0, f"PyInstaller build failed: {res.stdout}\n{res.stderr}"
    
    exe_path = Path("dist/AegisOptimizer.exe")
    assert exe_path.exists(), "Executable AegisOptimizer.exe was not created in dist/ folder"
    
    # 2. Setup clean temporary APPDATA directory
    temp_appdata = tmp_path / "appdata"
    temp_appdata.mkdir()
    
    # Configure environmental variables for target run
    env = os.environ.copy()
    env["APPDATA"] = str(temp_appdata)
    env["PYTEST_CURRENT_TEST"] = "1"  # Skip live Discord API logins
    env["DISCORD_BOT_TOKEN"] = "valid.token.format"

    # Pre-create config.json to ensure database check and migrations run
    aegis_dir = temp_appdata / "Aegis"
    config_dir = aegis_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    config_data = {
        "setup_complete": True,
        "client_id": "1234567890",
        "hosting_mode": "cloud",
        "welcome_settings": {
            "enabled": False,
            "channel_id": None,
            "channel_name": "welcome",
            "message_title": "Welcome",
            "message_description": "Hello",
            "embed_color": "#6366F1",
            "auto_assign_roles": []
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": False,
            "block_links": False,
            "max_mentions": 5,
            "log_channel_id": None,
            "log_channel_name": "mod-logs",
            "profanity_words": []
        },
        "ticket_settings": {
            "enabled": False,
            "category_name": "SUPPORT",
            "staff_role_name": "Moderator",
            "ticket_channel_id": None,
            "panel_message_id": None
        }
    }
    with open(config_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config_data, f)
    
    print("[*] Booting built executable in background...")
    proc = subprocess.Popen(
        [str(exe_path)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    
    # Wait for resolved port and server launch
    time.sleep(6.0)
    
    try:
        # Verify process is active
        assert proc.poll() is None, "AegisOptimizer.exe exited prematurely after boot"
        
        # Determine the port from single-instance url file
        url_file = temp_appdata / "Aegis" / "aegis.url"
        assert url_file.exists(), "Aegis did not write URL file to local directory"
        url = url_file.read_text().strip()
        print(f"[+] Discovered running dashboard URL: {url}")
        
        # Query health check endpoint via standard urllib
        health_url = f"{url}/api/health"
        req = urllib.request.Request(health_url)
        with urllib.request.urlopen(req, timeout=5.0) as response:
            assert response.status == 200
            payload = json.loads(response.read().decode('utf-8'))
            assert payload["database"]["reachable"] is True
            assert payload["database"]["integrity_ok"] is True
        
        # Verify data folder separation was created
        db_file = temp_appdata / "Aegis" / "aegis.db"
        assert db_file.exists(), "Aegis database was not initialized at root"
        
    finally:
        # Stop background executable process
        print("[*] Terminating executable process...")
        proc.terminate()
        try:
            proc.wait(timeout=5.0)
        except subprocess.TimeoutExpired:
            proc.kill()
