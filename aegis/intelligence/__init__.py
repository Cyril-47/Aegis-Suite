"""
Local Intelligence Engine for Aegis Suite.

100% local execution, no AI, no cloud, no telemetry.
Uses heuristics, statistics, pattern analysis, and rule engines.
"""

from aegis.intelligence.raid_detector import AdaptiveRaidDetector
from aegis.intelligence.sentiment import SmartSentimentAnalyzer
from aegis.intelligence.spam_detector import FuzzySpamDetector
from aegis.intelligence.activity import ActivityIntelligence
from aegis.intelligence.automation import AutomationEngine
from aegis.intelligence.recommendations import SmartRecommendationEngine
from aegis.intelligence.fix_center import OneClickFixCenter
from aegis.intelligence.timeline import IntelligenceTimeline

__all__ = [
    "AdaptiveRaidDetector",
    "SmartSentimentAnalyzer",
    "FuzzySpamDetector",
    "ActivityIntelligence",
    "AutomationEngine",
    "SmartRecommendationEngine",
    "OneClickFixCenter",
    "IntelligenceTimeline",
]
