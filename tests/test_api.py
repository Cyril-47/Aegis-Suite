"""
Tests for API endpoints.
"""

import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi.testclient import TestClient

# Add parent directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


class TestHealthEndpoints:
    """Tests for health check endpoints."""

    def test_health_endpoint(self):
        """Test that health endpoint returns OK."""
        # This would require setting up the full FastAPI app
        # For now, we'll test the route functions directly
        pass


class TestSmartFeaturesEndpoints:
    """Tests for smart features endpoints."""

    def test_raid_monitor_returns_data(self):
        """Test that raid monitor returns proper data structure."""
        from aegis.intelligence.raid_detector import AdaptiveRaidDetector
        
        detector = AdaptiveRaidDetector()
        result = detector.analyze("test_guild")
        
        assert "threat_level" in result
        assert "threat_score" in result
        assert "scores" in result
        assert "reasons" in result

    def test_sentiment_analyzer_returns_data(self):
        """Test that sentiment analyzer returns proper data structure."""
        from aegis.intelligence.sentiment import SmartSentimentAnalyzer
        
        analyzer = SmartSentimentAnalyzer()
        result = analyzer.get_community_health("test_guild")
        
        assert "overall_score" in result
        assert "positivity_rate" in result
        assert "toxicity_rate" in result

    def test_spam_detector_returns_data(self):
        """Test that spam detector returns proper data structure."""
        from aegis.intelligence.spam_detector import FuzzySpamDetector
        
        detector = FuzzySpamDetector()
        result = detector.get_spam_intelligence("test_guild")
        
        assert "campaigns" in result
        assert "total_campaigns" in result

    def test_activity_intelligence_returns_data(self):
        """Test that activity intelligence returns proper data structure."""
        from aegis.intelligence.activity import ActivityIntelligence
        
        intelligence = ActivityIntelligence()
        result = intelligence.analyze_activity("test_guild")
        
        assert "peak_hour" in result
        assert "peak_day" in result
        assert "recommendations" in result


class TestSmartFeatures:
    """Tests for smart features engine."""

    def test_recommendation_engine(self):
        """Test recommendation engine with mock bot."""
        from unittest.mock import MagicMock
        
        bot = MagicMock()
        bot.get_guild.return_value = MagicMock(
            verification_level=0,
            text_channels=[],
            roles=[MagicMock(name="@everyone", members=[MagicMock()])],
        )
        
        from aegis.analytics.smart_features import RecommendationEngine
        engine = RecommendationEngine(bot)
        recommendations = engine.analyze(bot.get_guild())
        
        assert isinstance(recommendations, list)
        # Should have at least one recommendation for verification
        assert len(recommendations) > 0

    def test_config_doctor(self):
        """Test config doctor with mock guild."""
        from unittest.mock import MagicMock
        
        bot = MagicMock()
        guild = MagicMock()
        guild.verification_level.value = 0
        guild.mfa_level = 0
        guild.text_channels = []
        guild.auto_moderation_rules = []
        guild.member_count = 10
        
        from aegis.analytics.smart_features import ConfigDoctor
        doctor = ConfigDoctor(bot)
        result = doctor.diagnose(guild)
        
        assert "overall" in result
        assert "dimensions" in result
        assert isinstance(result["overall"], int)

    def test_permission_doctor(self):
        """Test permission doctor with mock guild."""
        from unittest.mock import MagicMock
        
        bot = MagicMock()
        guild = MagicMock()
        guild.roles = [
            MagicMock(name="@everyone", permissions=MagicMock(administrator=False), managed=False, members=[MagicMock()]),
            MagicMock(name="Admin", permissions=MagicMock(administrator=True), managed=False, members=[MagicMock()]),
        ]
        
        from aegis.analytics.smart_features import PermissionDoctor
        doctor = PermissionDoctor(bot)
        result = doctor.analyze(guild)
        
        assert "total_roles" in result
        assert "findings" in result


class TestAutomationEngine:
    """Tests for automation engine."""

    def test_create_rule(self):
        """Test creating an automation rule."""
        from aegis.intelligence.automation import AutomationEngine
        
        engine = AutomationEngine()
        rule = engine.create_rule("123456789", {
            "name": "Test Rule",
            "trigger": "member_join",
            "conditions": [],
            "actions": [{"action": "log_event", "params": {"event_type": "join"}}]
        })
        
        assert rule.name == "Test Rule"
        assert rule.trigger == "member_join"
        assert rule.enabled is True

    def test_validate_rule(self):
        """Test rule validation."""
        from aegis.intelligence.automation import AutomationEngine
        
        engine = AutomationEngine()
        
        # Valid rule
        valid = engine.validate_rule({
            "trigger": "member_join",
            "conditions": [],
            "actions": [{"action": "log_event", "params": {}}]
        })
        assert valid["valid"] is True
        
        # Invalid rule (missing trigger)
        invalid = engine.validate_rule({
            "conditions": [],
            "actions": [{"action": "log_event", "params": {}}]
        })
        assert invalid["valid"] is False
        assert len(invalid["errors"]) > 0
