import pytest
from hypothesis import settings

# ⚠️ HYPOTHESIS + FIXTURE FOOTGUN WARNING:
# Property tests (using Hypothesis @given) must NOT consume function-scoped fixtures
# like `paths_tmp`. Hypothesis reuses the single fixture instance across all generated
# examples, causing state bleed. Property tests should build their own `Paths` instance
# using `tmp_path_factory.mktemp(...)` or a stateless approach per test case.

settings.register_profile("default", max_examples=200)
settings.load_profile("default")


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
    from aegis.core.app_core import _active_cores
    import asyncio
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


@pytest.fixture(autouse=True)
def clean_env():
    """Ensure that environment variables like DISCORD_BOT_TOKEN and ADMIN_PASSWORD_HASH
    are cleanly restored after each test, preventing state bleed.
    """
    import os
    orig_token = os.environ.get("DISCORD_BOT_TOKEN")
    orig_pass = os.environ.get("ADMIN_PASSWORD_HASH")
    yield
    if orig_token is not None:
        os.environ["DISCORD_BOT_TOKEN"] = orig_token
    elif "DISCORD_BOT_TOKEN" in os.environ:
        del os.environ["DISCORD_BOT_TOKEN"]

    if orig_pass is not None:
        os.environ["ADMIN_PASSWORD_HASH"] = orig_pass
    elif "ADMIN_PASSWORD_HASH" in os.environ:
        del os.environ["ADMIN_PASSWORD_HASH"]



# Create mock web_server module is no longer needed since legacy tests are modernized
