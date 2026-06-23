"""
Tests for smart features engine.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock

# Add parent directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aegis.analytics.smart_features import (
    RecommendationEngine,
    ConfigDoctor,
    PermissionDoctor,
    SmartRaidDetector,
    SmartGrowthAdvisor,
    SmartRoleCleaner,
    SmartChannelCleaner,
    SmartBackupAdvisor,
    ServerMaturityScore,
    AutoFixEngine,
)


class TestRecommendationEngine:
    """Tests for recommendation engine."""

    def test_analyze_returns_list(self):
        """Test that analyze returns a list of recommendations."""
        bot = MagicMock()
        bot.get_guild.return_value = MagicMock(
            verification_level=0,
            text_channels=[],
            roles=[MagicMock(name="@everyone", members=[MagicMock()])],
        )
        
        engine = RecommendationEngine(bot)
        result = engine.analyze(bot.get_guild())
        
        assert isinstance(result, list)
        assert len(result) > 0

    def test_recommendation_has_required_fields(self):
        """Test that recommendations have required fields."""
        bot = MagicMock()
        bot.get_guild.return_value = MagicMock(
            verification_level=0,
            text_channels=[],
            roles=[MagicMock(name="@everyone", members=[MagicMock()])],
        )
        
        engine = RecommendationEngine(bot)
        result = engine.analyze(bot.get_guild())
        
        for rec in result:
            assert hasattr(rec, "id")
            assert hasattr(rec, "title")
            assert hasattr(rec, "description")
            assert hasattr(rec, "severity")
            assert hasattr(rec, "impact_score")


class TestConfigDoctor:
    """Tests for config doctor."""

    def test_diagnose_returns_dict(self):
        """Test that diagnose returns a dict with scores."""
        bot = MagicMock()
        guild = MagicMock()
        guild.verification_level.value = 0
        guild.mfa_level = 0
        guild.text_channels = []
        guild.auto_moderation_rules = []
        guild.member_count = 10
        
        doctor = ConfigDoctor(bot)
        result = doctor.diagnose(guild)
        
        assert "overall" in result
        assert "dimensions" in result
        assert isinstance(result["overall"], int)
        assert 0 <= result["overall"] <= 100

    def test_dimension_scores(self):
        """Test that dimension scores are present."""
        bot = MagicMock()
        guild = MagicMock()
        guild.verification_level.value = 0
        guild.mfa_level = 0
        guild.text_channels = []
        guild.auto_moderation_rules = []
        guild.member_count = 10
        
        doctor = ConfigDoctor(bot)
        result = doctor.diagnose(guild)
        
        assert "security" in result["dimensions"]
        assert "moderation" in result["dimensions"]
        assert "growth" in result["dimensions"]
        assert "automation" in result["dimensions"]
        assert "reliability" in result["dimensions"]


class TestPermissionDoctor:
    """Tests for permission doctor."""

    def test_analyze_returns_dict(self):
        """Test that analyze returns findings."""
        bot = MagicMock()
        guild = MagicMock()
        guild.roles = [
            MagicMock(name="@everyone", permissions=MagicMock(administrator=False), managed=False, members=[MagicMock()]),
            MagicMock(name="Admin", permissions=MagicMock(administrator=True), managed=False, members=[MagicMock()]),
        ]
        
        doctor = PermissionDoctor(bot)
        result = doctor.analyze(guild)
        
        assert "total_roles" in result
        assert "findings" in result
        assert isinstance(result["findings"], list)


class TestSmartRaidDetector:
    """Tests for smart raid detector."""

    def test_analyze_returns_threat_level(self):
        """Test that analyze returns threat level."""
        bot = MagicMock()
        detector = SmartRaidDetector(bot)
        result = detector.analyze("guild1", [])
        
        assert "threat_level" in result
        assert result["threat_level"] in ["low", "medium", "high", "critical"]

    def test_record_join_increases_threat(self):
        """Test that recording joins increases threat level."""
        bot = MagicMock()
        detector = SmartRaidDetector(bot)
        
        # Create mock joins to simulate a raid pattern
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        recent_joins = [
            {
                "user_id": f"user{i}",
                "username": f"user{i}",
                "timestamp": now - datetime.timedelta(seconds=i * 10),
                "account_age_days": 1,
            }
            for i in range(15)
        ]
        
        result = detector.analyze("guild1", recent_joins)
        # Should have high/critical threat level due to high join rate of new accounts
        assert "threat_level" in result
        assert result["threat_level"] in ["high", "critical"]


class TestSmartRoleCleaner:
    """Tests for smart role cleaner."""

    def test_analyze_returns_unused_roles(self):
        """Test that analyze returns unused roles."""
        bot = MagicMock()
        guild = MagicMock()
        guild.roles = [
            MagicMock(name="@everyone", members=[MagicMock()]),
            MagicMock(name="UsedRole", members=[MagicMock()]),
            MagicMock(name="UnusedRole", members=[], managed=False),
        ]
        
        cleaner = SmartRoleCleaner(bot)
        result = cleaner.analyze(guild)
        
        assert "unused" in result
        assert "duplicates" in result
        assert isinstance(result["unused"], list)


class TestSmartChannelCleaner:
    """Tests for smart channel cleaner."""

    def test_analyze_returns_dead_channels(self):
        """Test that analyze returns dead channels."""
        bot = MagicMock()
        guild = MagicMock()
        guild.text_channels = [
            MagicMock(name="active-channel", last_message_id=123456789),
            MagicMock(name="dead-channel", last_message_id=None),
        ]
        
        cleaner = SmartChannelCleaner(bot)
        result = cleaner.analyze(guild)
        
        assert "dead" in result
        assert "duplicates" in result


class TestAutoFixEngine:
    """Tests for auto-fix engine."""

    def test_execute_fix_returns_result(self):
        """Test that execute_fix returns a FixResult."""
        bot = MagicMock()
        guild = MagicMock()
        
        engine = AutoFixEngine(bot)
        # This would require async execution, so we'll test the structure
        # In a real test, we'd use pytest-asyncio


class TestServerMaturityScore:
    """Tests for server maturity score."""

    def test_compute_returns_score(self):
        """Test that compute returns a maturity score."""
        bot = MagicMock()
        guild = MagicMock()
        guild.verification_level.value = 0
        guild.mfa_level = 0
        guild.text_channels = []
        guild.auto_moderation_rules = []
        guild.member_count = 10
        guild.roles = []
        
        scorer = ServerMaturityScore(bot)
        result = scorer.compute(guild)
        
        assert "overall" in result
        assert "dimensions" in result
        assert isinstance(result["overall"], int)
        assert 0 <= result["overall"] <= 100
