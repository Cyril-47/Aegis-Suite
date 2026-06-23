"""Tests for dynamic slowmode policy — validates bot_manager fix and tracker integration."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import discord


class MockChannel:
    def __init__(self, name="general", channel_id=111):
        self.name = name
        self.id = channel_id
        self.send = AsyncMock()
        self.slowmode_delay = 0
        self.edit = AsyncMock()

    async def edit(self, **kwargs):
        self.slowmode_delay = kwargs.get("slowmode_delay", 0)


class MockGuild:
    def __init__(self, guild_id=9999):
        self.id = guild_id
        self.name = "Test Guild"
        self.owner_id = 8888
        self.member_count = 50
        self.me = MagicMock()
        self.me.guild_permissions.manage_channels = True
        self.text_channels = [
            MockChannel("general", 111),
            MockChannel("mod-chat", 222),
        ]

    def get_member(self, member_id):
        return MagicMock()


class MockMessage:
    def __init__(self, content, author_id=7777, guild_id=9999, channel_id=111):
        self.content = content
        self.guild = MockGuild(guild_id)
        self.author = MagicMock()
        self.author.id = author_id
        self.author.bot = False
        self.author.mention = f"<@{author_id}>"
        self.author.name = f"User_{author_id}"
        self.channel = MagicMock()
        self.channel.id = channel_id
        self.channel.name = "general"
        self.delete = AsyncMock()


@pytest.fixture
def mock_config():
    return {
        "slowmode_settings": {
            "enabled": True,
            "burst_threshold": 10,
            "slowmode_duration": 5,
            "cooldown_seconds": 60,
            "whitelisted_channels": [],
        },
        "guild_configs": {},
        "auto_responders": [],
        "welcome_settings": {},
        "automod_settings": {"enabled": False},
    }


@pytest.mark.asyncio
async def test_slowmode_tracker_receives_config(mock_config):
    """Verify the slowmode block in on_message can access config without NameError."""
    with patch("aegis.bot.bot_manager.utils") as mock_utils:
        mock_utils.get_guild_slowmode_settings.return_value = mock_config["slowmode_settings"]
        mock_utils.get_guild_config.return_value = {}

        mock_utils.get_guild_slowmode_settings.return_value = mock_config["slowmode_settings"]

        from aegis.bot.bot_manager import DiscordOptimizerBot

        bot = DiscordOptimizerBot.__new__(DiscordOptimizerBot)
        bot.config = mock_config
        bot.stats = {"messages_today": 0, "commands_today": 0, "joins_today": 0}
        bot._new_members = []
        bot.process_commands = AsyncMock()
        bot.check_stats_reset = MagicMock()
        bot._recent_messages = {}
        bot._message_times = {}
        bot._user_message_counts = {}

        msg = MockMessage("hello")

        from aegis.bot.slowmode_tracker import slowmode_tracker

        with patch.object(slowmode_tracker, "record_message") as mock_record, \
             patch.object(slowmode_tracker, "check_and_apply", new_callable=AsyncMock) as mock_check:

            await bot.on_message(msg)

            mock_record.assert_called_once_with(str(msg.channel.id), str(msg.author.id))
            mock_check.assert_called_once()
            args = mock_check.call_args
            assert args[0][0] == msg.guild
            assert args[0][1].id == msg.channel.id
            assert args[0][2]["enabled"] is True


@pytest.mark.asyncio
async def test_slowmode_disabled_does_nothing(mock_config):
    """When slowmode is disabled, tracker should NOT be called at all."""
    mock_config["slowmode_settings"]["enabled"] = False

    with patch("aegis.bot.bot_manager.utils") as mock_utils:
        mock_utils.get_guild_slowmode_settings.return_value = mock_config["slowmode_settings"]
        mock_utils.get_guild_config.return_value = {}

        from aegis.bot.bot_manager import DiscordOptimizerBot

        bot = DiscordOptimizerBot.__new__(DiscordOptimizerBot)
        bot.config = mock_config
        bot.stats = {"messages_today": 0, "commands_today": 0, "joins_today": 0}
        bot._new_members = []
        bot.process_commands = AsyncMock()
        bot.check_stats_reset = MagicMock()
        bot._recent_messages = {}
        bot._message_times = {}
        bot._message_counts = {}

        msg = MockMessage("hello")

        from aegis.bot.slowmode_tracker import slowmode_tracker

        with patch.object(slowmode_tracker, "record_message") as mock_record, \
             patch.object(slowmode_tracker, "check_and_apply", new_callable=AsyncMock) as mock_check:

            await bot.on_message(msg)

            mock_record.assert_not_called()
            mock_check.assert_not_called()
