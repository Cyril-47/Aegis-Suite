import pytest
import aegis.core.utils as utils
from aegis.core.permissions.resolver import PermissionResolver
from aegis.core.permissions.registry import CommandRegistry

@pytest.fixture(autouse=True)
def mock_config(monkeypatch):
    # Mock utils.load_config to return a clean configuration structure
    fake_config = {
        "guild_configs": {
            "123456": {
                "permission_roles": {
                    "admin_role_id": "999",
                    "moderator_role_id": "888"
                },
                "command_permissions": {
                    CommandRegistry.MUSIC_PLAY: {
                        "mode": "everyone"
                    },
                    CommandRegistry.MUSIC_STOP: {
                        "mode": "moderator"
                    },
                    CommandRegistry.OPTIMIZE_SERVER: {
                        "mode": "admin"
                    },
                    CommandRegistry.GIVEAWAY_CREATE: {
                        "mode": "roles",
                        "role_ids": ["777", "666"]
                    },
                    CommandRegistry.TICKET_CLOSE: {
                        "mode": "role",
                        "role_id": "555"
                    },
                    CommandRegistry.UNLINK: {
                        "mode": "owner"
                    }
                }
            }
        }
    }
    monkeypatch.setattr(utils, "load_config", lambda: fake_config)

@pytest.mark.asyncio
async def test_owner_and_admin_bypasses():
    # Owner always passes
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="111",
        command_name=CommandRegistry.UNLINK,
        user_roles=[],
        is_owner=True
    ) is True

    # Discord Admin always passes
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="222",
        command_name=CommandRegistry.UNLINK,
        user_roles=[],
        has_discord_admin=True
    ) is True

@pytest.mark.asyncio
async def test_everyone_mode():
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.MUSIC_PLAY,
        user_roles=[]
    ) is True

@pytest.mark.asyncio
async def test_moderator_mode():
    # Moderator passes
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.MUSIC_STOP,
        user_roles=["888"]
    ) is True

    # Admin inherits Moderator and passes
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.MUSIC_STOP,
        user_roles=["999"]
    ) is True

    # Normal user fails
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.MUSIC_STOP,
        user_roles=["111"]
    ) is False

@pytest.mark.asyncio
async def test_admin_mode():
    # Admin passes
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.OPTIMIZE_SERVER,
        user_roles=["999"]
    ) is True

    # Moderator fails
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.OPTIMIZE_SERVER,
        user_roles=["888"]
    ) is False

@pytest.mark.asyncio
async def test_specific_role_mode():
    # Has role
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.TICKET_CLOSE,
        user_roles=["555"]
    ) is True

    # Lacks role
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.TICKET_CLOSE,
        user_roles=["111"]
    ) is False

@pytest.mark.asyncio
async def test_multiple_roles_mode():
    # Has one of the roles
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.GIVEAWAY_CREATE,
        user_roles=["666"]
    ) is True

    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.GIVEAWAY_CREATE,
        user_roles=["777"]
    ) is True

    # Lacks both roles
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.GIVEAWAY_CREATE,
        user_roles=["111"]
    ) is False

@pytest.mark.asyncio
async def test_destructive_fail_closed_unconfigured():
    # Level reset is destructive and unconfigured
    # Should require admin role or owner bypass
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.LEVEL_RESET,
        user_roles=["111"]
    ) is False

    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.LEVEL_RESET,
        user_roles=["999"]
    ) is True

@pytest.mark.asyncio
async def test_unconfigured_non_destructive_defaults_to_true():
    # Welcome set is not destructive and unconfigured
    # Should default to True (open to everyone)
    assert await PermissionResolver.has_permission(
        guild_id="123456",
        user_id="333",
        command_name=CommandRegistry.WELCOME_SET,
        user_roles=["111"]
    ) is True
