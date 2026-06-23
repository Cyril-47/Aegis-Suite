"""
Feature 8: Intelligence Timeline

Chronological timeline of intelligence events.
"""

import logging
import datetime
from typing import Dict, List, Any
from collections import deque

logger = logging.getLogger("aegis.intelligence.timeline")


class IntelligenceTimeline:
    """Intelligence timeline for tracking events."""

    def __init__(self):
        self._events: deque = deque(maxlen=2000)

    def add_event(self, event_type: str, severity: str, details: str, guild_id: str = None):
        """Add an event to the timeline."""
        self._events.append({
            "type": event_type,
            "severity": severity,
            "details": details,
            "guild_id": guild_id,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

    def get_timeline(self, guild_id: str = None, days: int = 7, limit: int = 100) -> List[Dict[str, Any]]:
        """Get timeline events."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
        
        events = self._events
        if guild_id:
            events = [e for e in events if e.get("guild_id") == guild_id]
        
        events = [e for e in events if datetime.datetime.fromisoformat(e["timestamp"]) > cutoff]
        
        return sorted(events, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_event_counts(self, guild_id: str = None, days: int = 7) -> Dict[str, int]:
        """Get counts of events by type."""
        timeline = self.get_timeline(guild_id, days)
        
        counts = {}
        for event in timeline:
            event_type = event["type"]
            counts[event_type] = counts.get(event_type, 0) + 1
        
        return counts

    def get_severity_distribution(self, guild_id: str = None, days: int = 7) -> Dict[str, int]:
        """Get distribution of events by severity."""
        timeline = self.get_timeline(guild_id, days)
        
        distribution = {}
        for event in timeline:
            severity = event["severity"]
            distribution[severity] = distribution.get(severity, 0) + 1
        
        return distribution
