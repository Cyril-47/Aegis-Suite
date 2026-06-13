import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aegis.core.utils as utils
from aegis.core.app_core import AppCore

@pytest.mark.asyncio
async def test_giveaways_no_deadlock(paths_tmp, monkeypatch):
    # Setup isolated AppCore and path
    monkeypatch.setattr(utils, "GIVEAWAYS_PATH", str(paths_tmp.root / "giveaways.json"))
    
    # Initialize AppCore to set up the DB
    core = AppCore(paths_tmp)
    
    # Verify that calling load_giveaways under giveaways_lock does not deadlock
    try:
        async with asyncio.timeout(2.0):  # Timeout to catch deadlocks
            async with utils.giveaways_lock:
                giveaways = await utils.load_giveaways()
                assert isinstance(giveaways, dict)
                
                # Test saving as well
                await utils.save_giveaways(giveaways)
    except TimeoutError:
        pytest.fail("Giveaways operations deadlocked!")


@pytest.mark.asyncio
async def test_giveaway_audit_logging(paths_tmp, monkeypatch):
    import aegis.core.audit_log as audit_log
    
    # Mock bot object and command registration
    bot = MagicMock()
    registered_cmds = {}
    def mock_hybrid_command(name, *args, **kwargs):
        def decorator(func):
            registered_cmds[name] = func
            return func
        return decorator
    bot.hybrid_command = mock_hybrid_command
    
    # Import and register commands
    from aegis.bot.commands import register_commands
    register_commands(bot)
    
    # Setup test context and environment
    ctx = AsyncMock()
    ctx.guild = MagicMock()
    ctx.guild.id = 123456
    ctx.guild.name = "Test Guild"
    ctx.author = MagicMock()
    ctx.author.id = 78910
    ctx.author.roles = []
    ctx.channel = MagicMock()
    ctx.channel.mention = "#general"
    
    # Mock PermissionResolver to allow command execution
    from aegis.core.permissions.resolver import PermissionResolver
    monkeypatch.setattr(PermissionResolver, "has_permission", AsyncMock(return_value=True))
    
    # Mock start_giveaway_bot in bot_manager to succeed immediately
    monkeypatch.setattr("aegis.bot.bot_manager.start_giveaway_bot", AsyncMock(return_value="999999"))
    
    # Mock audit_log.log_action to verify it gets called
    logged_actions = []
    def mock_log_action(actor, category, action, target=None, details=None):
        logged_actions.append((actor, category, action, target, details))
    monkeypatch.setattr(audit_log, "log_action", mock_log_action)
    
    # Get the registered giveaway command
    giveaway_cmd = registered_cmds["giveaway"]
    
    # Run the "start" action
    await giveaway_cmd(ctx, action="start", target="10m", winners=2, prize="Beta Key", channel=None)
    
    # Verify audit log was written
    assert len(logged_actions) == 1
    actor, category, action, target, details = logged_actions[0]
    assert actor == "discord:78910"
    assert category == "GIVEAWAY_ACTION"
    assert "Started giveaway for 'Beta Key'" in action
    assert target == "123456"

    # Setup mock giveaways record for "end" action
    mock_giveaways = {
        "999999": {
            "guild_id": "123456",
            "channel_id": "888888",
            "prize": "Beta Key",
            "winners_count": 2,
            "end_time": 0.0,
            "entrants": [],
            "winners": [],
            "ended": False,
            "host_id": "78910"
        }
    }
    monkeypatch.setattr(utils, "load_giveaways", AsyncMock(return_value=mock_giveaways))
    monkeypatch.setattr(utils, "save_giveaways", AsyncMock())
    
    # Mock ch.fetch_message and bot.end_giveaway_action
    mock_ch = AsyncMock()
    ctx.guild.get_channel.return_value = mock_ch
    bot.get_guild.return_value = ctx.guild
    bot.end_giveaway_action = AsyncMock()
    
    # Run the "end" action
    logged_actions.clear()
    await giveaway_cmd(ctx, action="end", target="999999")
    
    # Verify audit log was written for "end" action
    assert len(logged_actions) == 1
    actor, category, action, target, details = logged_actions[0]
    assert actor == "discord:78910"
    assert category == "GIVEAWAY_ACTION"
    assert "Force ended giveaway 'Beta Key' early" in action
    assert target == "123456"
