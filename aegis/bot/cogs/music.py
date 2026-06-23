"""
Music Cog - Handles music player functionality.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
import random
from typing import Optional
from aegis.core.permissions.registry import CommandRegistry
from aegis.bot.music_permissions import music_permission_gate

logger = logging.getLogger("aegis.bot.music")


class MusicCog(commands.Cog, name="Music"):
    """Music player commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="play", description="Plays a song from YouTube URL or search query.")
    @app_commands.describe(query="Song URL or YouTube search keywords")
    @music_permission_gate(CommandRegistry.MUSIC_PLAY)
    async def play_command(self, ctx: commands.Context, query: str):
        """Play a song from YouTube."""
        await ctx.defer()
        if not ctx.author.voice:
            await ctx.send("❌ You must be in a voice channel to use this command.")
            return
            
        player = self.bot.get_music_player(ctx.guild.id)
        if not player:
            await ctx.send("❌ Failed to initialize music player.")
            return
            
        try:
            if not player.voice_client or not player.voice_client.is_connected():
                await player.join_channel(ctx.author.voice.channel.id)
                
            player.last_text_channel = ctx.channel
            song = await player.add_to_queue(query, requester_id=ctx.author.id)
            if isinstance(song, dict) and song.get('playlist'):
                msg = f"➕ Added **{song['title']}** ({song['count']} tracks) to the queue!"
                if song.get('limit_reached'):
                    msg += f" (Capped at limit. Skipped {song['skipped']} tracks)"
                await ctx.send(msg)
            else:
                await ctx.send(f"➕ Added **{song['title']}** to the queue!")
        except RuntimeError as e:
            await ctx.send(f"❌ {e}")
        except Exception as e:
            logger.error(f"Music play error: {e}")
            await ctx.send("❌ Failed to play song. Check that FFmpeg is installed and the URL is valid.")

    @commands.hybrid_command(name="pause", description="Pauses current playback.")
    @music_permission_gate(CommandRegistry.MUSIC_PAUSE)
    async def pause_command(self, ctx: commands.Context):
        """Pause the current playback."""
        player = self.bot.get_music_player(ctx.guild.id)
        if player and player.pause():
            await ctx.send("⏸️ Paused playback.")
        else:
            await ctx.send("❌ Music is not playing or already paused.")

    @commands.hybrid_command(name="resume", description="Resumes current playback.")
    @music_permission_gate(CommandRegistry.MUSIC_RESUME)
    async def resume_command(self, ctx: commands.Context):
        """Resume current playback."""
        player = self.bot.get_music_player(ctx.guild.id)
        if player and player.resume():
            await ctx.send("▶️ Resumed playback.")
        else:
            await ctx.send("❌ Playback is not paused.")

    @commands.hybrid_command(name="skip", description="Skips the current song.")
    @music_permission_gate(CommandRegistry.MUSIC_SKIP)
    async def skip_command(self, ctx: commands.Context):
        """Skip the current song."""
        player = self.bot.get_music_player(ctx.guild.id)
        if player and player.skip():
            await ctx.send("⏭️ Skipped current song.")
        else:
            await ctx.send("❌ Nothing is playing.")

    @commands.hybrid_command(name="stop", description="Stops music and clears queue.")
    @music_permission_gate(CommandRegistry.MUSIC_STOP)
    async def stop_command(self, ctx: commands.Context):
        """Stop music and clear queue."""
        player = self.bot.get_music_player(ctx.guild.id)
        if player and player.stop():
            await ctx.send("⏹️ Playback stopped and queue cleared.")
        else:
            await ctx.send("❌ Nothing is playing.")

    @commands.hybrid_command(name="queue", description="Shows the current music queue.")
    @music_permission_gate(CommandRegistry.MUSIC_QUEUE)
    async def queue_command(self, ctx: commands.Context):
        """Show the current music queue."""
        player = self.bot.get_music_player(ctx.guild.id)
        if not player or (not player.current and len(player.queue) == 0):
            await ctx.send("📭 The queue is empty.")
            return
            
        embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blurple())
        if player.current:
            embed.description = f"**Now Playing:** {player.current['title']}\n\n"
        else:
            embed.description = ""
            
        if len(player.queue) > 0:
            queue_list = []
            for idx, song in enumerate(player.queue[:10]):
                queue_list.append(f"`{idx+1}.` {song['title']}")
            if len(player.queue) > 10:
                queue_list.append(f"...and {len(player.queue) - 10} more songs.")
            embed.add_field(name="Upcoming:", value="\n".join(queue_list), inline=False)
        else:
            embed.add_field(name="Upcoming:", value="No songs in queue.", inline=False)
            
        await ctx.send(embed=embed)

    @commands.hybrid_command(name="volume", description="Adjusts player volume.")
    @app_commands.describe(level="Volume level from 0 to 100")
    @music_permission_gate(CommandRegistry.MUSIC_VOLUME)
    async def volume_command(self, ctx: commands.Context, level: int):
        """Adjust player volume."""
        if level < 0 or level > 100:
            await ctx.send("❌ Volume must be between 0 and 100.")
            return
        player = self.bot.get_music_player(ctx.guild.id)
        if player:
            vol = player.set_volume(level / 100.0)
            await ctx.send(f"🔊 Volume set to **{int(vol * 100)}%**")
        else:
            await ctx.send("❌ Music player is not active.")

    @commands.hybrid_command(name="nowplaying", description="Shows details of the now playing song.")
    @music_permission_gate(CommandRegistry.MUSIC_NOWPLAYING)
    async def nowplaying_command(self, ctx: commands.Context):
        """Show details of the now playing song."""
        player = self.bot.get_music_player(ctx.guild.id)
        if player and player.current:
            song = player.current
            embed = discord.Embed(title="📻 Now Playing", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.green())
            if song.get("thumbnail"):
                embed.set_thumbnail(url=song["thumbnail"])
            duration_str = f"{song['duration'] // 60}:{song['duration'] % 60:02d}" if song.get("duration") else "Live Stream"
            embed.add_field(name="Duration", value=duration_str, inline=True)
            embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Nothing is playing.")

    @commands.hybrid_command(name="shuffle", description="Shuffles the queue.")
    @music_permission_gate(CommandRegistry.MUSIC_SHUFFLE)
    async def shuffle_command(self, ctx: commands.Context):
        """Shuffle the current queue."""
        player = self.bot.get_music_player(ctx.guild.id)
        if player and len(player.queue) > 1:
            random.shuffle(player.queue)
            await ctx.send("🔀 Shuffled the queue.")
        else:
            await ctx.send("❌ Queue has fewer than 2 songs to shuffle.")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(MusicCog(bot))
