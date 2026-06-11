import discord
import asyncio
import logging
from typing import Optional
import re
import urllib.request
import urllib.parse
import json

logger = logging.getLogger("aegis.bot.music")

def _resolve_spotify_metadata(query: str) -> list[dict]:
    """Helper to scrape public Spotify embed pages and resolve metadata."""
    pattern = r"open\.spotify\.com/(track|playlist|album)/([a-zA-Z0-9]+)"
    match = re.search(pattern, query)
    if not match:
        raise ValueError("Invalid Spotify URL format.")
    
    media_type, media_id = match.group(1), match.group(2)
    url = f"https://open.spotify.com/embed/{media_type}/{media_id}"
    
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
    )
    
    try:
        with urllib.request.urlopen(req, timeout=10.0) as response:
            html = response.read().decode('utf-8')
    except Exception as e:
        logger.error(f"Failed to fetch Spotify embed page: {e}")
        raise ValueError(f"Failed to fetch Spotify metadata: {e}")
        
    next_data_match = re.search(r'<script[^>]*id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not next_data_match:
        raise ValueError("Failed to extract NextJS data from Spotify page.")
        
    try:
        data = json.loads(next_data_match.group(1))
    except Exception as e:
        raise ValueError(f"Failed to parse NextJS data: {e}")
        
    entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('data', {}).get('entity', {})
    if not entity:
        # Fallback to check nested paths
        entity = data.get('props', {}).get('pageProps', {}).get('state', {}).get('entity', {})
        
    if not entity:
        raise ValueError("Could not find entity data in Spotify embed JSON.")
        
    results = []
    
    if media_type == "track":
        title = entity.get('title') or entity.get('name')
        if not title:
            raise ValueError("Could not resolve track title from Spotify data.")
        
        artists = entity.get('artists', [])
        artist_names = []
        for a in artists:
            if isinstance(a, dict) and 'name' in a:
                artist_names.append(a['name'])
            elif isinstance(a, str):
                artist_names.append(a)
        
        artist_str = ", ".join(artist_names) if artist_names else ""
        query_str = f"ytsearch:{title} {artist_str}".strip()
        results.append({
            'title': f"{title} - {artist_str}" if artist_str else title,
            'artist': artist_str,
            'spotify_title': title,
            'query': query_str,
            'resolved': False
        })
    else:
        track_list = entity.get('trackList', [])
        if not track_list:
            track_list = entity.get('tracks', {}).get('items', [])
            
        for item in track_list:
            if not isinstance(item, dict):
                continue
            title = item.get('title') or item.get('name')
            subtitle = item.get('subtitle')
            if not subtitle:
                artists = item.get('artists', [])
                artist_names = []
                for a in artists:
                    if isinstance(a, dict) and 'name' in a:
                        artist_names.append(a['name'])
                    elif isinstance(a, str):
                        artist_names.append(a)
                subtitle = ", ".join(artist_names) if artist_names else ""
                
            if not title:
                continue
            
            query_str = f"ytsearch:{title} {subtitle}".strip()
            results.append({
                'title': f"{title} - {subtitle}" if subtitle else title,
                'artist': subtitle or "",
                'spotify_title': title,
                'query': query_str,
                'resolved': False
            })
            
    if not results:
        raise ValueError("No tracks found in the Spotify link.")
        
    media_title = entity.get('title') or entity.get('name') or "Spotify Link"
    return media_title, results

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

    PLAYLIST_YTDL_OPTIONS = {
        'format': 'bestaudio/best',
        'extract_flat': True,
        'nocheckcertificate': True,
        'ignoreerrors': True,
        'logtostderr': False,
        'quiet': True,
        'no_warnings': True,
        'source_address': '0.0.0.0'
    }

    FFMPEG_OPTIONS = {
        'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
        'options': '-vn'
    }

    ytdl = yt_dlp.YoutubeDL(YTDL_OPTIONS)
    playlist_ytdl = yt_dlp.YoutubeDL(PLAYLIST_YTDL_OPTIONS)
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
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.get_event_loop()
        self.disconnect_task = None
        self.idle_task = None
        self.resolved_track_cache = {}
        self.auto_leave_reason = None

    def _start_auto_leave_timer(self, seconds: int, reason: str):
        """Starts an asynchronous timer to automatically leave the voice channel."""
        self._cancel_auto_leave_timer()
        
        async def timer_coro():
            try:
                await asyncio.sleep(seconds)
                logger.info(f"Auto-leaving channel due to timer: {reason}")
                await self.leave_channel()
            except asyncio.CancelledError:
                pass
                
        self.auto_leave_reason = reason
        self.disconnect_task = self.loop.create_task(timer_coro())

    def _cancel_auto_leave_timer(self):
        """Cancels any active auto-leave timer."""
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
        self.disconnect_task = None
        self.auto_leave_reason = None

    def _check_alone_and_start_timer(self):
        """Helper to start 60s alone timer if alone in channel."""
        if self.voice_client and self.voice_client.is_connected():
            channel = getattr(self.voice_client, "channel", None)
            if channel:
                humans = [m for m in channel.members if not m.bot]
                if len(humans) == 0:
                    self._start_auto_leave_timer(60, "alone")

    async def join_channel(self, channel_id: int):
        """Joins a voice channel."""
        self.loop = asyncio.get_running_loop()
        channel = self.guild.get_channel(channel_id)
        if not isinstance(channel, discord.VoiceChannel):
            raise ValueError("Target channel is not a voice channel.")
            
        # Log and check bot permissions (Fix 4006 permissions issue)
        permissions = channel.permissions_for(self.guild.me)
        logger.info(f"Bot permissions in channel '{channel.name}' (ID: {channel_id}): "
                    f"view_channel={permissions.view_channel}, connect={permissions.connect}, "
                    f"speak={permissions.speak}, administrator={self.guild.me.guild_permissions.administrator}")
        
        if not permissions.view_channel:
            raise ValueError("Bot does not have View Channel permission in the target voice channel.")
        if not permissions.connect:
            raise ValueError("Bot does not have Connect permission in the target voice channel.")
            
        try:
            import nacl
        except ImportError:
            raise RuntimeError("Voice support is disabled because PyNaCl library is not installed.")
            
        # Authoritative voice client check (Fix 4006)
        voice_client = self.guild.voice_client
        if voice_client:
            if voice_client.is_connected():
                if voice_client.channel.id == channel_id:
                    self.voice_client = voice_client
                    return voice_client
                try:
                    await voice_client.move_to(channel)
                    self.voice_client = voice_client
                    return voice_client
                except Exception as e:
                    logger.warning(f"Failed to move voice channel: {e}. Reconnecting from scratch.")
                    try:
                        await voice_client.disconnect(force=True)
                    except Exception:
                        pass
            else:
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass

        try:
            self.voice_client = await channel.connect()
        except Exception as e:
            logger.warning(f"Initial connection failed ({e}), clearing voice state and retrying...")
            try:
                await self.guild.change_voice_state(channel=None)
            except Exception:
                pass
            
            # Check voice client again after state change
            voice_client = self.guild.voice_client
            if voice_client:
                try:
                    await voice_client.disconnect(force=True)
                except Exception:
                    pass
            
            await asyncio.sleep(1.5)
            try:
                self.voice_client = await channel.connect()
            except Exception as retry_err:
                logger.error(f"Failed to connect to voice channel on retry: {retry_err}")
                raise retry_err
        
        # Start inactivity loop if not already running
        if self.loop.is_running():
            if not self.idle_task or self.idle_task.done():
                self.idle_task = self.loop.create_task(self._inactivity_check_loop())
            
        self._cancel_auto_leave_timer()
        self._check_alone_and_start_timer()
        return self.voice_client

    async def leave_channel(self):
        """Leaves voice channel and clears queue."""
        self.loop = asyncio.get_running_loop()
        if self.voice_client and await self._is_connected():
            await self.voice_client.disconnect()
        self.voice_client = None
        self.queue = []
        self.current = None
        self._cancel_auto_leave_timer()
        if self.disconnect_task and not self.disconnect_task.done():
            self.disconnect_task.cancel()
        self.disconnect_task = None
        if self.idle_task and not self.idle_task.done():
            self.idle_task.cancel()
        self.idle_task = None

    async def _is_connected(self) -> bool:
        if not self.voice_client:
            return False
        fn = self.voice_client.is_connected
        if asyncio.iscoroutinefunction(fn):
            return await fn()
        elif callable(fn):
            res = fn()
            if asyncio.iscoroutine(res):
                return await res
            return bool(res)
        return bool(fn)

    async def _is_playing_or_paused(self) -> bool:
        if not self.voice_client:
            return False
        playing = False
        fn_playing = getattr(self.voice_client, "is_playing", None)
        if callable(fn_playing):
            res = fn_playing()
            if asyncio.iscoroutine(res):
                playing = await res
            else:
                playing = bool(res)
        else:
            playing = bool(fn_playing)

        paused = False
        fn_paused = getattr(self.voice_client, "is_paused", None)
        if callable(fn_paused):
            res = fn_paused()
            if asyncio.iscoroutine(res):
                paused = await res
            else:
                paused = bool(res)
        else:
            paused = bool(fn_paused)

        return playing or paused

    async def _inactivity_check_loop(self):
        """Periodically checks if the bot is alone in the voice channel or not playing music,
        and disconnects if the inactivity threshold (5 minutes) is met.
        """
        idle_seconds = 0
        while self.voice_client and await self._is_connected():
            await asyncio.sleep(5)
            
            # Check if alone
            bot_channel = self.voice_client.channel
            humans = [m for m in bot_channel.members if not m.bot]
            is_alone = len(humans) == 0
            
            # Check if playing music (active or paused)
            is_playing = await self._is_playing_or_paused()
            
            if is_alone or not is_playing:
                idle_seconds += 5
            else:
                idle_seconds = 0
                
            if idle_seconds >= 300: # 5 minutes timeout
                logger.info(f"Auto-disconnecting from voice channel '{bot_channel.name}' due to inactivity (alone={is_alone}, not_playing={not is_playing}).")
                await self.leave_channel()
                break

    async def play_next(self):
        """Plays the next song in queue with lazy resolution and recovery."""
        self.loop = asyncio.get_running_loop()
        
        # Cancel any active auto-leave timer when starting to process a new song
        self._cancel_auto_leave_timer()
        
        if len(self.queue) == 0:
            self.current = None
            # Queue is empty, start 120s empty queue timer
            self._start_auto_leave_timer(120, "empty")
            return
            
        if not self.voice_client or not self.voice_client.is_connected():
            return
            
        next_song = self.queue.pop(0)
        self.current = next_song
        
        # Check if song is resolved
        if not next_song.get('resolved', True):
            resolved = False
            # Check cache
            cache_key = next_song.get('webpage_url') or next_song.get('query')
            if cache_key and cache_key in self.resolved_track_cache:
                cached = self.resolved_track_cache[cache_key]
                next_song['url'] = cached.get('url')
                next_song['title'] = cached.get('title') or next_song['title']
                next_song['duration'] = cached.get('duration') or next_song.get('duration', 0)
                next_song['thumbnail'] = cached.get('thumbnail') or next_song.get('thumbnail')
                next_song['resolved'] = True
                resolved = True
                logger.info(f"Resolved track from cache: {next_song['title']}")
                
            if not resolved:
                # Resolve using ytsearch or webpage_url
                try:
                    resolve_query = next_song.get('webpage_url') or next_song.get('query')
                    if not resolve_query:
                        raise ValueError("No webpage_url or query to resolve.")
                        
                    logger.info(f"Lazily resolving track: {resolve_query}")
                    data = await self.loop.run_in_executor(
                        None,
                        lambda: ytdl.extract_info(resolve_query, download=False)
                    )
                    
                    if 'entries' in data:
                        if len(data['entries']) == 0:
                            raise ValueError("No search results found.")
                        song_data = data['entries'][0]
                    else:
                        song_data = data
                        
                    if not song_data or not song_data.get('url'):
                        raise ValueError("No stream URL resolved.")
                        
                    next_song['url'] = song_data.get('url')
                    if song_data.get('title'):
                        next_song['title'] = song_data.get('title')
                    next_song['duration'] = song_data.get('duration', 0)
                    next_song['thumbnail'] = song_data.get('thumbnail')
                    next_song['resolved'] = True
                    
                    # Cache the resolved data
                    if cache_key:
                        self.resolved_track_cache[cache_key] = {
                            'url': next_song['url'],
                            'title': next_song['title'],
                            'duration': next_song['duration'],
                            'thumbnail': next_song['thumbnail']
                        }
                        
                except Exception as e:
                    logger.warning(f"Failed to resolve track '{next_song.get('title')}': {e}. Skipping...")
                    # Recover: play next song
                    self.loop.create_task(self.play_next())
                    return
        else:
            # If it was marked resolved, but only has webpage_url and not stream url, refresh it
            if next_song.get('webpage_url') and not next_song.get('url'):
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

        # Start playback
        try:
            import shutil
            if not shutil.which("ffmpeg"):
                logger.error("FFmpeg not found in PATH. Playback failed.")
                return
                
            if not next_song.get('url'):
                raise ValueError("No stream URL available for playback.")
                
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
            logger.error(f"Error starting playback: {e}. Skipping...")
            self.loop.create_task(self.play_next())

    async def add_to_queue(self, query: str, requester_id: Optional[int] = None) -> dict:
        """Searches YouTube or resolves Spotify metadata and adds song(s) to queue."""
        self.loop = asyncio.get_running_loop()
        if not yt_dlp:
            raise RuntimeError("yt-dlp is not installed on this system.")
            
        loop = self.loop
        
        # Cancel any active auto-leave timer since we are adding a song
        self._cancel_auto_leave_timer()
        
        is_spotify = "open.spotify.com" in query
        is_youtube_playlist = ("list=" in query or "/playlist" in query) and not is_spotify
        is_youtube_mix = is_youtube_playlist and "list=RD" in query
        
        songs_added = []
        skipped_count = 0
        limit_reached = False
        
        try:
            if is_spotify:
                media_title, spotify_tracks = await self.loop.run_in_executor(
                    None,
                    lambda: _resolve_spotify_metadata(query)
                )
                
                # Determine limit based on type
                if "/playlist/" in query:
                    limit = 200
                elif "/album/" in query:
                    limit = 100
                else:
                    limit = 1
                    
                total_tracks = len(spotify_tracks)
                if total_tracks > limit:
                    spotify_tracks = spotify_tracks[:limit]
                    skipped_count = total_tracks - limit
                    limit_reached = True
                    
                for track in spotify_tracks:
                    song_info = {
                        'title': track['title'],
                        'url': None,
                        'webpage_url': None,
                        'query': track['query'],
                        'duration': 0,
                        'thumbnail': None,
                        'resolved': False,
                        'requester_id': requester_id
                    }
                    self.queue.append(song_info)
                    songs_added.append(song_info)
                    
                if len(songs_added) > 1:
                    if not self.voice_client or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                        if self.voice_client and self.voice_client.is_connected():
                            await self.play_next()
                    self._check_alone_and_start_timer()
                    return {
                        'title': media_title or "Spotify Playlist/Album",
                        'playlist': True,
                        'count': len(songs_added),
                        'skipped': skipped_count,
                        'limit_reached': limit_reached
                    }
                elif len(songs_added) == 1:
                    song_info = songs_added[0]
                    if not self.voice_client or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                        if self.voice_client and self.voice_client.is_connected():
                            await self.play_next()
                    self._check_alone_and_start_timer()
                    return song_info
                else:
                    raise ValueError("No tracks could be added from Spotify link.")
                    
            elif is_youtube_playlist:
                limit = 100 if is_youtube_mix else 200
                
                data = await loop.run_in_executor(
                    None,
                    lambda: playlist_ytdl.extract_info(query, download=False)
                )
                
                if not data or 'entries' not in data:
                    raise ValueError("Failed to extract playlist entries.")
                    
                entries = list(data['entries'])
                if not entries:
                    raise ValueError("Playlist is empty or could not be loaded.")
                    
                total_tracks = len(entries)
                if total_tracks > limit:
                    entries = entries[:limit]
                    skipped_count = total_tracks - limit
                    limit_reached = True
                    
                for entry in entries:
                    if not entry:
                        continue
                    video_url = entry.get('url') or entry.get('webpage_url')
                    if not video_url and entry.get('id'):
                        video_url = f"https://www.youtube.com/watch?v={entry['id']}"
                        
                    song_info = {
                        'title': entry.get('title') or 'Unknown Title',
                        'url': None,
                        'webpage_url': video_url,
                        'duration': entry.get('duration', 0),
                        'thumbnail': entry.get('thumbnail'),
                        'resolved': False,
                        'requester_id': requester_id
                    }
                    self.queue.append(song_info)
                    songs_added.append(song_info)
                    
                if not self.voice_client or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                    if self.voice_client and self.voice_client.is_connected():
                        await self.play_next()
                        
                self._check_alone_and_start_timer()
                return {
                    'title': data.get('title') or f"YouTube Playlist ({len(songs_added)} tracks)",
                    'playlist': True,
                    'count': len(songs_added),
                    'skipped': skipped_count,
                    'limit_reached': limit_reached
                }
            else:
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
                    'thumbnail': song_data.get('thumbnail'),
                    'resolved': True,
                    'requester_id': requester_id
                }
                
                if song_info.get('webpage_url'):
                    self.resolved_track_cache[song_info['webpage_url']] = {
                        'url': song_info['url'],
                        'title': song_info['title'],
                        'duration': song_info['duration'],
                        'thumbnail': song_info['thumbnail']
                    }
                    
                self.queue.append(song_info)
                
                if not self.voice_client or (not self.voice_client.is_playing() and not self.voice_client.is_paused()):
                    if self.voice_client and self.voice_client.is_connected():
                        await self.play_next()
                        
                self._check_alone_and_start_timer()
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
            self._start_auto_leave_timer(120, "empty")
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
