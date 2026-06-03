import os
import json
import pytest
import asyncio
from fastapi.testclient import TestClient

from unittest.mock import AsyncMock, MagicMock
from aegis.core.state import LifecycleState, ReasonCode
from aegis.core.app_core import AppCore
from aegis.core.lifecycle import run_startup_checks
from aegis.web.app import build_app
import auth

def get_valid_config_data() -> dict:
    return {
        "client_id": "123456789012345678",
        "setup_complete": True,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_name": "welcome",
            "message_title": "Welcome",
            "message_description": "Welcome to our server!",
            "embed_color": "#00FF00",
            "auto_assign_roles": []
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": True,
            "block_links": False,
            "max_mentions": 3,
            "log_channel_name": "automod-logs",
            "profanity_words": []
        }
    }

@pytest.mark.asyncio
async def test_startup_checks_needs_setup(paths_tmp, temp_appdata):
    """Verify that when config is missing, startup transitions to SAFE_MODE (needs-setup)."""
    core = AppCore(paths=paths_tmp)
    # Ensure config file is deleted
    paths_tmp.config_file.unlink(missing_ok=True)
    
    verdict, reason = await run_startup_checks(core)
    assert verdict == "FATAL-to-bot"
    assert reason == ReasonCode.NEEDS_SETUP
    assert core.health.checks.get("config") == "FATAL-to-bot"

@pytest.mark.asyncio
async def test_startup_checks_db_recovery(paths_tmp, temp_appdata):
    """Verify that when the database is corrupt, startup transitions to SAFE_MODE (db-recovery)."""
    core = AppCore(paths=paths_tmp)
    
    # 1. Write valid config file
    config_data = get_valid_config_data()
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    # 2. Corrupt the database file
    with open(paths_tmp.db_file, "w") as f:
        f.write("totally invalid database format")
        
    verdict, reason = await run_startup_checks(core)
    assert verdict == "FATAL-to-bot"
    assert reason == ReasonCode.DB_RECOVERY
    assert core.health.checks.get("database") == "FATAL-to-bot"

@pytest.mark.asyncio
async def test_startup_checks_token_recovery(paths_tmp, temp_appdata):
    """Verify that when the bot token is invalid, startup transitions to SAFE_MODE (token-recovery)."""
    core = AppCore(paths=paths_tmp)
    
    # Write valid config
    config_data = get_valid_config_data()
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    # Put an invalid token format in .env
    env_path = paths_tmp.root / ".env" # Or write_writeable_path
    os.environ["DISCORD_BOT_TOKEN"] = "bad_token"
    
    verdict, reason = await run_startup_checks(core)
    assert verdict == "FATAL-to-bot"
    assert reason == ReasonCode.TOKEN_RECOVERY
    assert core.health.checks.get("token") == "FATAL-to-bot"

@pytest.mark.asyncio
async def test_startup_checks_intent_recovery(paths_tmp, temp_appdata):
    """Verify that when the bot token causes intent check failure, startup transitions to SAFE_MODE (intent-recovery)."""
    core = AppCore(paths=paths_tmp)
    
    # Write valid config
    config_data = get_valid_config_data()
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    os.environ["DISCORD_BOT_TOKEN"] = "intent_failed"
    
    from unittest.mock import patch
    from aegis.bot.runner import TokenVerdict
    with patch("aegis.bot.runner.validate_token", return_value=TokenVerdict.INTENT_FAILED):
        verdict, reason = await run_startup_checks(core)
        
    assert verdict == "FATAL-to-bot"
    assert reason == ReasonCode.INTENT_RECOVERY
    assert core.health.checks.get("intents") == "FATAL-to-bot"

@pytest.mark.asyncio
async def test_startup_checks_happy_path(paths_tmp, temp_appdata):
    """Verify that on clean configuration and credentials, startup checks pass successfully."""
    core = AppCore(paths=paths_tmp)
    
    # Write valid config
    config_data = get_valid_config_data()
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    # Write valid token format (three dot-separated components)
    os.environ["DISCORD_BOT_TOKEN"] = "valid.discord.token"
    
    from unittest.mock import patch
    from aegis.bot.runner import TokenVerdict
    with patch("aegis.bot.runner.validate_token", return_value=TokenVerdict.OK):
        verdict, reason = await run_startup_checks(core)
        
    assert verdict == "OK"
    assert reason is None
    
    assert core.health.checks.get("data_directory") == "OK"
    assert core.health.checks.get("config") == "OK"
    assert core.health.checks.get("database") == "OK"
    assert core.health.checks.get("migrations") == "OK"
    assert core.health.checks.get("token") == "OK"
    assert core.health.checks.get("intents") == "OK"

def test_recovery_endpoints_html_serving(paths_tmp, temp_appdata):
    """Verify GET / serves recovery HTML in SAFE_MODE, or static index.html/text in RUNNING."""
    core = AppCore(paths=paths_tmp)
    
    # 1. Start in SAFE_MODE
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.TOKEN_RECOVERY)
    
    app = build_app(core)
    client = TestClient(app)
    
    r1 = client.get("/")
    assert r1.status_code == 200
    assert "text/html" in r1.headers["content-type"]
    assert "Discord Token Recovery" in r1.text
    
    # 2. Transition to RUNNING
    core.state.transition(LifecycleState.RUNNING)
    r2 = client.get("/")
    assert r2.status_code == 200
    # In test workspace we might not have static index.html built, so we fallback or serve index.html
    # In either case it shouldn't contain the Recovery template text.
    assert "Discord Token Recovery" not in r2.text

def test_recovery_endpoint_token_submission(paths_tmp, temp_appdata, monkeypatch):
    """Verify that posting a token validates it and saves it successfully."""
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    core = AppCore(paths=paths_tmp)
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.TOKEN_RECOVERY)
    
    # Setup initial config on disk so load doesn't crash
    config_data = get_valid_config_data()
    config_data["setup_complete"] = False
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    app = build_app(core)
    client = TestClient(app)
    
    from unittest.mock import patch
    from aegis.bot.runner import TokenVerdict
    
    async def mock_val(token, timeout=10.0):
        if token == "bad_token":
            return TokenVerdict.AUTH_FAILED
        return TokenVerdict.OK
        
    with patch("aegis.web.routes.wizard.validate_token", side_effect=mock_val):
        # Send invalid token
        r1 = client.post("/api/recovery/token", json={"token": "bad_token"})
        assert r1.status_code == 400
        
        # Send valid format token
        r2 = client.post("/api/recovery/token", json={"token": "token1.token2.token3"})
        assert r2.status_code == 200
        assert r2.json()["status"] == "success"
    
    # Verify environment variable and config files are updated
    assert os.environ.get("DISCORD_BOT_TOKEN") == "token1.token2.token3"
    
    # Load config and verify setup_complete is now True
    from aegis.config.loader import ConfigStore
    store = ConfigStore.load(paths_tmp)
    assert store.is_setup_complete() is True

def test_recovery_endpoint_backups_list(paths_tmp, temp_appdata, monkeypatch):
    """Verify backups listing returned chronologically."""
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    core = AppCore(paths=paths_tmp)
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
    
    # Create mock backup files
    paths_tmp.backups_db.mkdir(parents=True, exist_ok=True)
    f1 = paths_tmp.backups_db / "aegis_baseline_v1_20260531_120000.db"
    f2 = paths_tmp.backups_db / "aegis_baseline_v1_20260531_140000.db"
    f1.touch()
    f2.touch()
    import time
    now = time.time()
    os.utime(f1, (now - 3600, now - 3600))
    os.utime(f2, (now, now))
    
    app = build_app(core)
    client = TestClient(app)
    
    r = client.get("/api/recovery/backups")
    assert r.status_code == 200
    res = r.json()
    assert len(res) == 2
    # Sorted reverse lexicographically (newest first)
    assert res[0] == "aegis_baseline_v1_20260531_140000.db"
    assert res[1] == "aegis_baseline_v1_20260531_120000.db"

def test_recovery_endpoint_db_restore(paths_tmp, temp_appdata, monkeypatch):
    """Verify database file replacement on restore request."""
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("JWT_SECRET", "test_key")
    core = AppCore(paths=paths_tmp)
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
    paths_tmp.backups_db.mkdir(parents=True, exist_ok=True)
    backup_file = paths_tmp.backups_db / "aegis_baseline_v1_backup.db"
    with open(backup_file, "w") as f:
        f.write("original backup DB content")
        
    app = build_app(core)
    client = TestClient(app)
    
    admin_token = auth.create_session(role="admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    # Path traversal validation check
    r1 = client.post("/api/recovery/db/restore", json={"backup_name": "../config/config.json"}, headers=headers)
    assert r1.status_code == 400
    
    # Valid restore
    r2 = client.post("/api/recovery/db/restore", json={"backup_name": "aegis_baseline_v1_backup.db"}, headers=headers)
    assert r2.status_code == 200
    assert r2.json()["status"] == "success"
    
    # Verify core database engine is cleared (set to None) to force recreate
    assert core.db is None
    # Verify DB file was copied
    with open(paths_tmp.db_file, "r") as f:
        assert f.read() == "original backup DB content"

def test_recovery_endpoint_db_rebuild(paths_tmp, temp_appdata, monkeypatch):
    """Verify database schema is rebuilt from scratch."""
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    monkeypatch.setenv("JWT_SECRET", "test_key")
    core = AppCore(paths=paths_tmp)
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.DB_RECOVERY)
    
    app = build_app(core)
    client = TestClient(app)
    
    admin_token = auth.create_session(role="admin")
    headers = {"Authorization": f"Bearer {admin_token}"}
    
    r = client.post("/api/recovery/db/rebuild", headers=headers)
    assert r.status_code == 200
    assert r.json()["status"] == "success"
    
    # Core DB engine should be initialized and contain standard tables
    assert core.db is not None
    from aegis.db.maintenance import table_exists
    assert table_exists(core.db, "schema_meta") is True
    assert table_exists(core.db, "migration_log") is True

@pytest.mark.asyncio
async def test_recovery_endpoint_retry_promotion(paths_tmp, temp_appdata, monkeypatch):
    """Verify that posting retry runs startup checks and promotes state on success."""
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    core = AppCore(paths=paths_tmp)
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.TOKEN_RECOVERY)
    
    # Prevent TestClient's request cleanup from transitioning back to safe mode
    core._on_bot_task_done = lambda task: None
    
    # Initialize valid config and token so checks pass
    config_data = get_valid_config_data()
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
    os.environ["DISCORD_BOT_TOKEN"] = "valid.token.format"
    
    app = build_app(core)
    client = TestClient(app)
    
    from unittest.mock import patch
    from aegis.bot.runner import TokenVerdict
    
    with patch("aegis.bot.runner.validate_token", return_value=TokenVerdict.OK):
        # Post retry (which runs async, so we use TestClient)
        # Note: TestClient handles running async routes on the event loop
        r = client.post("/api/recovery/retry")
        assert r.status_code == 200
        assert r.json()["status"] == "running"
        
    assert core.state.current_state == LifecycleState.RUNNING
    # Should start bot task placeholders
    assert core._bot_task is not None

@pytest.mark.asyncio
async def test_recovery_endpoint_restart(paths_tmp, temp_appdata):
    """Verify that restart triggers shutdown request."""
    core = AppCore(paths=paths_tmp)
    
    # Mock request_shutdown to prevent loop closure issues in test environment
    core.request_shutdown = AsyncMock()
    
    # Construct a mock Request
    mock_request = MagicMock()
    mock_request.app.state.core = core
    mock_request.headers.get.return_value = "Bearer mock_token"
    
    from unittest.mock import patch
    with patch("auth.validate_session", return_value=True), \
         patch("auth.get_session_role", return_value="admin"):
        from aegis.web.routes.wizard import restart_application
        response = await restart_application(mock_request)
        
    assert response["status"] == "success"
    
    # Wait for the background task to run
    await asyncio.sleep(0.6)
    
    core.request_shutdown.assert_called_once()
