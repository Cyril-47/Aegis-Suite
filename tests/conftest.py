import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
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


# Create mock web_server module so legacy tests that import web_server still pass
import sys
from types import ModuleType

web_server_mock = ModuleType("web_server")
sys.modules["web_server"] = web_server_mock

from aegis.web.app import build_app
from aegis.config.schema import ConfigModel
from aegis.core.paths import Paths
from aegis.core.state import LifecycleStateMachine
from aegis.core.lifecycle import _bootstrap_hosting_mode_from_env

mock_core = MagicMock()
mock_core.paths = Paths()
mock_core.state = LifecycleStateMachine()
mock_core.config = None

web_server_mock.app = build_app(mock_core)
web_server_mock.ConfigModel = ConfigModel
web_server_mock._bootstrap_hosting_mode_from_env = _bootstrap_hosting_mode_from_env
