import pytest
from unittest.mock import AsyncMock, MagicMock
import discord
import json
import re

import aegis.core.utils as utils
import aegis.bot.bot_manager as bot_manager
print("AEGIS PATH:", utils.__file__)
print("BOT_MANAGER PATH:", bot_manager.__file__)
from aegis.db.models import Base
from sqlalchemy import create_engine
import aegis.bot.leveling as leveling
import aegis.bot.leveling

class MockChannel:
    def __init__(self, name="general", id=111):
        self.name = name
        self.id = id
        self.send = AsyncMock()

class MockGuild:
    def __init__(self, id=1509050530369114162):
        self.id = id
        self.name = "Cyril's Server"
        self.owner_id = 9999
        self.member_count = 120
        self.text_channels = [
            MockChannel("welcome", 1509557921615319041),
            MockChannel("mod-logs", 1509557966792167579),
            MockChannel("general", 1508707951550922782)
        ]
        
    def get_channel(self, channel_id):
        for ch in self.text_channels:
            if ch.id == int(channel_id):
                return ch
        return None

    def get_member(self, member_id):
        m = MagicMock()
        m.id = member_id
        m.guild_permissions.manage_messages = False
        m.guild_permissions.administrator = False
        return m

class MockMessage:
    def __init__(self, content, author_id=7777, guild_id=1509050530369114162):
        self.content = content
        self.guild = MockGuild(id=guild_id)
        self.author = MagicMock()
        self.author.id = author_id
        self.author.bot = False
        self.author.mention = f"<@{author_id}>"
        self.author.name = f"User_{author_id}"
        self.channel = self.guild.text_channels[2] # general
        self.delete = AsyncMock()

@pytest.mark.asyncio
async def test_cyril_server_configurations(monkeypatch):
    """Test retrieving Cyril's server configurations correctly."""
    # Setup the mock config mimicking the actual Cyril config
    mock_config = {
        "guild_configs": {
            "1509050530369114162": {
                "welcome_settings": {
                    "enabled": True,
                    "channel_id": "1509557921615319041",
                    "channel_name": "welcome",
                    "message_title": "Welcome to Cyril's Server, {user}!",
                    "message_description": "Have fun!",
                    "embed_color": "#6366F1",
                    "auto_assign_roles": []
                },
                "automod_settings": {
                    "enabled": True,
                    "block_profanity": True,
                    "block_links": True,
                    "block_invites": True,
                    "max_mentions": 5,
                    "log_channel_id": "1509557966792167579",
                    "log_channel_name": "mod-logs",
                    "whitelisted_domains": ["github.com"],
                    "whitelisted_invites": [],
                    "profanity_words": ["badword1", "badword2"]
                },
                "ticket_settings": {
                    "enabled": True,
                    "category_name": "🎟️ SUPPORT TICKETS",
                    "staff_role_name": "Moderator",
                    "ticket_channel_id": None,
                    "panel_message_id": None
                },
                "leveling_settings": {
                    "enabled": True,
                    "xp_per_message": 20,
                    "xp_cooldown_seconds": 30,
                    "level_up_channel": "1509557921615319041",
                    "level_roles": {},
                    "ignored_channels": [],
                    "ignored_roles": []
                }
            }
        }
    }
    
    monkeypatch.setattr(utils, "load_config", lambda: mock_config)
    
    # 1. Test Welcome configuration retrieval
    welcome = utils.get_guild_welcome_settings(mock_config, "1509050530369114162")
    assert welcome["enabled"] is True
    assert welcome["channel_id"] == "1509557921615319041"
    assert "Cyril" in welcome["message_title"]
    
    # 2. Test AutoMod configuration retrieval
    automod = utils.get_guild_automod_settings(mock_config, "1509050530369114162")
    assert automod["enabled"] is True
    assert automod["block_links"] is True
    assert automod["block_invites"] is True
    assert "badword1" in automod["profanity_words"]
    
    # 3. Test Ticket settings retrieval
    tickets = utils.get_guild_ticket_settings(mock_config, "1509050530369114162")
    assert tickets["enabled"] is True
    assert tickets["category_name"] == "🎟️ SUPPORT TICKETS"
    
    # 4. Test Leveling settings retrieval
    leveling_cfg = utils.get_guild_leveling_settings(mock_config, "1509050530369114162")
    assert leveling_cfg["enabled"] is True
    assert leveling_cfg["xp_per_message"] == 20
    assert leveling_cfg["xp_cooldown_seconds"] == 30


@pytest.mark.asyncio
async def test_cyril_automod_enforcement(monkeypatch):
    """Test AutoMod enforcement blocks links/invites/profanity according to Cyril's rules."""
    bot = bot_manager.DiscordOptimizerBot(command_prefix="!", intents=discord.Intents.default())
    bot.config = {}
    bot.log_infraction = AsyncMock()
    bot.process_commands = AsyncMock()

    automod_settings = {
        "enabled": True,
        "block_profanity": True,
        "block_links": True,
        "block_invites": True,
        "max_mentions": 5,
        "log_channel_id": "1509557966792167579",
        "log_channel_name": "mod-logs",
        "whitelisted_domains": ["github.com"],
        "whitelisted_invites": [],
        "profanity_words": ["badword1", "badword2"]
    }
    
    monkeypatch.setattr(utils, "load_config", lambda: {})
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: automod_settings)

    # A: Test Link Blocking (Non-whitelisted)
    msg_link = MockMessage("Check this out: https://malicious.org/phishing")
    await bot.on_message(msg_link)
    assert msg_link.delete.called
    assert "Contains links (unauthorized)" in bot.log_infraction.call_args[0][2]
    
    msg_link.delete.reset_mock()
    bot.log_infraction.reset_mock()

    # B: Test Whitelisted Link (github.com should bypass)
    msg_whitelisted = MockMessage("Check this out: https://github.com/Cyril-47/Aegis-Suite")
    await bot.on_message(msg_whitelisted)
    assert not msg_whitelisted.delete.called

    # C: Test Invite Blocking
    msg_invite = MockMessage("Join my server: discord.gg/somesecretinvite")
    await bot.on_message(msg_invite)
    assert msg_invite.delete.called
    assert "Contains Discord invite link (unauthorized)" in bot.log_infraction.call_args[0][2]
    
    msg_invite.delete.reset_mock()
    bot.log_infraction.reset_mock()

    # D: Test Profanity Blocking
    msg_profanity = MockMessage("This message contains badword1!")
    await bot.on_message(msg_profanity)
    assert msg_profanity.delete.called
    assert "Contains blocked word: 'badword1'" in bot.log_infraction.call_args[0][2]


@pytest.mark.asyncio
async def test_cyril_leveling_system():
    """Test Leveling integration (adding XP, leveling up) for Cyril's server."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    # Backup singleton state
    old_engine = leveling.leveling_system.engine
    old_xp_data = leveling.leveling_system.xp_data.copy()
    
    try:
        leveling.leveling_system.set_engine(engine)
        leveling.leveling_system.xp_data = {}
        
        guild_id = "1509050530369114162"
        user_id = "88888"
        
        # Add initial XP
        new_lvl, leveled_up, current_xp, msg_count = leveling.leveling_system.add_xp(guild_id, user_id, 15, cooldown_seconds=0)
        assert current_xp == 15
        assert new_lvl == 0
        assert leveled_up is False
        
        # Add enough XP to level up
        # Lvl 1 is at 100 XP (floor(sqrt(100/100)) = 1)
        new_lvl, leveled_up, current_xp, msg_count = leveling.leveling_system.add_xp(guild_id, user_id, 90, cooldown_seconds=0)
        assert current_xp == 105
        assert new_lvl == 1
        assert leveled_up is True
        
        # Persist and reload
        leveling.leveling_system.save()
        leveling.leveling_system.xp_data = {}
        leveling.leveling_system.load()
        
        rank = leveling.leveling_system.get_user_rank(guild_id, user_id)
        assert rank["xp"] == 105
        assert rank["level"] == 1
        
    finally:
        leveling.leveling_system.engine = old_engine
        leveling.leveling_system.xp_data = old_xp_data


@pytest.mark.asyncio
async def test_cyril_auto_responders(monkeypatch):
    """Test auto responder actions for Cyril's server (exact, contains, regex)."""
    bot = bot_manager.DiscordOptimizerBot(command_prefix="!", intents=discord.Intents.default())
    bot.config = {
        "auto_responders": [
            {
                "id": "trigger_e70d05f8",
                "guild_id": "1509050530369114162",
                "trigger_type": "exact",
                "trigger": "Miga",
                "response": "What's up Miga!",
                "enabled": True,
                "channels": [],
                "roles": []
            },
            {
                "id": "trigger_81b7a950",
                "guild_id": "1509050530369114162",
                "trigger_type": "contains",
                "trigger": "Miga",
                "response": "Mi good Boii",
                "enabled": True,
                "channels": [],
                "roles": []
            },
            {
                "id": "trigger_5f08cf93",
                "guild_id": "1509050530369114162",
                "trigger_type": "regex",
                "trigger": "@Cyril",
                "response": "@GUN What's up mi Miga",
                "enabled": True,
                "channels": [],
                "roles": []
            }
        ]
    }
    monkeypatch.setattr(utils, "load_config", lambda: bot.config)
    bot.process_commands = AsyncMock()
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: {"enabled": False})
    monkeypatch.setattr(utils, "get_guild_leveling_settings", lambda config, guild_id: {"enabled": False})

    # Exact trigger check
    msg_exact = MockMessage("Miga")
    await bot.on_message(msg_exact)
    assert msg_exact.channel.send.called
    assert msg_exact.channel.send.call_args[1].get("content") == "What's up Miga!"
    
    msg_exact.channel.send.reset_mock()

    # Contains trigger check
    msg_contains = MockMessage("hello Miga user")
    await bot.on_message(msg_contains)
    assert msg_contains.channel.send.called
    assert msg_contains.channel.send.call_args[1].get("content") == "Mi good Boii"

    msg_contains.channel.send.reset_mock()

    # Regex trigger check
    msg_regex = MockMessage("Hey @Cyril, join voice please")
    await bot.on_message(msg_regex)
    assert msg_regex.channel.send.called
    assert msg_regex.channel.send.call_args[1].get("content") == "@GUN What's up mi Miga"

@pytest.mark.asyncio
async def test_cyril_custom_commands(monkeypatch):
    """Test custom command triggers for Cyril's server."""
    bot = bot_manager.DiscordOptimizerBot(command_prefix="!", intents=discord.Intents.default())
    bot.config = {
        "guild_configs": {
            "1509050530369114162": {
                "custom_commands": {
                    "!website": "Visit our official website at https://example.com!",
                    "!rules": "Please read #rules-and-info. Be respectful and have fun!",
                    "!help": "Cyril's custom help message",
                    "!ip": "Cyril server ip is play.cyril.net"
                }
            }
        }
    }
    monkeypatch.setattr(utils, "load_config", lambda: bot.config)
    bot.process_commands = AsyncMock()
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: {"enabled": False})
    monkeypatch.setattr(utils, "get_guild_leveling_settings", lambda config, guild_id: {"enabled": False})

    # Test !website custom command trigger
    msg = MockMessage("!website")
    await bot.on_message(msg)
    assert msg.channel.send.called
    assert "Visit our official website" in msg.channel.send.call_args[0][0]

