import os
import json
import pytest
from fastapi.testclient import TestClient

from aegis.core.paths import Paths
from aegis.config.schema import validate_config
from aegis.core.state import LifecycleState, ReasonCode
from aegis.web.app import build_app
from aegis.core.app_core import AppCore
import auth

@pytest.fixture
def core_app(paths_tmp, monkeypatch):
    core = AppCore(paths=paths_tmp)
    
    # Ensure config setup complete is False initially
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
    core.web_port = 8000
    
    return core

def test_destructive_endpoints_always_require_admin(core_app, monkeypatch):
    app = build_app(core_app)
    client = TestClient(app)
    
    # Set password hash to enforce auth
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")
    
    destructive_paths = [
        "/api/recovery/db/rebuild",
        "/api/recovery/db/restore",
        "/api/recovery/restart"
    ]
    
    # Test Scenario A: RUNNING State
    core_app.state._current_state = LifecycleState.RUNNING
    core_app.state._reason = None
    
    for path in destructive_paths:
        # Case 1: Unauthenticated -> should return 401
        r = client.post(path, json={"backup_name": "aegis_test.db"})
        assert r.status_code == 401, f"{path} did not reject unauthenticated request in RUNNING"
        
        # Case 2: Tenant session -> should return 403
        tenant_token = auth.create_session(role="tenant", guild_id="123")
        r = client.post(path, json={"backup_name": "aegis_test.db"}, headers={"Authorization": f"Bearer {tenant_token}"})
        assert r.status_code == 403, f"{path} allowed tenant access in RUNNING"
        
        # Case 3: Admin session -> should proceed (i.e. not return 401/403)
        # Note: Handlers might fail with 500 or 400 due to mocks but should bypass auth (not return 401/403)
        admin_token = auth.create_session(role="admin")
        # We mock database operations or check return codes
        r = client.post(path, json={"backup_name": "aegis_test.db"}, headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code not in (401, 403), f"{path} rejected admin in RUNNING: {r.status_code}"

    # Test Scenario B: SAFE_MODE State
    core_app.state._current_state = LifecycleState.SAFE_MODE
    core_app.state._reason = ReasonCode.TOKEN_RECOVERY
    
    for path in destructive_paths:
        # Case 1: Unauthenticated -> should return 401
        r = client.post(path, json={"backup_name": "aegis_test.db"})
        assert r.status_code == 401, f"{path} did not reject unauthenticated request in SAFE_MODE"
        
        # Case 2: Tenant session -> should return 403
        tenant_token = auth.create_session(role="tenant", guild_id="123")
        r = client.post(path, json={"backup_name": "aegis_test.db"}, headers={"Authorization": f"Bearer {tenant_token}"})
        assert r.status_code == 403, f"{path} allowed tenant access in SAFE_MODE"
        
        # Case 3: Admin session -> should proceed
        admin_token = auth.create_session(role="admin")
        r = client.post(path, json={"backup_name": "aegis_test.db"}, headers={"Authorization": f"Bearer {admin_token}"})
        assert r.status_code not in (401, 403), f"{path} rejected admin in SAFE_MODE: {r.status_code}"

def test_pre_auth_endpoints_bypass_checks(core_app, monkeypatch):
    app = build_app(core_app)
    client = TestClient(app)
    
    # 1. When PASSWORD HASH IS UNSET (first run) -> pre-auth endpoints should bypass auth in RUNNING or SAFE_MODE
    monkeypatch.delenv("ADMIN_PASSWORD_HASH", raising=False)
    core_app.state._current_state = LifecycleState.SAFE_MODE
    core_app.state._reason = ReasonCode.NEEDS_SETUP
    
    # Pre-auth routes: e.g. /wizard/token, /api/recovery/retry
    # They should not return 401/403
    r = client.post("/wizard/token", json={"token": "some_token"})
    assert r.status_code not in (401, 403)
    
    r = client.post("/api/recovery/retry")
    assert r.status_code not in (401, 403)
    
    # 2. When PASSWORD HASH IS SET -> pre-auth endpoints bypass ONLY in SAFE_MODE
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")
    
    # SAFE_MODE -> should bypass
    core_app.state._current_state = LifecycleState.SAFE_MODE
    core_app.state._reason = ReasonCode.TOKEN_RECOVERY
    r = client.post("/wizard/token", json={"token": "some_token"})
    assert r.status_code not in (401, 403)
    
    # RUNNING -> should NOT bypass (falls through to normal auth check)
    core_app.state._current_state = LifecycleState.RUNNING
    core_app.state._reason = None
    r = client.post("/wizard/token", json={"token": "some_token"})
    assert r.status_code in (401, 403)

def test_origin_header_validation(core_app, monkeypatch):
    app = build_app(core_app)
    client = TestClient(app)
    
    # Set password hash to enforce auth
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")
    core_app.state._current_state = LifecycleState.SAFE_MODE
    core_app.state._reason = ReasonCode.TOKEN_RECOVERY
    
    # Scenario 1: core.web_port is set to 8000
    core_app.web_port = 8000
    
    # Expected origin is http://127.0.0.1:8000
    # A) Valid origin -> Allowed to proceed (returns 401 or runs handler; not 403 from Origin check)
    r = client.post("/wizard/token", json={"token": "some_token"}, headers={"Origin": "http://127.0.0.1:8000"})
    assert r.status_code not in (401, 403) or r.status_code == 401 # Should bypass or fail normally
    
    # B) Mismatched origin -> Rejected with 403
    r = client.post("/wizard/token", json={"token": "some_token"}, headers={"Origin": "http://evil.com"})
    assert r.status_code == 403
    
    # C) Absent origin -> Allowed to proceed
    r = client.post("/wizard/token", json={"token": "some_token"})
    assert r.status_code not in (401, 403)
    
    # Scenario 2: core.web_port is None (cannot be determined)
    core_app.web_port = None
    
    # A) Origin validation should be SKIPPED completely (as per user comment)
    r = client.post("/wizard/token", json={"token": "some_token"}, headers={"Origin": "http://evil.com"})
    # Since we skipped Origin validation, evil.com is not rejected by Origin check.
    # It proceeds to auth/validation check (which might return 200 or 400, but not 403 Origin error)
    assert r.status_code != 403 or "Cross-Origin" not in r.json().get("detail", "")
