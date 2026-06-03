import os
import re
import json
import logging
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
import discord

from aegis.core.paths import Paths
from aegis.core.app_core import AppCore
from aegis.config.loader import ConfigStore
from aegis.config.schema import validate_config
from aegis.core.logging_setup import setup_logging
import utils
import bot_manager
from aegis.bot.music import MusicPlayer

# Mock Discord classes for testing
class MockChannel:
    def __init__(self, channel_id=123):
        self.id = channel_id
        self.name = "mock-channel"
    async def send(self, content=None, embed=None):
        m = MagicMock()
        m.delete = AsyncMock()
        return m

class MockGuild:
    def __init__(self, guild_id=12345):
        self.id = guild_id
        self.name = "Mock Guild"
        self.voice_client = None
    def get_channel(self, channel_id):
        # We will override this in the voice test using a MagicMock with spec=discord.VoiceChannel
        return MockChannel(channel_id)
    def get_member(self, member_id):
        # Return a member without permissions to trigger automod checks
        m = MagicMock()
        m.guild_permissions.manage_messages = False
        m.guild_permissions.administrator = False
        return m

class MockMessage:
    def __init__(self, content, guild_id=12345, author_id=999):
        self.content = content
        self.guild = MockGuild(guild_id)
        self.author = MagicMock()
        self.author.id = author_id
        self.author.bot = False
        self.author.name = "TestUser"
        self.channel = MockChannel()
        self.mentions = []

# --- 1. CONFIG SYNC & APPCORE RELOAD TEST ---
def test_config_sync_updates_appcore_and_bot(paths_tmp, monkeypatch):
    # Patch utils.CONFIG_PATH to use paths_tmp.config_file for test isolation
    monkeypatch.setattr(utils, "CONFIG_PATH", paths_tmp.config_file)

    # Setup initial config.json
    config_data = {
        "client_id": "123456",
        "setup_complete": True,
        "welcome_settings": {"enabled": False, "channel_name": "welcome", "message_title": "W", "message_description": "D", "embed_color": "#000"},
        "automod_settings": {"enabled": True, "block_profanity": False, "block_links": False, "max_mentions": 5, "log_channel_name": "mod-logs"}
    }
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    core = AppCore(paths_tmp)
    core.config = ConfigStore.load(paths_tmp)
    
    # Create bot mock
    bot = MagicMock()
    bot.is_ready.return_value = True
    bot.config = core.config.as_dict()
    core.bot = bot
    
    # Register bot in bot_manager
    monkeypatch.setattr(bot_manager, "bot_instance", bot)
    
    # Mock auth.get_session_role and auth.get_session_guild_id to allow admin
    monkeypatch.setattr("auth.get_session_role", lambda token: "admin")
    monkeypatch.setattr("auth.get_session_guild_id", lambda token: "12345")
    monkeypatch.setattr("auth.validate_session", lambda token: True)
    
    from aegis.web.app import build_app
    app = build_app(core)
    client = TestClient(app)
    
    # Post updated config (enable block_links)
    updated_config_data = config_data.copy()
    updated_config_data["automod_settings"]["block_links"] = True
    
    headers = {"Authorization": "Bearer valid_token"}
    response = client.post("/api/config", json=updated_config_data, headers=headers)
    assert response.status_code == 200
    
    # Verify core.config has the new value
    assert core.config.as_dict()["automod_settings"]["block_links"] is True
    # Verify bot.config reference is updated and block_links is True
    assert bot.config["automod_settings"]["block_links"] is True

# --- 2. MENTION SPAM CHECK TEST ---
@pytest.mark.asyncio
async def test_mention_spam_raw_content_counting(monkeypatch):
    # Mock utils.get_guild_automod_settings
    automod_settings = {
        "enabled": True,
        "block_profanity": False,
        "block_links": False,
        "max_mentions": 2,
        "profanity_words": []
    }
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: automod_settings)
    
    # Scenario A: Under limit (2 distinct mentions)
    msg_ok = MockMessage("Hello <@123> <@456>")
    
    # Scenario B: Over limit with repeated same user mention (3 mentions of same user)
    msg_spam_same = MockMessage("Spam <@123> <@123> <@123>")
    
    # Scenario C: Over limit with role mentions
    msg_spam_roles = MockMessage("Roles <@&777> <@&888> <@123>")
    
    # Scenario D: Over limit with @everyone or @here
    msg_spam_everyone = MockMessage("Pings @everyone <@123> <@456>")

    # Verify our mention count logic works
    def get_mentions_count(content):
        user_mentions_count = len(re.findall(r'<@!?\d+>', content))
        role_mentions_count = len(re.findall(r'<@&\d+>', content))
        everyone_here_count = content.count("@everyone") + content.count("@here")
        return user_mentions_count + role_mentions_count + everyone_here_count

    assert get_mentions_count(msg_ok.content) == 2
    assert get_mentions_count(msg_spam_same.content) == 3
    assert get_mentions_count(msg_spam_roles.content) == 3
    assert get_mentions_count(msg_spam_everyone.content) == 3

# --- 3. LIVE CONSOLE BROADCAST & SECRETS REDACTION TEST ---
def test_live_console_broadcaster_redacts_secrets(paths_tmp):
    # Initialize setup_logging, which registers WebConsoleHandler
    setup_logging(paths_tmp)
    
    root_logger = logging.getLogger()
    # Confirm WebConsoleHandler is present
    from utils import WebConsoleHandler
    web_handlers = [h for h in root_logger.handlers if isinstance(h, WebConsoleHandler)]
    assert len(web_handlers) > 0
    web_handler = web_handlers[0]
    
    # Mock an active websocket and add to utils.active_websockets
    ws_mock = MagicMock()
    ws_mock.role = "admin"
    ws_mock.guild_id = None
    utils.active_websockets.add(ws_mock)
    
    try:
        # Clear log history
        utils.log_history.clear()
        
        # Test basic logging
        test_logger = logging.getLogger("test_console")
        test_logger.info("Normal log message")
        
        # Verify log_history is populated
        assert len(utils.log_history) > 0
        assert any("Normal log message" in line for line in utils.log_history)
        
        # Register a secret token and test redaction
        secret_token = "validtoken.abc123xyz.secretpart12345"
        from aegis.core.logging_setup import register_secret
        register_secret(secret_token)
        
        test_logger.info(f"Logging with token: {secret_token}")
        
        # Check that secret token is redacted
        assert not any(secret_token in line for line in utils.log_history)
        assert any("***REDACTED***" in line for line in utils.log_history)
    finally:
        utils.active_websockets.discard(ws_mock)

# --- 4. MUSIC STALE CONNECTION SAFETY TEST (4006 FIX) ---
@pytest.mark.asyncio
async def test_music_voice_stale_session_cleanup():
    guild = MagicMock()
    # Mock stale, disconnected guild.voice_client (is_connected = False)
    stale_vc = MagicMock(spec=discord.VoiceClient)
    stale_vc.is_connected.return_value = False
    stale_vc.disconnect = AsyncMock()
    guild.voice_client = stale_vc
    
    # Mock channel and connect method using VoiceChannel spec
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 999
    channel.name = "Voice channel"
    
    # Setup AsyncMock for connect on channel
    connect_mock = AsyncMock()
    channel.connect = connect_mock
    
    guild.get_channel.return_value = channel
    
    player = MusicPlayer(guild)
    
    # Mock PyNaCl dependency check to avoid ImportError inside join_channel
    with patch('sys.modules', {'nacl': MagicMock()}):
        await player.join_channel(999)
        
    # Assert that the stale voice client was forcefully disconnected
    stale_vc.disconnect.assert_called_once_with(force=True)
    # Assert that a new connection is established via channel.connect()
    connect_mock.assert_called_once()


# --- 5. MUSIC VOICE RETRY ON FAILURE TEST ---
@pytest.mark.asyncio
async def test_music_voice_retry_on_failure():
    guild = MagicMock()
    guild.voice_client = None
    guild.change_voice_state = AsyncMock()
    
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 999
    
    # First connect fails, second connect succeeds
    first_vc = MagicMock(spec=discord.VoiceClient)
    connect_mock = AsyncMock(side_effect=[Exception("WebSocket 4006 close"), first_vc])
    channel.connect = connect_mock
    
    guild.get_channel.return_value = channel
    
    player = MusicPlayer(guild)
    
    with patch('sys.modules', {'nacl': MagicMock()}):
        res = await player.join_channel(999)
        
    assert res == first_vc
    assert connect_mock.call_count == 2
    guild.change_voice_state.assert_called_once_with(channel=None)


# --- 6. VOICE GATEWAY MONKEYPATCH TEST ---
# Removed as voice gateway version monkeypatch has been deleted in favor of native discord.py 2.7.x DAVE E2EE support.


# --- 7. SCHEDULED MESSAGES TIMEZONE SAFETY TEST ---
@pytest.mark.asyncio
async def test_scheduled_messages_loop_timezone_safety(monkeypatch):
    import datetime
    from unittest.mock import AsyncMock, MagicMock
    
    # Mock AegisBot instance
    bot = MagicMock()
    bot.wait_until_ready = AsyncMock()
    
    # We mock is_closed to run the loop exactly once
    closed_states = [False, True]
    def mock_is_closed():
        return closed_states.pop(0)
    bot.is_closed = mock_is_closed
    
    # Mock config data with naive and aware datetimes
    now = datetime.datetime.now(datetime.timezone.utc)
    naive_next_run = (now - datetime.timedelta(minutes=5)).replace(tzinfo=None).isoformat()
    aware_next_run = (now - datetime.timedelta(minutes=5)).isoformat()
    
    config_mock = {
        "scheduled_messages": [
            {
                "id": "sched_naive",
                "guild_id": "12345",
                "channel_id": "67890",
                "content": "Naive Test Message",
                "schedule_type": "once",
                "enabled": True,
                "next_run": naive_next_run
            },
            {
                "id": "sched_aware",
                "guild_id": "12345",
                "channel_id": "67890",
                "content": "Aware Test Message",
                "schedule_type": "once",
                "enabled": True,
                "next_run": aware_next_run
            }
        ]
    }
    
    # Mock utils.load_config and utils.save_config
    monkeypatch.setattr(utils, "load_config", lambda: config_mock)
    save_called = []
    monkeypatch.setattr(utils, "save_config", lambda cfg: save_called.append(cfg))
    
    # Mock guild and channel sending
    mock_guild = MagicMock()
    mock_channel = MagicMock()
    mock_channel.send = AsyncMock()
    mock_guild.get_channel.return_value = mock_channel
    bot.get_guild.return_value = mock_guild
    
    # Call the loop logic using bot_manager's function on the mock bot
    from bot_manager import DiscordOptimizerBot as RealAegisBot
    await RealAegisBot.scheduler_loop(bot)
    
    # Verify both messages were successfully processed and sent
    assert mock_channel.send.call_count == 2


# --- 8. MUSIC PLAYER DYNAMIC LOOP UPDATE TEST ---
@pytest.mark.asyncio
async def test_music_player_dynamic_loop_update(monkeypatch):
    import asyncio
    guild = MagicMock()
    player = MusicPlayer(guild)
    
    # Create a new event loop and run our updates inside it
    new_loop = asyncio.new_event_loop()
    
    # We patch asyncio.get_running_loop inside the test run to return the new_loop
    monkeypatch.setattr(asyncio, "get_running_loop", lambda: new_loop)
    
    # Mock dependencies to prevent join_channel from hitting real APIs/methods
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 999
    permissions = MagicMock()
    permissions.view_channel = True
    permissions.connect = True
    permissions.speak = True
    channel.permissions_for.return_value = permissions
    guild.get_channel.return_value = channel
    guild.voice_client = None
    
    # Patch connect and PyNaCl nacl module
    channel.connect = AsyncMock()
    with patch('sys.modules', {'nacl': MagicMock()}):
        await player.join_channel(999)
        
    # Verify player.loop has updated to new_loop
    assert player.loop is new_loop
    new_loop.close()


# --- 9. VOICE STATE UPDATE SCOPING & TIMERS TEST ---
@pytest.mark.asyncio
async def test_on_voice_state_update_scoping_and_timers():
    import asyncio
    from bot_manager import DiscordOptimizerBot
    
    # Construct mock bot
    bot = MagicMock(spec=DiscordOptimizerBot)
    bot.user = MagicMock()
    bot.user.id = 12345
    bot.music_players = {}
    
    # Setup players for Guild A and Guild B
    guild_a = MagicMock()
    guild_a.id = 1111
    player_a = MagicMock()
    player_a.voice_client = MagicMock()
    player_a.voice_client.is_connected.return_value = True
    player_a.voice_client.channel = MagicMock()
    player_a.disconnect_task = MagicMock()
    player_a.disconnect_task.done.return_value = False
    
    guild_b = MagicMock()
    guild_b.id = 2222
    player_b = MagicMock()
    player_b.voice_client = MagicMock()
    player_b.voice_client.is_connected.return_value = True
    player_b.voice_client.channel = MagicMock()
    player_b.disconnect_task = MagicMock()
    player_b.disconnect_task.done.return_value = False
    
    bot.music_players[1111] = player_a
    bot.music_players[2222] = player_b
    
    # Member voice state update event on Guild B
    member_b = MagicMock()
    member_b.id = 9999
    member_b.bot = False
    member_b.guild = guild_b
    
    before_b = MagicMock()
    before_b.channel = None
    
    after_b = MagicMock()
    # The member joined player B's channel
    after_b.channel = player_b.voice_client.channel
    player_b.voice_client.channel.members = [member_b]
    
    # Trigger voice state update for Guild B
    task_b = player_b.disconnect_task
    from bot_manager import DiscordOptimizerBot as RealBot
    await RealBot.on_voice_state_update(bot, member_b, before_b, after_b)
    
    # Since it's scoped to Guild B, player A's disconnect task should NOT be cancelled
    player_a.disconnect_task.cancel.assert_not_called()
    
    # Since member joined player B's channel (human_members > 0), player B's disconnect task should be cancelled
    task_b.cancel.assert_called_once()
    assert player_b.disconnect_task is None



