import zipfile
import re
from unittest.mock import MagicMock

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

def test_diagnostics_redaction_audit(paths_tmp):
    """ST-1: Diagnostics ZIP Redaction Audit.
    Ensures that the generated zip diagnostics archive never leaks credentials,
    secrets, or .env files.
    """
    # Setup mock core object
    mock_core = MagicMock()
    mock_core.paths = paths_tmp
    mock_core.config = MockConfig()
    mock_core.state = MockState()
    mock_core.db = None
    mock_core._start_time = 123456789.0
    
    # Write sensitive credentials directly into logs to test redaction
    sensitive_token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTA.abcdef.ghijklmnopqrstuvwxyzABCDE" # 24.6.27 format
    alternative_token = "MTIzNDU2Nzg5MDEyMzQ1Njc4OTAxMi.abcde_.ghijklmnopqrstuvwxyzABCDEF12" # 30.6.32 format
    db_password_str = "postgresql://my_user:super_secret_db_pass@127.0.0.1:5432/db"
    env_var_leak = "JWT_SECRET=super_secret_jwt"
    session_cookie_leak = "session_cookie: abc123xyz456"
    client_secret_leak = "client_secret = secret_123_abc"
    
    with open(paths_tmp.log_file, "w", encoding="utf-8") as f:
        f.write(f"Line 1: INFO - Bot starting with token {sensitive_token}\n")
        f.write(f"Line 2: INFO - Alternate token: {alternative_token}\n")
        f.write(f"Line 3: ERROR - Failed to connect to {db_password_str}\n")
        f.write(f"Line 4: DEBUG - {env_var_leak}\n")
        f.write(f"Line 5: DEBUG - {session_cookie_leak}\n")
        f.write(f"Line 6: DEBUG - {client_secret_leak}\n")
        
    with open(paths_tmp.err_log_file, "w", encoding="utf-8") as f:
        f.write(f"CRITICAL - Secrets leaked: {sensitive_token} and {db_password_str}\n")
        
    # Generate diagnostics package
    zip_path = generate_package(mock_core)
    
    assert zip_path.exists()
    
    # Regex to test for Discord client bot tokens
    token_regex = re.compile(r'[a-zA-Z0-9_\-\.]{24,36}\.[a-zA-Z0-9_\-\.]{6}\.[a-zA-Z0-9_\-\.]{27,43}')
    
    # Check zip contents
    with zipfile.ZipFile(zip_path, 'r') as zipf:
        namelist = zipf.namelist()
        
        # Assertion: If .env files are present in the zip structure, it fails
        for name in namelist:
            assert ".env" not in name.lower(), f".env file detected in ZIP: {name}"
            
        # Inspect info.json, aegis.log, and aegis.err.log
        for filename in ["info.json", "aegis.log", "aegis.err.log"]:
            if filename in namelist:
                content = zipf.read(filename).decode("utf-8")
                
                # Check for Discord client bot tokens
                matches = token_regex.findall(content)
                assert not matches, f"Discord token leaked in {filename}: {matches}"
                
                # Check for client secrets, session cookies, database passwords, .env file contents
                # None of the raw secrets should be in the content
                assert sensitive_token not in content, f"Sensitive token leaked in {filename}"
                assert alternative_token not in content, f"Alternative token leaked in {filename}"
                assert "super_secret_db_pass" not in content, f"Database password leaked in {filename}"
                assert "super_secret_jwt" not in content, f"JWT secret leaked in {filename}"
                assert "abc123xyz456" not in content, f"Session cookie leaked in {filename}"
                assert "secret_123_abc" not in content, f"Client secret leaked in {filename}"
