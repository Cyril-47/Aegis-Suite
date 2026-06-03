import pytest
from unittest.mock import MagicMock
from discord.ext import commands
from aegis.bot.music_permissions import check_music_permission, music_permission_gate
from aegis.bot.permissions import universal_permission_check
from aegis.core.permissions.resolver import PermissionResolver
from aegis.core.permissions.registry import CommandRegistry

@pytest.mark.asyncio
async def test_music_module_solo_vc_bypass_exactly_one_human():
    """IT-1: Music Module Solo VC Bypass (Solo scenario).
    Ensures that playback commands bypass PermissionResolver when the caller is the only human in VC.
    """
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    
    # Mock voice client with exactly one human (the caller) and one bot
    voice_client = MagicMock()
    ctx.guild.voice_client = voice_client
    
    caller_member = MagicMock()
    caller_member.id = 111111
    caller_member.bot = False
    
    bot_member = MagicMock()
    bot_member.id = 222222
    bot_member.bot = True
    
    voice_client.channel.members = [caller_member, bot_member]
    
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PLAY) is True

@pytest.mark.asyncio
async def test_music_module_solo_vc_bypass_multiple_humans(monkeypatch):
    """IT-1: Music Module Solo VC Bypass (Multi-human scenario).
    Ensures that when other humans are in VC, permissions fall back to PermissionResolver.
    """
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    
    # Mock voice client with multiple humans
    voice_client = MagicMock()
    ctx.guild.voice_client = voice_client
    
    caller_member = MagicMock()
    caller_member.id = 111111
    caller_member.bot = False
    
    other_member = MagicMock()
    other_member.id = 333333
    other_member.bot = False
    
    voice_client.channel.members = [caller_member, other_member]
    
    # Mock PermissionResolver to return False to prove it falls back
    async def mock_has_permission(*args, **kwargs):
        return False
    monkeypatch.setattr(PermissionResolver, "has_permission", mock_has_permission)
    
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PLAY) is False

@pytest.mark.asyncio
async def test_universal_decorator_gate_raises_missing_permissions(monkeypatch):
    """IT-2: Universal Decorator Gate.
    Verifies that the bot check decorator raises MissingPermissions when permission check fails.
    """
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    
    # Force PermissionResolver to return False
    async def mock_has_permission(*args, **kwargs):
        return False
    monkeypatch.setattr(PermissionResolver, "has_permission", mock_has_permission)
    
    # Instantiate the decorator check
    decorator = universal_permission_check("TEST_COMMAND")
    predicate = decorator.predicate
    
    with pytest.raises(commands.MissingPermissions) as exc_info:
        await predicate(ctx)
        
    err_str = str(exc_info.value).upper()
    assert "TEST" in err_str and "COMMAND" in err_str
