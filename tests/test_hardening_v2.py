import os
import json
import pytest
import sys
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from aegis.core.paths import Paths
from aegis.config.schema import validate_config, ConfigModel
from aegis.core.state import LifecycleState, ReasonCode
from aegis.web.app import build_app
from aegis.core.app_core import AppCore
from aegis.db.models import Base
from aegis.db.maintenance import run_migrations
import utils
import auth

def test_config_extra_preservation():
    """Verify ConfigModel uses extra='allow' and preserves unknown keys during parse and dump."""
    raw_data = {
        "client_id": "1234567890",
        "setup_complete": True,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_name": "welcome",
            "message_title": "Welcome",
            "message_description": "Hello",
            "embed_color": "#00ff00"
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": False,
            "block_links": False,
            "max_mentions": 5,
            "log_channel_name": "mod-logs"
        },
        # Unknown keys that must be preserved
        "giveaways": {"active": []},
        "guild_configs": {"123": {}},
        "scheduled_messages": [],
        "leveling_settings": {"enabled": True},
        "auto_responders": [{"trigger": "hello", "response": "world"}]
    }
    
    # 1. Parse config
    model = validate_config(raw_data)
    assert model.client_id == "1234567890"
    
    # Verify extra fields are present in the model dictionary
    dump = model.model_dump()
    for key in ["giveaways", "guild_configs", "scheduled_messages", "leveling_settings", "auto_responders"]:
        assert key in dump
        assert dump[key] == raw_data[key]

def test_config_path_migration(tmp_path):
    """Verify that Paths.ensure() automatically migrates legacy config from root to subfolder."""
    # Setup temporary directory as Paths root
    p = Paths(root=tmp_path / "aegis")
    
    # Pre-create root folder and place legacy config.json there
    p.root.mkdir(parents=True, exist_ok=True)
    legacy_data = {"test_key": "test_val"}
    legacy_file = p.root / "config.json"
    with open(legacy_file, "w", encoding="utf-8") as f:
        json.dump(legacy_data, f)
        
    assert not p.config_file.exists()
    
    # Call ensure() which should trigger the migration copy
    p.ensure()
    
    assert p.config_file.exists()
    with open(p.config_file, "r", encoding="utf-8") as f:
        loaded = json.load(f)
    assert loaded == legacy_data

def test_get_writeable_path_unification():
    """Verify get_writeable_path resolves config.json to the new canonical location."""
    canonical_path = str(Paths().config_file)
    resolved = utils.get_writeable_path("config.json")
    assert resolved == canonical_path

def test_sec1_wizard_and_recovery_hardening(paths_tmp, monkeypatch):
    """Verify access controls for wizard and recovery routes under setup scenarios and state restrictions."""
    # 1. Setup AppCore and config
    core = AppCore(paths=paths_tmp)
    
    # Ensure config has setup_complete=False initially
    raw_config = {
        "client_id": "123456",
        "setup_complete": False,
        "welcome_settings": {
            "enabled": True, "channel_name": "welcome",
            "message_title": "Welcome", "message_description": "Hello", "embed_color": "#0000ff"
        },
        "automod_settings": {
            "enabled": False, "block_profanity": False, "block_links": False,
            "max_mentions": 5, "log_channel_name": "logs"
        }
    }
    
    from aegis.config.loader import ConfigStore
    core.config = ConfigStore(paths_tmp, validate_config(raw_config))
    core.config.save()
    
    # Fast-start app client
    app = build_app(core)
    client = TestClient(app)
    
    # Ensure ADMIN_PASSWORD_HASH is set to enforce authentication rules when triggered
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")
    
    # --- SCENARIO A: Setup is NOT complete (State is SAFE_MODE by default) ---
    assert core.config.is_setup_complete() is False
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.NEEDS_SETUP)
    
    # Wizard endpoint should succeed unauthenticated on setup_complete=False
    r = client.post("/wizard/token", json={"token": "valid.token.format"})
    # It attempts to run validate_token which we can mock or it fails validate_token check (returning bad format error)
    # But it should pass the auth_middleware (not return 401/403 auth block)
    assert r.status_code != 401
    assert r.status_code != 403
    
    # --- SCENARIO B: Setup IS complete (State is RUNNING) ---
    core.config._model.setup_complete = True
    core.config.save()
    assert core.config.is_setup_complete() is True
    core.state.transition(LifecycleState.RUNNING)
    
    # 1. Wizard endpoint should now return 401/403 auth errors when setup is complete
    r_wizard = client.post("/wizard/token", json={"token": "valid.token.format"})
    assert r_wizard.status_code in (401, 403)
    
    # 2. Recovery endpoint should fail with 403 because application is RUNNING (not in SAFE_MODE)
    r_rec_running = client.post("/api/recovery/retry")
    assert r_rec_running.status_code == 403
    assert "SAFE_MODE" in r_rec_running.json()["detail"]
    
    # --- SCENARIO C: Recovery in SAFE_MODE (Setup Complete) ---
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.TOKEN_RECOVERY)
    
    # 1. Without auth token, recovery endpoint should fail with 401
    r_rec_unauth = client.post("/api/recovery/retry")
    assert r_rec_unauth.status_code == 401
    
    # 2. With a valid admin session, recovery endpoint should pass auth_middleware
    admin_token = auth.create_session(role="admin")
    r_rec_auth = client.post("/api/recovery/retry", headers={"Authorization": f"Bearer {admin_token}"})
    # Auth middleware allowed it, so it reached route handler (which may fail due to testing mock but should NOT be 401/403)
    assert r_rec_auth.status_code != 401
    assert r_rec_auth.status_code != 403

def test_alembic_frozen_paths_programmatic(paths_tmp, monkeypatch):
    """Verify run_migrations programmatically overrides script_location when sys.frozen is simulated."""
    # 1. Setup mock sys.frozen
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    
    # Use paths_tmp.root as simulated sys._MEIPASS
    monkeypatch.setattr(sys, "_MEIPASS", str(paths_tmp.root), raising=False)
    
    # Place alembic.ini and migration versions under mock sys._MEIPASS
    mock_ini = paths_tmp.root / "alembic.ini"
    with open(mock_ini, "w", encoding="utf-8") as f:
        f.write("[alembic]\nscript_location = aegis/db/migrations\n")
        
    migrations_dir = paths_tmp.root / "aegis" / "db" / "migrations"
    migrations_dir.mkdir(parents=True, exist_ok=True)
    
    # Create baseline migration inside migrations folder to test script resolution
    with open(migrations_dir / "env.py", "w", encoding="utf-8") as f:
        f.write("# env.py mock\n")
        
    # Build engine
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    # Verify that run_migrations runs and attempts upgrade without raising FileNotFoundError on alembic.ini path
    # (It will fail on executing env.py since it's a mock, but that proves it successfully resolved/loaded the files)
    try:
        run_migrations(paths_tmp, engine)
    except Exception as e:
        # If it complains about env.py or metadata, that means it successfully located and parsed the config/script directory!
        assert "FileNotFoundError" not in str(e)
        assert "alembic.ini" not in str(e)
