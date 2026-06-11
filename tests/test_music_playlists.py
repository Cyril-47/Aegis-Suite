import pytest
import asyncio
import discord
import urllib.request
import json
from unittest.mock import AsyncMock, MagicMock, patch
from aegis.bot.music import MusicPlayer, _resolve_spotify_metadata

def make_spotify_html(media_type, media_id, title, tracks_data=None):
    if media_type == "track":
        entity = {
            "title": title,
            "artists": [{"name": "Test Artist"}]
        }
    else:
        entity = {
            "title": title,
            "trackList": tracks_data or [
                {"title": "Track 1", "subtitle": "Artist 1"},
                {"title": "Track 2", "subtitle": "Artist 2"}
            ]
        }
        
    next_data = {
        "props": {
            "pageProps": {
                "state": {
                    "data": {
                        "entity": entity
                    }
                }
            }
        }
    }
    return f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(next_data)}</script></html>'

@pytest.mark.asyncio
async def test_resolve_spotify_metadata_track():
    html = make_spotify_html("track", "12345", "Spoti Track")
    
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = html.encode('utf-8')
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        title, results = _resolve_spotify_metadata("https://open.spotify.com/track/12345")
        
        assert title == "Spoti Track"
        assert len(results) == 1
        assert results[0]['spotify_title'] == "Spoti Track"
        assert results[0]['query'] == "ytsearch:Spoti Track Test Artist"
        assert results[0]['resolved'] is False

@pytest.mark.asyncio
async def test_resolve_spotify_metadata_playlist():
    tracks = [{"title": f"Spoti Song {i}", "subtitle": f"Artist {i}"} for i in range(5)]
    html = make_spotify_html("playlist", "67890", "Spoti Playlist", tracks)
    
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = html.encode('utf-8')
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        title, results = _resolve_spotify_metadata("https://open.spotify.com/playlist/67890")
        
        assert title == "Spoti Playlist"
        assert len(results) == 5
        assert results[0]['spotify_title'] == "Spoti Song 0"
        assert results[0]['query'] == "ytsearch:Spoti Song 0 Artist 0"
        assert results[0]['resolved'] is False

@pytest.mark.asyncio
async def test_queue_safety_limits_spotify_playlist():
    guild = MagicMock()
    guild.voice_client = None
    player = MusicPlayer(guild)
    
    tracks = [{"title": f"Song {i}", "subtitle": "Artist"} for i in range(250)]
    html = make_spotify_html("playlist", "67890", "Big Spotify Playlist", tracks)
    
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = html.encode('utf-8')
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        res = await player.add_to_queue("https://open.spotify.com/playlist/67890")
        
        assert res['playlist'] is True
        assert res['count'] == 200
        assert res['skipped'] == 50
        assert res['limit_reached'] is True
        assert len(player.queue) == 200

@pytest.mark.asyncio
async def test_queue_safety_limits_spotify_album():
    guild = MagicMock()
    guild.voice_client = None
    player = MusicPlayer(guild)
    
    tracks = [{"title": f"Song {i}", "subtitle": "Artist"} for i in range(120)]
    html = make_spotify_html("album", "67890", "Big Spotify Album", tracks)
    
    mock_response = MagicMock()
    mock_response.__enter__.return_value = mock_response
    mock_response.read.return_value = html.encode('utf-8')
    
    with patch("urllib.request.urlopen", return_value=mock_response):
        res = await player.add_to_queue("https://open.spotify.com/album/67890")
        
        assert res['playlist'] is True
        assert res['count'] == 100
        assert res['skipped'] == 20
        assert res['limit_reached'] is True
        assert len(player.queue) == 100

@pytest.mark.asyncio
async def test_queue_safety_limits_youtube_playlist():
    guild = MagicMock()
    guild.voice_client = None
    player = MusicPlayer(guild)
    
    playlist_ytdl_mock = MagicMock()
    playlist_ytdl_mock.extract_info.return_value = {
        'title': 'Big YT Playlist',
        'entries': [{'title': f'YT Track {i}', 'url': f'http://yt/url/{i}', 'duration': 180} for i in range(220)]
    }
    
    with patch("aegis.bot.music.playlist_ytdl", playlist_ytdl_mock):
        res = await player.add_to_queue("https://www.youtube.com/playlist?list=PL123")
        
        assert res['playlist'] is True
        assert res['count'] == 200
        assert res['skipped'] == 20
        assert res['limit_reached'] is True
        assert len(player.queue) == 200

@pytest.mark.asyncio
async def test_queue_safety_limits_youtube_mix():
    guild = MagicMock()
    guild.voice_client = None
    player = MusicPlayer(guild)
    
    playlist_ytdl_mock = MagicMock()
    playlist_ytdl_mock.extract_info.return_value = {
        'title': 'Big YT Mix',
        'entries': [{'title': f'YT Track {i}', 'url': f'http://yt/url/{i}', 'duration': 180} for i in range(130)]
    }
    
    with patch("aegis.bot.music.playlist_ytdl", playlist_ytdl_mock):
        res = await player.add_to_queue("https://www.youtube.com/watch?v=123&list=RD123")
        
        assert res['playlist'] is True
        assert res['count'] == 100
        assert res['skipped'] == 30
        assert res['limit_reached'] is True
        assert len(player.queue) == 100

@pytest.mark.asyncio
async def test_lazy_resolution_and_cache_lookup():
    guild = MagicMock()
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = True
    guild.voice_client = vc
    
    player = MusicPlayer(guild)
    player.voice_client = vc
    
    player.queue.append({
        'title': 'Lazy Track',
        'url': None,
        'webpage_url': 'http://yt/lazy-track',
        'resolved': False
    })
    
    mock_data = {
        'title': 'Lazy Track Resolved',
        'url': 'http://stream/lazy-track-stream',
        'duration': 150,
        'thumbnail': 'http://thumb'
    }
    
    ytdl_mock = MagicMock()
    ytdl_mock.extract_info.return_value = mock_data
    
    with patch("shutil.which", return_value="/bin/ffmpeg"), \
         patch("discord.FFmpegPCMAudio"), \
         patch("discord.PCMVolumeTransformer", lambda source, volume: source), \
         patch("aegis.bot.music.ytdl", ytdl_mock):
         
        await player.play_next()
        
        ytdl_mock.extract_info.assert_called_once_with('http://yt/lazy-track', download=False)
        assert player.current['resolved'] is True
        assert player.current['url'] == 'http://stream/lazy-track-stream'
        
        assert 'http://yt/lazy-track' in player.resolved_track_cache
        assert player.resolved_track_cache['http://yt/lazy-track']['url'] == 'http://stream/lazy-track-stream'
        
        player.queue.append({
            'title': 'Lazy Track',
            'url': None,
            'webpage_url': 'http://yt/lazy-track',
            'resolved': False
        })
        
        ytdl_mock.extract_info.reset_mock()
        await player.play_next()
        
        ytdl_mock.extract_info.assert_not_called()
        assert player.current['resolved'] is True
        assert player.current['url'] == 'http://stream/lazy-track-stream'

@pytest.mark.asyncio
async def test_failed_track_recovery():
    guild = MagicMock()
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = True
    guild.voice_client = vc
    
    player = MusicPlayer(guild)
    player.voice_client = vc
    
    player.queue.append({
        'title': 'Failing Track',
        'url': None,
        'webpage_url': 'http://yt/fail',
        'resolved': False
    })
    player.queue.append({
        'title': 'Succeeding Track',
        'url': None,
        'webpage_url': 'http://yt/success',
        'resolved': False
    })
    
    def mock_extract(query, download=False):
        if "fail" in query:
            raise Exception("YouTube extraction failed")
        return {
            'title': 'Succeeding Track Resolved',
            'url': 'http://stream/success',
            'duration': 120
        }
        
    ytdl_mock = MagicMock()
    ytdl_mock.extract_info.side_effect = mock_extract
    
    with patch("shutil.which", return_value="/bin/ffmpeg"), \
         patch("discord.FFmpegPCMAudio"), \
         patch("discord.PCMVolumeTransformer", lambda source, volume: source), \
         patch("aegis.bot.music.ytdl", ytdl_mock):
         
        await player.play_next()
        await asyncio.sleep(0.1)
        
        assert player.current['title'] == 'Succeeding Track Resolved'
        assert player.current['resolved'] is True
        assert player.current['url'] == 'http://stream/success'

@pytest.mark.asyncio
async def test_auto_leave_timers():
    guild = MagicMock()
    vc = MagicMock(spec=discord.VoiceClient)
    vc.is_connected.return_value = True
    vc.channel = MagicMock(spec=discord.VoiceChannel)
    vc.channel.members = []
    guild.voice_client = vc
    
    player = MusicPlayer(guild)
    player.voice_client = vc
    
    # 1. Empty queue auto-leave scenario
    await player.play_next()
    assert player.auto_leave_reason == "empty"
    assert player.disconnect_task is not None
    assert not player.disconnect_task.done()
    
    # 2. Cancelling auto-leave when adding a track
    ytdl_mock = MagicMock()
    ytdl_mock.extract_info.return_value = {
        'title': 'New Track',
        'url': 'http://stream/new',
        'webpage_url': 'http://yt/new',
        'duration': 120
    }
    with patch("aegis.bot.music.ytdl", ytdl_mock):
        player.voice_client = None # prevent auto-playing and resetting timer
        await player.add_to_queue("http://yt/new")
        
        assert player.disconnect_task is None
        assert player.auto_leave_reason is None
