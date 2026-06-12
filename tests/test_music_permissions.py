import pytest
from unittest.mock import MagicMock
import discord
from discord.ext import commands
from aegis.bot.music_permissions import check_music_permission
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
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    # Mock voice channel and connection state for author
    author_voice = MagicMock()
    author_voice.channel = MagicMock()
    author_voice.channel.id = 777777
    ctx.author.voice = author_voice
    
    # Mock voice client with exactly one human (the caller) and one bot
    voice_client = MagicMock()
    voice_client.channel = MagicMock()
    voice_client.channel.id = 777777
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
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    # Mock voice channel and connection state for author
    author_voice = MagicMock()
    author_voice.channel = MagicMock()
    author_voice.channel.id = 777777
    ctx.author.voice = author_voice
    
    # Mock voice client with multiple humans
    voice_client = MagicMock()
    voice_client.channel = MagicMock()
    voice_client.channel.id = 777777
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
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
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

@pytest.mark.asyncio
async def test_music_vc_mismatch_and_admin_bypass():
    """Verify that VC mismatch blocks control commands for normal users, but admins/owners bypass it."""
    # Scenario A: User is not in a voice channel
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.author.voice = None
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is False

    # Scenario B: User is in a different channel than the bot
    author_voice = MagicMock()
    author_voice.channel = MagicMock()
    author_voice.channel.id = 888888  # Different channel
    ctx.author.voice = author_voice
    
    voice_client = MagicMock()
    voice_client.channel = MagicMock()
    voice_client.channel.id = 777777  # Bot is in 777777
    ctx.guild.voice_client = voice_client
    
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is False

    # Scenario C: Owner bypasses mismatch
    ctx.author.id = ctx.guild.owner_id  # Set caller as owner
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is True

@pytest.mark.asyncio
async def test_music_bot_owner_bypass():
    """Verify that the Bot Owner bypasses VC checks for music controls."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 777777 # Bot owner
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.bot = MagicMock()
    ctx.bot.owner_id = 777777 # Match author
    
    ctx.author.voice = None
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is True

@pytest.mark.asyncio
async def test_music_discord_admin_bypass():
    """Verify that Discord Administrators bypass VC checks for music controls."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = True # Discord admin
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    ctx.author.voice = None
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is True

@pytest.mark.asyncio
async def test_music_configured_moderator_bypass(monkeypatch):
    """Verify that configured Admin/Moderator roles bypass VC checks."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    
    role_mock = MagicMock()
    role_mock.id = 555555 # Configured mod role
    ctx.author.roles = [role_mock]
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    config_data = {
        "guild_configs": {
            "123456": {
                "permission_roles": {
                    "admin_role_id": "444444",
                    "moderator_role_id": "555555"
                }
            }
        }
    }
    import aegis.core.utils as utils
    monkeypatch.setattr(utils, "load_config", lambda: config_data)
    
    ctx.author.voice = None
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is True

@pytest.mark.asyncio
async def test_music_track_requester_bypass():
    """Verify that the track requester can control playback even if other humans are in VC."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111 # Requester
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    author_voice = MagicMock()
    author_voice.channel = MagicMock()
    author_voice.channel.id = 777777
    ctx.author.voice = author_voice
    
    voice_client = MagicMock()
    voice_client.channel = MagicMock()
    voice_client.channel.id = 777777
    ctx.guild.voice_client = voice_client
    
    other_member = MagicMock()
    other_member.id = 222222
    other_member.bot = False
    voice_client.channel.members = [ctx.author, other_member]
    
    player = MagicMock()
    player.current = {"title": "Test Track", "requester_id": 111111}
    ctx.bot.get_music_player = MagicMock(return_value=player)
    
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is True

@pytest.mark.asyncio
async def test_music_regular_user_denied(monkeypatch):
    """Verify that a normal user who is not alone and not the requester is denied access."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.owner_id = 999999
    ctx.author = MagicMock()
    ctx.author.id = 111111
    ctx.author.roles = []
    ctx.author.guild_permissions = MagicMock()
    ctx.author.guild_permissions.administrator = False
    ctx.bot = MagicMock()
    ctx.bot.owner_id = None
    
    author_voice = MagicMock()
    author_voice.channel = MagicMock()
    author_voice.channel.id = 777777
    ctx.author.voice = author_voice
    
    voice_client = MagicMock()
    voice_client.channel = MagicMock()
    voice_client.channel.id = 777777
    ctx.guild.voice_client = voice_client
    
    other_member = MagicMock()
    other_member.id = 222222
    other_member.bot = False
    voice_client.channel.members = [ctx.author, other_member]
    
    player = MagicMock()
    player.current = {"title": "Test Track", "requester_id": 999999} # Different requester
    ctx.bot.get_music_player = MagicMock(return_value=player)
    
    async def mock_has_permission(*args, **kwargs):
        return False
    monkeypatch.setattr(PermissionResolver, "has_permission", mock_has_permission)
    
    assert await check_music_permission(ctx, CommandRegistry.MUSIC_PAUSE) is False

@pytest.mark.asyncio
async def test_linkdashboard_prefix_dm_success(monkeypatch):
    """Verify that !linkdashboard DM delivery works and code is not exposed in public channel."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.name = "Test Guild"
    ctx.interaction = None # Prefix execution
    ctx.author = MagicMock()
    ctx.author.id = 111111
    
    dm_sent = []
    async def mock_send(embed):
        dm_sent.append(embed)
    ctx.author.send = mock_send
    
    ctx_sent = []
    async def mock_ctx_send(content, **kwargs):
        ctx_sent.append(content)
    ctx.send = mock_ctx_send
    
    import aegis.core.utils as bot_utils
    monkeypatch.setattr(bot_utils, "can_generate_code", lambda guild_id: True)
    
    config_data = {}
    def mock_load_config():
        return config_data
    def mock_save_config(cfg):
        nonlocal config_data
        config_data = cfg
    monkeypatch.setattr(bot_utils, "load_config", mock_load_config)
    monkeypatch.setattr(bot_utils, "save_config", mock_save_config)
    
    bot = MagicMock()
    registered_cmds = {}
    def mock_hybrid_command(name, **kwargs):
        def decorator(func):
            registered_cmds[name] = func
            return func
        return decorator
    bot.hybrid_command = mock_hybrid_command
    
    from aegis.bot.commands import register_commands
    register_commands(bot)
    
    link_cmd = registered_cmds["linkdashboard"]
    await link_cmd(ctx)
    
    assert len(dm_sent) == 1
    assert "I've sent your dashboard connection code via DM." in ctx_sent[0]
    
    # Connection code must not be exposed in channel response
    pending = config_data.get("pending_pairings", {})
    assert len(pending) == 1
    code = list(pending.keys())[0]
    assert code not in ctx_sent[0]

@pytest.mark.asyncio
async def test_linkdashboard_prefix_dm_failure(monkeypatch):
    """Verify linkdashboard prefix execution when user DMs are closed."""
    ctx = MagicMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.name = "Test Guild"
    ctx.interaction = None
    ctx.author = MagicMock()
    ctx.author.id = 111111
    
    mock_response = MagicMock()
    mock_response.status = 403
    mock_response.reason = "Forbidden"
    async def mock_send(embed):
        raise discord.Forbidden(mock_response, "Cannot send DM")
    ctx.author.send = mock_send
    
    ctx_sent = []
    async def mock_ctx_send(content, **kwargs):
        ctx_sent.append(content)
    ctx.send = mock_ctx_send
    
    import aegis.core.utils as bot_utils
    monkeypatch.setattr(bot_utils, "can_generate_code", lambda guild_id: True)
    
    config_data = {}
    def mock_load_config():
        return config_data
    def mock_save_config(cfg):
        nonlocal config_data
        config_data = cfg
    monkeypatch.setattr(bot_utils, "load_config", mock_load_config)
    monkeypatch.setattr(bot_utils, "save_config", mock_save_config)
    
    bot = MagicMock()
    registered_cmds = {}
    def mock_hybrid_command(name, **kwargs):
        def decorator(func):
            registered_cmds[name] = func
            return func
        return decorator
    bot.hybrid_command = mock_hybrid_command
    
    from aegis.bot.commands import register_commands
    register_commands(bot)
    
    link_cmd = registered_cmds["linkdashboard"]
    await link_cmd(ctx)
    
    assert "I couldn't send you a DM." in ctx_sent[0]
    assert "Please enable Direct Messages and try again." in ctx_sent[0]
    assert not config_data.get("pending_pairings")
