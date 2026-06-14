import pytest
from fastapi.testclient import TestClient
from unittest.mock import MagicMock
import json

from aegis.core.app_core import AppCore
from aegis.config.loader import ConfigStore
import aegis.core.utils as utils
import aegis.bot.bot_manager as bot_manager
from aegis.web.app import build_app

def test_custom_embed_presets_api(paths_tmp, monkeypatch):
    # Patch CONFIG_PATH to use paths_tmp for database isolation
    monkeypatch.setattr(utils, "CONFIG_PATH", paths_tmp.config_file)
    
    # Ensure ADMIN_PASSWORD_HASH is set to bypass the incomplete setup middleware check
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")

    
    # Setup initial config.json with a custom preset for guild 12345
    config_data = {
        "client_id": "123456",
        "setup_complete": True,
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
        },
        "guild_configs": {
            "12345": {
                "custom_embed_presets": {
                    "Old Preset": {
                        "title": "Old Welcome",
                        "description": "Welcome to old server"
                    }
                }
            }
        }
    }
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    core = AppCore(paths_tmp)
    core.config = ConfigStore.load(paths_tmp)
    
    # Mock bot
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.config = core.config.as_dict()
    core.bot = bot
    monkeypatch.setattr(bot_manager, "bot_instance", bot)
    
    # Mock authentication checks - Admin
    monkeypatch.setattr("aegis.core.auth.get_session_role", lambda token: "admin")
    monkeypatch.setattr("aegis.core.auth.get_session_guild_id", lambda token: None)
    monkeypatch.setattr("aegis.core.auth.validate_session", lambda token: True)
    
    app = build_app(core)
    client = TestClient(app)
    
    headers = {"Authorization": "Bearer admin_token"}
    
    # 1. Test GET presets
    res = client.get("/api/guilds/12345/embeds/presets", headers=headers)
    assert res.status_code == 200
    presets = res.json()
    assert "Old Preset" in presets
    assert presets["Old Preset"]["title"] == "Old Welcome"
    
    # 2. Test POST preset (Save)
    new_preset_payload = {
        "title": "New Rules",
        "description": "Follow the rules!",
        "fields": [{"name": "Rule 1", "value": "Be nice", "inline": True}]
    }
    res = client.post("/api/guilds/12345/embeds/presets/New%20Preset", json=new_preset_payload, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    
    # Reload configs and verify save
    core.config = ConfigStore.load(paths_tmp)
    guild_conf = utils.get_guild_config("12345")
    assert "New Preset" in guild_conf["custom_embed_presets"]
    assert guild_conf["custom_embed_presets"]["New Preset"]["title"] == "New Rules"
    
    # 3. Test DELETE preset
    res = client.delete("/api/guilds/12345/embeds/presets/Old%20Preset", headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    
    # Verify deletion in config
    core.config = ConfigStore.load(paths_tmp)
    guild_conf = utils.get_guild_config("12345")
    assert "Old Preset" not in guild_conf["custom_embed_presets"]
    
    # 4. Test DELETE non-existent preset (should return 404)
    res = client.delete("/api/guilds/12345/embeds/presets/NonExistent", headers=headers)
    assert res.status_code == 404
    
    # 5. Test tenant security boundaries (tenant for 12345 tries to access 99999 - should be 403 Forbidden)
    monkeypatch.setattr("aegis.core.auth.get_session_role", lambda token: "tenant")
    monkeypatch.setattr("aegis.core.auth.get_session_guild_id", lambda token: "12345")
    
    headers_tenant = {"Authorization": "Bearer tenant_token"}
    res = client.get("/api/guilds/99999/embeds/presets", headers=headers_tenant)
    assert res.status_code == 403
    
    # But tenant for 12345 CAN access 12345 presets
    res = client.get("/api/guilds/12345/embeds/presets", headers=headers_tenant)
    assert res.status_code == 200
