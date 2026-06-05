import pytest
import asyncio
import discord
from unittest.mock import AsyncMock, MagicMock, patch
from aegis.bot.music import MusicPlayer

@pytest.mark.asyncio
async def test_music_player_inactivity_disconnect():
    guild = MagicMock()
    guild.voice_client = None
    
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 999
    channel.name = "Voice channel"
    permissions = MagicMock()
    permissions.view_channel = True
    permissions.connect = True
    permissions.speak = True
    channel.permissions_for.return_value = permissions
    
    # Mock voice client
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = True
    vc.is_playing.return_value = False
    vc.is_paused.return_value = False
    vc.channel = channel
    
    # Alone in voice channel (only bot is present)
    bot_member = MagicMock()
    bot_member.bot = True
    channel.members = [bot_member]
    
    channel.connect = AsyncMock(return_value=vc)
    guild.get_channel.return_value = channel
    
    player = MusicPlayer(guild)
    
    # Mock leave_channel to trace when it gets called, wrapping original to ensure cleanup
    original_leave = player.leave_channel
    player.leave_channel = AsyncMock(side_effect=original_leave)
    
    # We patch asyncio.sleep to not wait, but we let it run enough times to trigger threshold
    real_sleep = asyncio.sleep
    sleep_calls = 0
    async def mock_sleep(seconds):
        nonlocal sleep_calls
        if seconds > 0:
            sleep_calls += 1
            if sleep_calls >= 65:
                # Force exit the loop
                vc.is_connected.return_value = False
        await real_sleep(0) # yield control

    with patch("sys.modules", {"nacl": MagicMock()}), \
         patch("aegis.bot.music.asyncio.sleep", side_effect=mock_sleep):
        await player.join_channel(999)
        
        # Give the background task time to run
        for _ in range(100):
            await asyncio.sleep(0)
            
        # Assert leave_channel was called because of inactivity
        player.leave_channel.assert_called_once()
