import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import discord
from aegis.bot.music import MusicPlayer
from aegis.bot.cogs.music import MusicCog
from aegis.web.routes.dashboard import MusicPlayRequest

@pytest.mark.asyncio
async def test_join_channel_string_id_conversion():
    guild = MagicMock()
    guild.voice_client = None
    
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 123456789
    channel.name = "General VC"
    permissions = MagicMock()
    permissions.view_channel = True
    permissions.connect = True
    channel.permissions_for.return_value = permissions
    
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = True
    channel.connect = AsyncMock(return_value=vc)
    guild.get_channel.return_value = channel
    
    player = MusicPlayer(guild)
    
    with patch("sys.modules", {"nacl": MagicMock()}):
        # Call join_channel with a string ID (as passed by HTTP API)
        res = await player.join_channel("123456789")
        guild.get_channel.assert_called_with(123456789)
        channel.connect.assert_called_once()
        assert res == vc
        await player.leave_channel()

@pytest.mark.asyncio
async def test_join_channel_stage_channel_support():
    guild = MagicMock()
    guild.voice_client = None
    
    stage = MagicMock(spec=discord.StageChannel)
    stage.id = 987654321
    stage.name = "Stage VC"
    permissions = MagicMock()
    permissions.view_channel = True
    permissions.connect = True
    stage.permissions_for.return_value = permissions
    
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = True
    stage.connect = AsyncMock(return_value=vc)
    guild.get_channel.return_value = stage
    
    player = MusicPlayer(guild)
    
    with patch("sys.modules", {"nacl": MagicMock()}):
        res = await player.join_channel(987654321)
        assert res == vc
        await player.leave_channel()

@pytest.mark.asyncio
async def test_join_channel_missing_connect_permission():
    guild = MagicMock()
    guild.voice_client = None
    
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 12345
    channel.name = "Restricted VC"
    permissions = MagicMock()
    permissions.view_channel = True
    permissions.connect = False
    channel.permissions_for.return_value = permissions
    guild.get_channel.return_value = channel
    guild.me.guild_permissions.administrator = False
    
    player = MusicPlayer(guild)
    
    with patch("sys.modules", {"nacl": MagicMock()}):
        with pytest.raises(ValueError, match="Connect permission"):
            await player.join_channel(12345)

@pytest.mark.asyncio
async def test_leave_channel_disconnects_and_resets_state():
    guild = MagicMock()
    vc = MagicMock(spec=discord.VoiceClient)
    vc.disconnect = AsyncMock()
    guild.voice_client = vc
    guild.change_voice_state = AsyncMock()
    
    player = MusicPlayer(guild)
    player.voice_client = vc
    player.queue = [{"title": "Song 1"}]
    player.current = {"title": "Now Playing"}
    
    await player.leave_channel()
    
    vc.disconnect.assert_called_once_with(force=True)
    guild.change_voice_state.assert_called_once_with(channel=None)
    assert player.voice_client is None
    assert len(player.queue) == 0
    assert player.current is None

def test_music_play_request_accepts_channel_id():
    req = MusicPlayRequest(query="https://youtube.com/watch?v=123", channel_id="45678")
    assert req.query == "https://youtube.com/watch?v=123"
    assert req.channel_id == "45678"

@pytest.mark.asyncio
async def test_music_cog_join_and_leave_commands():
    bot = MagicMock()
    cog = MusicCog(bot)
    
    # Test join command
    ctx = MagicMock()
    ctx.guild.id = 111
    ctx.channel = MagicMock()
    ctx.send = AsyncMock()
    voice_ch = MagicMock(spec=discord.VoiceChannel)
    voice_ch.id = 222
    voice_ch.name = "Ch-222"
    ctx.author.voice.channel = voice_ch
    
    player = MagicMock()
    player.join_channel = AsyncMock()
    player.leave_channel = AsyncMock()
    player.voice_client = MagicMock()
    bot.get_music_player.return_value = player
    
    # Invoke join
    await cog.join_command.callback(cog, ctx, channel=None)
    player.join_channel.assert_called_once_with(222)
    assert "Joined **Ch-222**" in ctx.send.call_args[0][0]
    
    # Invoke leave
    await cog.leave_command.callback(cog, ctx)
    player.leave_channel.assert_called_once()
    assert "Disconnected" in ctx.send.call_args[0][0]
