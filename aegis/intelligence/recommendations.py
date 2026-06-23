"""
Feature 6: Smart Recommendations Center

Generates actionable recommendations based on server analysis. Delegates to the central RecommendationEngine.
"""

import logging
import time
from typing import Dict, List, Any
from aegis.analytics.smart_features import RecommendationEngine

logger = logging.getLogger("aegis.intelligence.recommendations")

_cache: Dict[str, tuple] = {}  # guild_id -> (timestamp, result)
CACHE_TTL = 60  # seconds


class SmartRecommendationEngine:
    """Generates smart recommendations for server improvement by delegating to central engine."""

    def __init__(self, bot):
        self.bot = bot
        self._engine = RecommendationEngine(bot)

    def generate_recommendations(self, guild) -> List[Dict[str, Any]]:
        """Generate recommendations for a guild."""
        guild_id = str(guild.id)
        now = time.monotonic()
        if guild_id in _cache:
            ts, result = _cache[guild_id]
            if now - ts < CACHE_TTL:
                return result
        try:
            recs = self._engine.analyze(guild)
            result = [
                {
                    "title": r.title,
                    "description": r.description,
                    "severity": r.severity,
                    "impact_score": r.impact_score,
                    "confidence": r.confidence,
                    "auto_fix_available": r.auto_fix_available,
                    "fix_action": r.auto_fix_action,
                }
                for r in recs
            ]
            _cache[guild_id] = (now, result)
            return result
        except Exception as e:
            logger.error(f"Error generating recommendations: {e}")
            return []
