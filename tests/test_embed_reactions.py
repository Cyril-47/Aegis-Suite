import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
from aegis.bot.bot_manager import add_reactions_from_embeds
from fastapi.testclient import TestClient
from aegis.core.app_core import AppCore
from aegis.config.loader import ConfigStore
import aegis.core.utils as utils
import aegis.bot.bot_manager as bot_manager
from aegis.web.app import build_app
import json

@pytest.mark.asyncio
async def test_add_reactions_from_embeds():
    # Mock message
    msg = AsyncMock(spec=discord.Message)
    msg.id = 99999
    
    # 1. Test with discord.Embed objects
    embed1 = discord.Embed(title="Test Embed")
    embed1.add_field(name="1️⃣ Option A", value="Val A")
    embed1.add_field(name="🎮 Gaming Option", value="Val B")
    embed1.add_field(name="No emoji", value="Val C")
    
    await add_reactions_from_embeds(msg, [embed1])
    
    # Verify add_reaction was called with expected emojis
    assert msg.add_reaction.call_count == 2
    msg.add_reaction.assert_any_call("1️⃣")
    msg.add_reaction.assert_any_call("🎮")
    
    # Reset mock for next test
    msg.add_reaction.reset_mock()
    
    # 2. Test with dict representation of embeds (e.g. from scheduler)
    dict_embed = {
        "title": "Dict Embed",
        "fields": [
            {"name": "2️⃣ Option B", "value": "Val B"},
            {"name": "<:pepe:123456789012345678> Pepe Custom", "value": "Val Custom"},
            {"name": "2️⃣ Duplicate Option", "value": "Duplicate"}
        ]
    }
    
    await add_reactions_from_embeds(msg, [dict_embed])
    
    # Verify reactions: "2️⃣" and "<:pepe:123456789012345678>". Duplicate "2️⃣" should be ignored/de-duplicated.
    assert msg.add_reaction.call_count == 2
    msg.add_reaction.assert_any_call("2️⃣")
    msg.add_reaction.assert_any_call("<:pepe:123456789012345678>")
    
    # Reset mock
    msg.add_reaction.reset_mock()
    
    # 3. Test exception safety (should not raise exception)
    msg.add_reaction.side_effect = Exception("Discord API error")
    embed_error = discord.Embed(title="Error Embed")
    embed_error.add_field(name="🎵 Music", value="Val")
    
    # This should execute without throwing the exception, logging it instead
    await add_reactions_from_embeds(msg, [embed_error])
    msg.add_reaction.assert_called_once_with("🎵")

def test_send_embed_route_reactions(paths_tmp, monkeypatch):
    from aegis.core.app_core import _active_cores
    _active_cores.clear()
    monkeypatch.setattr(utils, "CONFIG_PATH", paths_tmp.config_file)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")

    
    # Write fully schema-compliant config
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
        }
    }
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    core = AppCore(paths_tmp)
    core.config = ConfigStore.load(paths_tmp)
    
    # Mock bot, guild, and channel
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.config = core.config.as_dict()
    
    guild = MagicMock()
    channel = MagicMock()
    
    # channel.send returns a mock message
    sent_msg = AsyncMock(spec=discord.Message)
    channel.send = AsyncMock(return_value=sent_msg)
    
    guild.get_channel.return_value = channel
    bot.get_guild.return_value = guild
    
    core.bot = bot
    monkeypatch.setattr(bot_manager, "bot_instance", bot)
    
    # Mock authentication
    monkeypatch.setattr("aegis.core.auth.get_session_role", lambda token: "admin")
    monkeypatch.setattr("aegis.core.auth.get_session_guild_id", lambda token: None)
    monkeypatch.setattr("aegis.core.auth.validate_session", lambda token: True)
    
    app = build_app(core)
    client = TestClient(app)
    
    headers = {"Authorization": "Bearer admin_token"}
    
    # 1. Send embed with add_reactions=False
    payload_no_react = {
        "channel_id": "999",
        "embed": {
            "title": "Title",
            "fields": [{"name": "🎮 Gaming", "value": "Val"}]
        },
        "add_reactions": False
    }
    
    # Mock the helper function to see if it is called or check reactions
    mock_add_reactions = AsyncMock()
    monkeypatch.setattr(bot_manager, "add_reactions_from_embeds", mock_add_reactions)
    
    res = client.post("/api/guilds/12345/embeds/send", json=payload_no_react, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    
    # Helper should NOT have been called
    mock_add_reactions.assert_not_called()
    
    # 2. Send embed with add_reactions=True
    payload_react = {
        "channel_id": "999",
        "embed": {
            "title": "Title",
            "fields": [{"name": "🎮 Gaming", "value": "Val"}]
        },
        "add_reactions": True
    }
    
    res = client.post("/api/guilds/12345/embeds/send", json=payload_react, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    
    # Helper SHOULD have been called once
    mock_add_reactions.assert_called_once()

def test_process_embed_data_urls():
    from aegis.bot.bot_manager import process_embed_data_urls
    
    # 1. Base64 png thumbnail & jpeg image
    embeds = [
        {
            "title": "Embed 1",
            "thumbnail": {
                "url": "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
            },
            "image": {
                "url": "data:image/jpeg;base64,/9j/4AAQSkZJRgABAQEASABIAAD/2wBDAP//////////////////////////////////////////////////////////////////////////////////////wgALCAABAAEBAREA/8QAFBABAAAAAAAAAAAAAAAAAAAAAP/aAAgBAQABPxA="
            }
        }
    ]
    
    processed, files = process_embed_data_urls(embeds)
    
    assert len(files) == 2
    assert isinstance(files[0], discord.File)
    assert files[0].filename == "thumbnail_0.png"
    assert isinstance(files[1], discord.File)
    assert files[1].filename == "image_1.jpeg"
    
    # Verify replaced URLs
    assert processed[0]["thumbnail"]["url"] == "attachment://thumbnail_0.png"
    assert processed[0]["image"]["url"] == "attachment://image_1.jpeg"

def test_dm_user_resolutions(paths_tmp, monkeypatch):
    from aegis.core.app_core import _active_cores
    _active_cores.clear()
    monkeypatch.setattr(utils, "CONFIG_PATH", paths_tmp.config_file)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", "some_hash")

    
    # Write fully schema-compliant config
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
        }
    }
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    core = AppCore(paths_tmp)
    core.config = ConfigStore.load(paths_tmp)
    
    # Mock bot, guild, and member
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.config = core.config.as_dict()
    
    guild = MagicMock()
    member = MagicMock(spec=discord.Member)
    member.name = "Cyril"
    member.display_name = "Cyril Display"
    
    sent_msg = AsyncMock(spec=discord.Message)
    member.send = AsyncMock(return_value=sent_msg)
    
    # Mock lookup methods
    guild.get_member.return_value = None
    guild.fetch_member = AsyncMock(side_effect=Exception("Not found"))
    guild.get_member_named.return_value = member
    
    bot.get_guild.return_value = guild
    
    core.bot = bot
    monkeypatch.setattr(bot_manager, "bot_instance", bot)
    
    # Mock authentication
    monkeypatch.setattr("aegis.core.auth.get_session_role", lambda token: "admin")
    monkeypatch.setattr("aegis.core.auth.get_session_guild_id", lambda token: None)
    monkeypatch.setattr("aegis.core.auth.validate_session", lambda token: True)
    
    app = build_app(core)
    client = TestClient(app)
    
    headers = {"Authorization": "Bearer admin_token"}
    
    # Send request with string username instead of numerical ID
    payload = {
        "dm_user_id": "cyril7662",
        "embed": {
            "title": "Title"
        }
    }
    
    res = client.post("/api/guilds/12345/embeds/send", json=payload, headers=headers)
    assert res.status_code == 200
    assert res.json() == {"status": "success"}
    guild.get_member_named.assert_called_with("cyril7662")
    member.send.assert_called_once()
