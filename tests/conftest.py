"""
Pytest configuration and fixtures for Aegis Suite tests.
"""

import pytest
import asyncio
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, AsyncMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Add parent directory to path for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))





@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    
    yield engine, Session
    
    # Cleanup
    os.unlink(db_path)


@pytest.fixture
def mock_bot():
    """Create a mock Discord bot."""
    bot = MagicMock()
    bot.user = MagicMock()
    bot.user.id = 123456789
    bot.user.name = "TestBot"
    bot.guilds = []
    bot.config = {
        "guild_configs": {},
        "welcome_settings": {"enabled": False},
        "automod_settings": {"enabled": False},
    }
    bot.analytics_engine = MagicMock()
    bot.db = MagicMock()
    return bot


@pytest.fixture
def mock_guild():
    """Create a mock Discord guild."""
    guild = MagicMock()
    guild.id = 987654321
    guild.name = "Test Server"
    guild.member_count = 100
    guild.text_channels = []
    guild.voice_channels = []
    guild.categories = []
    guild.roles = []
    guild.members = []
    guild.icon = MagicMock()
    guild.icon.url = "https://example.com/icon.png"
    guild.verification_level = 0
    guild.auto_moderation_rules = []
    return guild


@pytest.fixture
def mock_member():
    """Create a mock Discord member."""
    member = MagicMock()
    member.id = 111222333
    member.name = "TestUser"
    member.display_name = "Test User"
    member.bot = False
    member.joined_at = None
    member.created_at = None
    member.roles = []
    member.guild = MagicMock()
    member.guild.id = 987654321
    member.display_avatar = MagicMock()
    member.display_avatar.url = "https://example.com/avatar.png"
    return member


@pytest.fixture
def mock_channel():
    """Create a mock Discord channel."""
    channel = MagicMock()
    channel.id = 444555666
    channel.name = "test-channel"
    channel.guild = MagicMock()
    channel.guild.id = 987654321
    return channel


@pytest.fixture
def mock_message():
    """Create a mock Discord message."""
    message = MagicMock()
    message.id = 777888999
    message.content = "Test message"
    message.author = MagicMock()
    message.author.id = 111222333
    message.author.bot = False
    message.guild = MagicMock()
    message.guild.id = 987654321
    message.channel = MagicMock()
    message.channel.id = 444555666
    message.created_at = None
    message.mentions = []
    return message


@pytest.fixture
def sample_config():
    """Sample configuration for testing."""
    return {
        "client_id": "123456789",
        "setup_complete": True,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_id": "444555666",
            "channel_name": "welcome",
            "message_title": "Welcome!",
            "message_description": "Welcome to the server!",
            "embed_color": "#10b981",
            "auto_assign_roles": []
        },
        "automod_settings": {
            "enabled": True,
            "block_profanity": True,
            "block_links": True,
            "max_mentions": 5,
            "log_channel_id": "444555666",
            "log_channel_name": "mod-log",
            "profanity_words": [],
            "block_invites": False,
            "whitelisted_domains": [],
            "whitelisted_invites": []
        },
        "guild_configs": {
            "987654321": {
                "welcome": {"enabled": True},
                "automod": {"enabled": True}
            }
        }
    }


# Restored legacy fixtures for architectural and system tests
from hypothesis import settings

try:
    settings.register_profile("default", max_examples=200)
    settings.load_profile("default")
except Exception:
    pass


@pytest.fixture
def paths_tmp(tmp_path):
    """Constructs a Paths instance under a temporary directory,
    calls ensure(), and yields the Paths instance. Overrides APPDATA resolution
    by injecting the root path directly.
    """
    from aegis.core.paths import Paths
    p = Paths(root=tmp_path / "aegis")
    p.ensure()
    return p


@pytest.fixture
def temp_appdata(tmp_path, monkeypatch):
    """Sets the APPDATA environment variable to a temporary directory."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    return tmp_path


@pytest.fixture
def mock_discord():
    """Provides a mock discord.Client login surface conforming to discord.py's API.
    Raises LoginFailure on bad token and allows checking guilds after a successful login.
    """
    import discord
    
    class MockGuild:
        def __init__(self, guild_id: int, name: str) -> None:
            self.id = guild_id
            self.name = name

    class MockDiscordClient:
        def __init__(self, *args, **kwargs) -> None:
            self.guilds = []
            self.closed = False

        async def login(self, token: str) -> None:
            if token == "bad_token":
                raise discord.errors.LoginFailure("Improper token has been passed.")
            # Simulate a valid login by populating guilds
            self.guilds = [
                MockGuild(123456789, "Test Guild 1"),
                MockGuild(987654321, "Test Guild 2")
            ]

        async def close(self) -> None:
            self.closed = True

    return MockDiscordClient


@pytest.fixture(autouse=True)
async def cleanup_active_cores():
    """Autouse fixture to cleanly cancel and await any pending tasks of AppCore instances
    created during tests, preventing task leaks when the event loop is torn down.
    """
    yield
    try:
        from aegis.core.app_core import _active_cores
        for core in list(_active_cores):
            # Cancel and await ASGI task
            if hasattr(core, "_asgi_task") and core._asgi_task and not core._asgi_task.done():
                core._asgi_task.cancel()
                try:
                    await core._asgi_task
                except (asyncio.CancelledError, Exception):
                    pass
            # Cancel and await bot task
            if hasattr(core, "_bot_task") and core._bot_task and not core._bot_task.done():
                core._bot_task.cancel()
                try:
                    await core._bot_task
                except (asyncio.CancelledError, Exception):
                    pass
        _active_cores.clear()
    except Exception:
        pass


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure that environment variables like DISCORD_BOT_TOKEN, ADMIN_PASSWORD_HASH, and JWT_SECRET
    are cleanly restored after each test, preventing state bleed.
    """
    import os
    orig_token = os.environ.get("DISCORD_BOT_TOKEN")
    orig_pass = os.environ.get("ADMIN_PASSWORD_HASH")
    orig_jwt = os.environ.get("JWT_SECRET")
    yield
    if orig_token is not None:
        os.environ["DISCORD_BOT_TOKEN"] = orig_token
    elif "DISCORD_BOT_TOKEN" in os.environ:
        del os.environ["DISCORD_BOT_TOKEN"]

    if orig_pass is not None:
        os.environ["ADMIN_PASSWORD_HASH"] = orig_pass
    elif "ADMIN_PASSWORD_HASH" in os.environ:
        del os.environ["ADMIN_PASSWORD_HASH"]

    if orig_jwt is not None:
        os.environ["JWT_SECRET"] = orig_jwt
    elif "JWT_SECRET" in os.environ:
        del os.environ["JWT_SECRET"]
