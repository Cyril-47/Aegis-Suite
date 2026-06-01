import os
import json
import zipfile
import pytest
from unittest.mock import MagicMock
from pathlib import Path

from aegis.core.paths import Paths
from aegis.diagnostics.packager import generate_package

class MockConfig:
    def as_dict(self):
        return {
            "client_id": "1234567890",
            "setup_complete": True,
            "discord_bot_token": "MTIzNDU2Nzg5MDEyMzQ1Njc4OTA.ABCDEF.GHIJKLMNOPQRSTUVWXYZ",
            "jwt_secret": "my-secret-key-12345",
            "admin_password_hash": "pbkdf2:sha256:260000$abcd$efgh",
            "some_safe_key": "safe-value"
        }

class MockState:
    def __init__(self):
        from aegis.core.state import LifecycleState
        self.current_state = LifecycleState.RUNNING
        self.reason = None

def test_generate_package(paths_tmp):
    # Setup mock core object
    mock_core = MagicMock()
    mock_core.paths = paths_tmp
    mock_core.config = MockConfig()
    mock_core.state = MockState()
    mock_core.db = None
    mock_core._start_time = 123456789.0
    
    # Create fake log files to pack
    with open(paths_tmp.log_file, "w", encoding="utf-8") as f:
        f.write("Line 1: Log info\nLine 2: Log warning\nDISCORD_BOT_TOKEN=MTIzNDU2Nzg5MDEyMzQ1Njc4OTA.ABCDEF.GHIJKLMNOPQRSTUVWXYZ\n")
        
    with open(paths_tmp.err_log_file, "w", encoding="utf-8") as f:
        f.write("Line 1: Fatal error\n")
        
    # Generate diagnostics package
    zip_path = generate_package(mock_core)
    
    assert zip_path.exists()
    assert zip_path.parent == paths_tmp.diagnostics
    assert zip_path.name.startswith("aegis_diag_")
    assert zip_path.name.endswith(".zip")
    
    # Check zip contents
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        namelist = zipf.namelist()
        assert "info.json" in namelist
        assert "aegis.log" in namelist
        assert "aegis.err.log" in namelist
        
        # Verify info.json redaction
        info_content = zipf.read("info.json").decode("utf-8")
        info = json.loads(info_content)
        
        # Config snapshot assertions
        config = info["config_snapshot"]
        assert config["some_safe_key"] == "safe-value"
        assert config["client_id"] == "1234567890"
        
        # Verify secrets are redacted
        assert config["discord_bot_token"] == "***REDACTED***"
        assert config["jwt_secret"] == "***REDACTED***"
        assert config["admin_password_hash"] == "***REDACTED***"
        
        # Verify log tail did not get altered inside the zip (or check if it was packed)
        log_content = zipf.read("aegis.log").decode("utf-8")
        assert "Line 1: Log info" in log_content

    # Double check that no files were written outside of paths_tmp.diagnostics
    # By listing files in root and verifying only expected subdirs exist
    for root_item in paths_tmp.root.iterdir():
        if root_item.is_file():
            assert root_item.name == "aegis.db" or root_item.name == ".write_probe"
