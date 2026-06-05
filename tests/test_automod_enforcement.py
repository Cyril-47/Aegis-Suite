import pytest
from unittest.mock import AsyncMock, MagicMock
import discord

import utils
import bot_manager

# Import patterns from bot_manager
from bot_manager import DISCORD_INVITE_PATTERN, URL_DOMAIN_PATTERN

class MockChannel:
    def __init__(self, name="general", id=111):
        self.name = name
        self.id = id
        self.send = AsyncMock()

class MockGuild:
    def __init__(self, id=222):
        self.id = id
        self.name = "Mock Guild"
        self.owner_id = 999
        self.text_channels = [MockChannel("general", 111), MockChannel("mod-logs", 999)]
        
    def get_channel(self, channel_id):
        for ch in self.text_channels:
            if ch.id == channel_id:
                return ch
        return None

    def get_member(self, member_id):
        m = MagicMock()
        m.id = member_id
        m.guild_permissions.manage_messages = False
        m.guild_permissions.administrator = False
        return m

class MockMessage:
    def __init__(self, content, author_id=777):
        self.content = content
        self.guild = MockGuild()
        self.author = MagicMock()
        self.author.id = author_id
        self.author.bot = False
        self.author.mention = f"<@{author_id}>"
        self.author.name = f"User_{author_id}"
        self.channel = self.guild.text_channels[0]
        self.delete = AsyncMock()

@pytest.mark.asyncio
async def test_automod_regex_patterns():
    # Verify invite pattern
    assert DISCORD_INVITE_PATTERN.findall("Join discord.gg/abc") == ["abc"]
    assert DISCORD_INVITE_PATTERN.findall("Click here: https://discord.com/invite/xyz-123 now") == ["xyz-123"]
    assert DISCORD_INVITE_PATTERN.findall("discordapp.com/invite/code") == ["code"]
    
    # Verify url domain pattern
    assert URL_DOMAIN_PATTERN.findall("Go to https://google.com") == ["google.com"]
    assert URL_DOMAIN_PATTERN.findall("Check this: sub.example.org/page?query=1") == ["sub.example.org"]
    assert URL_DOMAIN_PATTERN.findall("www.test.co.uk") == ["test.co.uk"]

@pytest.mark.asyncio
async def test_automod_links_and_invites_blocking(monkeypatch):
    bot = bot_manager.DiscordOptimizerBot(command_prefix="!", intents=discord.Intents.default())
    bot.config = {}
    bot.log_infraction = AsyncMock()
    bot.process_commands = AsyncMock()

    # Configure automod to block both links and invites
    automod_settings = {
        "enabled": True,
        "block_profanity": False,
        "block_links": True,
        "block_invites": True,
        "max_mentions": 10,
        "profanity_words": [],
        "whitelisted_domains": ["google.com", "github.com"],
        "whitelisted_invites": ["aegis-dev"]
    }
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: automod_settings)
    monkeypatch.setattr(utils, "load_config", lambda: {})

    # Scenario A: Whitelisted domain link -> Should NOT block
    msg_whitelisted_link = MockMessage("Check out https://google.com/search")
    await bot.on_message(msg_whitelisted_link)
    assert not msg_whitelisted_link.delete.called

    # Scenario B: Subdomain of whitelisted domain -> Should NOT block
    msg_subdomain_link = MockMessage("Go to sub.github.com")
    await bot.on_message(msg_subdomain_link)
    assert not msg_subdomain_link.delete.called

    # Scenario C: Non-whitelisted link -> Should block
    msg_blocked_link = MockMessage("Click https://malicious.site/phishing")
    await bot.on_message(msg_blocked_link)
    assert msg_blocked_link.delete.called
    assert "Contains links (unauthorized)" in bot.log_infraction.call_args[0][2]

    # Reset mock
    bot.log_infraction.reset_mock()

    # Scenario D: Whitelisted invite -> Should NOT block
    msg_whitelisted_invite = MockMessage("Join our discord.gg/aegis-dev server")
    await bot.on_message(msg_whitelisted_invite)
    assert not msg_whitelisted_invite.delete.called

    # Scenario E: Blocked invite -> Should block
    msg_blocked_invite = MockMessage("Join discord.gg/malicious-server")
    await bot.on_message(msg_blocked_invite)
    assert msg_blocked_invite.delete.called
    assert "Contains Discord invite link (unauthorized)" in bot.log_infraction.call_args[0][2]

@pytest.mark.asyncio
async def test_automod_staff_bypass(monkeypatch):
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
        "profanity_words": ["badword"]
    }
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: automod_settings)

    # Mock get_member to return administrator/moderator
    def mock_get_member_staff(member_id):
        m = MagicMock()
        m.id = member_id
        m.guild_permissions.administrator = True
        m.guild_permissions.manage_messages = True
        return m

    # Scenario A: Administrator post link and blocked word -> Should NOT block
    msg_staff = MockMessage("Check out https://blocked.com containing badword")
    msg_staff.guild.get_member = mock_get_member_staff
    await bot.on_message(msg_staff)
    assert not msg_staff.delete.called

    # Scenario B: Guild Owner post -> Should NOT block
    msg_owner = MockMessage("Join discord.gg/invalid", author_id=999) # 999 is guild owner_id
    await bot.on_message(msg_owner)
    assert not msg_owner.delete.called

@pytest.mark.asyncio
async def test_automod_deduplication(monkeypatch):
    bot = bot_manager.DiscordOptimizerBot(command_prefix="!", intents=discord.Intents.default())
    bot.config = {}
    bot.log_infraction = AsyncMock()
    bot.process_commands = AsyncMock()

    automod_settings = {
        "enabled": True,
        "block_profanity": True,
        "block_links": True,
        "block_invites": True,
        "max_mentions": 2,
        "profanity_words": ["badword"]
    }
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: automod_settings)
    monkeypatch.setattr(utils, "load_config", lambda: {})

    # Scenario: Message containing links, invites, blocked words, and mention spam
    msg = MockMessage("badword and link: http://unauthorized.site, invite: discord.gg/other <@1> <@2> <@3>")
    await bot.on_message(msg)

    # Verify enforcement called exactly once
    assert msg.delete.call_count == 1
    # Check that infractions were batched in log_infraction reason argument
    reason = bot.log_infraction.call_args[0][2]
    assert "Contains blocked word: 'badword'" in reason
    assert "Contains Discord invite link (unauthorized)" in reason
    assert "Contains links (unauthorized)" in reason
    assert "Mention spam" in reason

@pytest.mark.asyncio
async def test_automod_logs_auto_creation(monkeypatch):
    bot = bot_manager.DiscordOptimizerBot(command_prefix="!", intents=discord.Intents.default())
    bot.config = {}
    
    automod_settings = {
        "enabled": True,
        "block_profanity": False,
        "block_links": True,
        "block_invites": True,
        "max_mentions": 10,
        "profanity_words": [],
        "log_channel_id": None,
        "log_channel_name": "automod-logs"
    }
    
    guild_config = {
        "automod_settings": automod_settings.copy()
    }
    
    monkeypatch.setattr(utils, "load_config", lambda: {})
    monkeypatch.setattr(utils, "get_guild_automod_settings", lambda config, guild_id: automod_settings)
    monkeypatch.setattr(utils, "get_guild_config", lambda guild_id: guild_config)
    
    saved_guild_config = []
    def mock_save_guild_config(guild_id, conf):
        saved_guild_config.append((guild_id, conf))
    monkeypatch.setattr(utils, "save_guild_config", mock_save_guild_config)
    
    created_channel = MagicMock(spec=discord.TextChannel)
    created_channel.id = 987654
    created_channel.name = "automod-logs"
    created_channel.send = AsyncMock()
    
    guild = MagicMock(spec=discord.Guild)
    guild.id = 12345
    guild.get_channel.return_value = None
    guild.text_channels = []
    guild.me.guild_permissions.manage_channels = True
    
    admin_role = MagicMock(spec=discord.Role)
    admin_role.name = "Admin"
    mod_role = MagicMock(spec=discord.Role)
    mod_role.name = "Moderator"
    guild.roles = [admin_role, mod_role]
    
    guild.create_text_channel = AsyncMock(return_value=created_channel)
    
    user = MagicMock(spec=discord.Member)
    user.mention = "<@777>"
    user.name = "testuser"
    user.id = 777
    
    await bot.log_infraction(guild, user, "Reason details", "message content", "general")
    
    assert guild.create_text_channel.called
    args, kwargs = guild.create_text_channel.call_args
    assert kwargs.get("name") == "automod-logs"
    assert kwargs.get("reason") == "Auto-created default AutoMod infraction log channel"
    
    overwrites = kwargs.get("overwrites")
    assert overwrites is not None
    assert overwrites[guild.default_role].view_channel is False
    assert overwrites[admin_role].view_channel is True
    assert overwrites[mod_role].view_channel is True
    
    assert created_channel.send.called
    send_embed = created_channel.send.call_args[1].get("embed")
    assert send_embed is not None
    assert send_embed.title == "🛡️ AutoMod Infraction Logged"
    
    assert len(saved_guild_config) == 1
    assert saved_guild_config[0][0] == "12345"
    assert saved_guild_config[0][1]["automod_settings"]["log_channel_id"] == "987654"
    assert saved_guild_config[0][1]["automod_settings"]["log_channel_name"] == "automod-logs"

