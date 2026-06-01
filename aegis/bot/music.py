import discord
import asyncio
import logging
import os

logger = logging.getLogger("aegis.bot.music")

try:
    import yt_dlp
    
    YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'noplaylist': True,
        'nocheckcertificate': True,
        'ignoreerrors': False,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'default_search': 'ytsearch',
        'source_address': '0.0.0.0'
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
except ImportError:
    yt_dlp = None
    logger.warning("yt-dlp library is missing. Music bot streaming will be unavailable.")

class MusicPlayer:
    """Manages music streaming queue and voice connection for a specific guild."""
    def __init__(self, guild: discord.Guild):
        self.guild = guild
        self.queue = []
        self.current = None
        self.voice_client = None
        self.volume = 0.5
        self.loop = asyncio.get_event_loop()

    async def join_channel(self, channel_id: int):
        """Joins a voice channel."""
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError("Target channel is not a voice channel.")
            
        try:
            import nacl
        except ImportError:
            raise RuntimeError("Voice support is disabled because PyNaCl library is not installed.")
            
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.move_to(channel)
        else:
            try:
                self.voice_client = await channel.connect()
            except Exception as e:
                logger.error(f"Failed to connect to voice channel: {e}")
                raise e
        return self.voice_client

    async def leave_channel(self):
        """Leaves voice channel and clears queue."""
        if self.voice_client and self.voice_client.is_connected():
            await self.voice_client.disconnect()
        self.voice_client = None
        self.queue = []
        self.current = None

    async def play_next(self):
        """Plays the next song in queue."""
        if len(self.queue) == 0:
            self.current = None
            return
            
        if not self.voice_client or not self.voice_client.is_connected():
            return
            
        next_song = self.queue.pop(0)
        self.current = next_song
        
        try:
            import shutil
            if not shutil.which("ffmpeg"):
                logger.error("FFmpeg not found in PATH. Playback failed.")
                return
                
            if next_song.get('webpage_url'):
                try:
                    logger.info(f"Refreshing YouTube URL for: {next_song['title']}")
                    data = await self.loop.run_in_executor(
                        None,
                        lambda: ytdl.extract_info(next_song['webpage_url'], download=False)
                    )
                    if data and data.get('url'):
                        next_song['url'] = data.get('url')
                except Exception as e:
                    logger.warning(f"Failed to refresh URL, trying original URL: {e}")

            source = discord.PCMVolumeTransformer(
                discord.FFmpegPCMAudio(next_song['url'], **FFMPEG_OPTIONS),
                volume=self.volume
            )
            
            def after_playing(error):
                if error:
                    logger.error(f"Player error: {error}")
                asyncio.run_coroutine_threadsafe(self.play_next(), self.loop)
                
            self.voice_client.play(source, after=after_playing)
        except Exception as e:
            logger.error(f"Error starting playback: {e}")

    async def add_to_queue(self, query: str) -> dict:
        """Searches YouTube and adds song to queue."""
        if not yt_dlp:
            raise RuntimeError("yt-dlp is not installed on this system.")
            
        loop = asyncio.get_event_loop()
        try:
            data = await loop.run_in_executor(
                None, 
                lambda: ytdl.extract_info(query, download=False)
            )
            
            if 'entries' in data:
                if len(data['entries']) == 0:
                    raise ValueError("No search results found.")
                song_data = data['entries'][0]
            else:
                song_data = data
                
            song_info = {
                'title': song_data.get('title', 'Unknown Title'),
                'url': song_data.get('url'),
                'webpage_url': song_data.get('webpage_url'),
                'duration': song_data.get('duration', 0),
                'thumbnail': song_data.get('thumbnail')
            }
            
            self.queue.append(song_info)
            
            if not self.voice_client or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                if self.voice_client and self.voice_client.is_connected():
                    await self.play_next()
                    
            return song_info
        except Exception as e:
            logger.error(f"Search failed for query '{query}': {e}")
            raise e

    def pause(self):
        if self.voice_client and self.voice_client.is_playing():
            self.voice_client.pause()
            return True
        return False

    def resume(self):
        if self.voice_client and self.voice_client.is_paused():
            self.voice_client.resume()
            return True
        return False

    def skip(self):
        if self.voice_client and self.voice_client.is_connected():
            if self.voice_client.is_playing() or self.voice_client.is_paused():
                self.voice_client.stop()
                return True
        return False

    def stop(self):
        self.queue = []
        self.current = None
        if self.voice_client and self.voice_client.is_connected():
            self.voice_client.stop()
            return True
        return False

    def set_volume(self, vol: float):
        self.volume = max(0.0, min(1.0, vol))
        if self.voice_client and self.voice_client.source:
            self.voice_client.source.volume = self.volume
        return self.volume

    def get_status(self) -> dict:
        return {
            "is_playing": self.voice_client.is_playing() if self.voice_client else False,
            "is_paused": self.voice_client.is_paused() if self.voice_client else False,
            "current_song": self.current,
            "queue": self.queue,
            "volume": self.volume,
            "connected": self.voice_client.is_connected() if self.voice_client else False
        }
