"""
Tests for analytics engine.
"""

import pytest
import datetime
from unittest.mock import MagicMock, patch
from collections import deque

# Add parent directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aegis.analytics.engine import AnalyticsEngine


class TestAnalyticsEngine:
    """Tests for AnalyticsEngine."""

    @pytest.fixture
    def mock_session_factory(self):
        """Create a mock session factory."""
        return MagicMock()

    @pytest.fixture
    def engine(self, mock_session_factory):
        """Create an AnalyticsEngine instance."""
        return AnalyticsEngine(mock_session_factory)

    def test_init(self, engine):
        """Test engine initialization."""
        assert engine._batch_size == 100
        assert engine._flush_interval == 5.0
        assert engine._running is False

    def test_record_message(self, engine):
        """Test recording a message event."""
        engine.record_message("guild1", "channel1", "user1", 10)
        assert len(engine._buffer) == 1

    def test_record_member_event(self, engine):
        """Test recording a member event."""
        engine.record_member_event("guild1", "user1", "join")
        assert len(engine._buffer) == 1

    def test_buffer_batch_flush(self, engine):
        """Test that buffer flushes at batch size."""
        engine._batch_size = 5
        engine._loop = MagicMock()
        
        for i in range(5):
            engine.record_message("guild1", "channel1", f"user{i}", 10)
            
        engine._loop.call_soon_threadsafe.assert_called_once_with(engine._flush_now)

    def test_get_daily_stats(self, engine, mock_session_factory):
        """Test getting daily stats."""
        mock_session = MagicMock()
        mock_session_factory.return_value = mock_session
        mock_session.query.return_value.all.return_value = []
        
        result = engine.get_daily_stats("guild1", days=7)
        assert isinstance(result, list)

    def test_get_channel_activity(self, engine, mock_session_factory):
        """Test getting channel activity."""
        mock_session = MagicMock()
        mock_session_factory.return_value = mock_session
        mock_session.query.return_value.all.return_value = []
        
        result = engine.get_channel_activity("guild1", days=7)
        assert isinstance(result, dict)

    def test_get_top_users(self, engine, mock_session_factory):
        """Test getting top users."""
        mock_session = MagicMock()
        mock_session_factory.return_value = mock_session
        mock_session.query.return_value.all.return_value = []
        
        result = engine.get_top_users("guild1", days=7)
        assert isinstance(result, list)

    def test_get_mod_summary(self, engine, mock_session_factory):
        """Test getting moderation summary."""
        mock_session = MagicMock()
        mock_session_factory.return_value = mock_session
        mock_session.query.return_value.all.return_value = []
        
        result = engine.get_mod_summary("guild1", days=7)
        assert isinstance(result, dict)

    def test_get_overview(self, engine, mock_session_factory):
        """Test getting overview."""
        mock_session = MagicMock()
        mock_session_factory.return_value = mock_session
        mock_session.query.return_value.all.return_value = []
        
        result = engine.get_overview("guild1")
        assert isinstance(result, dict)
        assert "active_users_7d" in result
        assert "voice_minutes_7d" in result
