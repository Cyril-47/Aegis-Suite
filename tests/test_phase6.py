import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch, AsyncMock

from aegis.core.app_core import AppCore
from aegis.core.state import LifecycleState, ReasonCode
from aegis.web.app import build_app
from aegis.bot.runner import TokenVerdict
from aegis.db.models import Server
from sqlalchemy.orm import sessionmaker

@pytest.fixture
def app_and_client(paths_tmp, temp_appdata):
    """Sets up a TestClient with AppCore in SAFE_MODE needs-setup state."""
    core = AppCore(paths=paths_tmp)
    # Put machine into safe mode needs-setup
    core.state.transition(LifecycleState.SAFE_MODE, ReasonCode.NEEDS_SETUP)
    app = build_app(core)
    client = TestClient(app)
    return core, client

def test_get_setup_renders_wizard(app_and_client):
    core, client = app_and_client
    
    # 1. Initially, setup is not complete, so /setup renders wizard HTML
    r = client.get("/setup")
    assert r.status_code == 200
    assert "Setup Wizard" in r.text
    assert "Welcome to Aegis Suite Onboarding" in r.text

    # 2. Mock setup complete in config and reload
    from aegis.config.loader import ConfigStore
    from aegis.web.routes.wizard import build_default_config
    
    default_config = build_default_config("987654321")
    default_config.setup_complete = True
    core.config = ConfigStore(core.paths, default_config)
    core.config.save()
    
    # Now /setup should redirect to /
    r = client.get("/setup", follow_redirects=False)
    assert r.status_code == 307
    assert r.headers["location"] == "/"

def test_wizard_token_validation_success(app_and_client):
    core, client = app_and_client
    
    # POST to /wizard/token with a valid dummy token format
    valid_token = "MTIzNDU2Nzg5.DEF.GHI"
    
    # Stub validate_token to return TokenVerdict.OK
    with patch("aegis.web.routes.wizard.validate_token", return_value=TokenVerdict.OK) as mock_val:
        r = client.post("/wizard/token", json={"token": valid_token})
        assert r.status_code == 200
        assert r.json()["status"] == "success"
        
    # Verify client ID was extracted (123456789) and config.json updated
    assert core.config is not None
    assert core.config.client_id == "123456789"
    assert core.config.is_setup_complete() is False # not complete until finish

    # Verify secret is saved to .env file
    env_path = core.paths.root / ".env"
    assert env_path.exists()
    content = env_path.read_text(encoding="utf-8")
    assert f"DISCORD_BOT_TOKEN={valid_token}" in content

def test_wizard_token_validation_failure(app_and_client):
    core, client = app_and_client
    
    # Stub validate_token to return AUTH_FAILED
    with patch("aegis.web.routes.wizard.validate_token", return_value=TokenVerdict.AUTH_FAILED):
        r = client.post("/wizard/token", json={"token": "bad_token"})
        assert r.status_code == 400
        assert "Authentication check failed" in r.json()["detail"]

    # Stub validate_token to return INTENT_FAILED
    with patch("aegis.web.routes.wizard.validate_token", return_value=TokenVerdict.INTENT_FAILED):
        r = client.post("/wizard/token", json={"token": "intent_failed_token"})
        assert r.status_code == 400
        assert "Intents check failed" in r.json()["detail"]

def test_wizard_guilds_list(app_and_client, monkeypatch):
    core, client = app_and_client
    
    # Clear token in env first
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    
    # 1. No token configured raises 400
    r = client.get("/wizard/guilds")
    assert r.status_code == 400
    assert "No Discord token configured" in r.json()["detail"]

    # 2. Configure a dummy valid token in environment and config.json
    from aegis.config.loader import ConfigStore
    from aegis.web.routes.wizard import build_default_config
    
    core.config = ConfigStore(core.paths, build_default_config("123456789"))
    core.config.save()
    
    os.environ["DISCORD_BOT_TOKEN"] = "valid_token.abc.def"
    
    mock_response = MagicMock()
    mock_response.status = 200
    mock_response.json = AsyncMock(return_value=[
        {"id": "123456789", "name": "Test Guild 1"},
        {"id": "987654321", "name": "Test Guild 2"}
    ])
    
    class MockClientSession:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass
        def get(self, url, headers=None, timeout=None):
            class MockGetContext:
                async def __aenter__(self):
                    return mock_response
                async def __aexit__(self, exc_type, exc_val, exc_tb):
                    pass
            return MockGetContext()
            
    with patch("aiohttp.ClientSession", MockClientSession):
        r = client.get("/wizard/guilds")
        
    assert r.status_code == 200
    guilds = r.json()
    assert len(guilds) == 2
    assert guilds[0]["name"] == "Test Guild 1"
    assert guilds[1]["name"] == "Test Guild 2"


def test_wizard_templates_metadata(app_and_client):
    core, client = app_and_client
    
    r = client.get("/wizard/templates")
    assert r.status_code == 200
    data = r.json()
    assert "gaming" in data
    assert "community" in data
    assert "creator" in data
    assert "empty" in data
    assert data["gaming"]["roles"] == ["Admin", "Moderator", "Gamer"]

def test_wizard_finish_flow(app_and_client):
    core, client = app_and_client
    
    # Pre-populate config
    from aegis.config.loader import ConfigStore
    from aegis.web.routes.wizard import build_default_config
    core.config = ConfigStore(core.paths, build_default_config("123456789"))
    core.config.save()
    
    # Make sure database engine exists
    from aegis.db.engine import make_engine
    core.db = make_engine(core.paths)
    
    # Disable bot task done callback to prevent loop wind-down transition back to safe mode
    core._on_bot_task_done = lambda task: None
    
    # Call /wizard/finish

    with patch("aegis.web.routes.wizard.run_startup_checks", return_value=("OK", None)):
        r = client.post("/wizard/finish", json={
            "guild_id": "999888777",
            "template_kind": "gaming"
        })
        assert r.status_code == 200
        assert r.json()["status"] == "success"
        
    # Verify setup_complete was set to True
    assert core.config.is_setup_complete() is True
    
    # Verify the target guild was saved to the Server DB table
    Session = sessionmaker(bind=core.db)
    with Session() as session:
        server = session.query(Server).filter(Server.guild_id == "999888777").first()
        assert server is not None
        assert server.guild_id == "999888777"
        
    # Verify the system promoted to RUNNING
    assert core.state.current_state == LifecycleState.RUNNING

