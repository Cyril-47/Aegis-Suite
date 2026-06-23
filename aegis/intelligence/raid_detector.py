"""
Feature 1: Adaptive Raid Detection

Replace static raid thresholds with adaptive anomaly detection.
Learns normal activity patterns and triggers alerts on anomalies.
"""

import logging
import math
import datetime
from typing import Dict, List, Optional, Any
from collections import deque
from dataclasses import dataclass

logger = logging.getLogger("aegis.intelligence.raid")


@dataclass
class ActivityMetrics:
    """Rolling metrics for activity tracking."""
    joins: deque  # timestamps of joins
    messages: deque  # timestamps of messages
    mod_actions: deque  # timestamps of moderation actions


class AdaptiveRaidDetector:
    """
    Adaptive anomaly detection for raid patterns.
    
    Learns normal activity rates and triggers alerts when
    current activity exceeds baseline by threshold multiples.
    """

    def __init__(self):
        # Store per-guild metrics
        self._metrics: Dict[str, ActivityMetrics] = {}
        
        # Thresholds (standard deviations above mean)
        self.WARNING_THRESHOLD = 2.0
        self.HIGH_THRESHOLD = 3.0
        self.CRITICAL_THRESHOLD = 5.0
        
        # Rolling window sizes
        self.SHORT_WINDOW = 15 * 60  # 15 minutes
        self.MEDIUM_WINDOW = 60 * 60  # 1 hour
        self.LONG_WINDOW = 24 * 60 * 60  # 24 hours

    def _get_metrics(self, guild_id: str) -> ActivityMetrics:
        """Get or create metrics for a guild."""
        if guild_id not in self._metrics:
            self._metrics[guild_id] = ActivityMetrics(
                joins=deque(),
                messages=deque(),
                mod_actions=deque(),
            )
        return self._metrics[guild_id]

    def _cleanup_old_entries(self, metric_queue: deque, max_age: int):
        """Remove entries older than max_age seconds."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=max_age)
        while metric_queue and metric_queue[0] < cutoff:
            metric_queue.popleft()

    def record_join(self, guild_id: str):
        """Record a member join event."""
        metrics = self._get_metrics(guild_id)
        metrics.joins.append(datetime.datetime.now(datetime.timezone.utc))
        self._cleanup_old_entries(metrics.joins, self.LONG_WINDOW)

    def record_message(self, guild_id: str):
        """Record a message event."""
        metrics = self._get_metrics(guild_id)
        metrics.messages.append(datetime.datetime.now(datetime.timezone.utc))
        self._cleanup_old_entries(metrics.messages, self.LONG_WINDOW)

    def record_mod_action(self, guild_id: str):
        """Record a moderation action."""
        metrics = self._get_metrics(guild_id)
        metrics.mod_actions.append(datetime.datetime.now(datetime.timezone.utc))
        self._cleanup_old_entries(metrics.mod_actions, self.LONG_WINDOW)

    def _calculate_rate(self, metric_queue: deque, window_seconds: int) -> float:
        """Calculate events per minute over a window."""
        cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=window_seconds)
        count = sum(1 for ts in metric_queue if ts >= cutoff)
        return count / (window_seconds / 60)

    def _calculate_baseline(self, metric_queue: deque) -> Dict[str, float]:
        """Calculate baseline statistics from historical data."""
        if len(metric_queue) < 5:
            return {"average": 0.0, "stdev": 0.0}
        
        now = datetime.datetime.now(datetime.timezone.utc)
        from collections import defaultdict
        bucket_counts = defaultdict(int)
        
        # Single pass: assign each event to its 5-min bucket
        for ts in metric_queue:
            age_minutes = (now - ts).total_seconds() / 60
            if age_minutes < 1440:  # within 24h
                bucket_idx = int(age_minutes / 5)
                bucket_counts[bucket_idx] += 1
        
        rates = [bucket_counts.get(i, 0) for i in range(288)]
        avg = sum(rates) / len(rates)
        variance = sum((r - avg) ** 2 for r in rates) / len(rates)
        stdev = math.sqrt(variance) if variance > 0 else 0.0
        return {"average": avg, "stdev": stdev}

    def analyze(self, guild_id: str) -> Dict[str, Any]:
        """
        Analyze current activity and detect anomalies.
        
        Returns:
            Dict with threat level, scores, and reasons.
        """
        metrics = self._get_metrics(guild_id)
        
        # Calculate current rates (events per minute)
        current_join_rate = self._calculate_rate(metrics.joins, self.SHORT_WINDOW)
        current_msg_rate = self._calculate_rate(metrics.messages, self.SHORT_WINDOW)
        current_mod_rate = self._calculate_rate(metrics.mod_actions, self.SHORT_WINDOW)
        
        # Calculate baselines
        join_baseline = self._calculate_baseline(metrics.joins)
        msg_baseline = self._calculate_baseline(metrics.messages)
        mod_baseline = self._calculate_baseline(metrics.mod_actions)
        
        # Calculate anomaly scores
        join_score = self._calculate_anomaly_score(current_join_rate, join_baseline)
        msg_score = self._calculate_anomaly_score(current_msg_rate, msg_baseline)
        mod_score = self._calculate_anomaly_score(current_mod_rate, mod_baseline)
        
        # Overall threat level
        max_score = max(join_score, msg_score, mod_score)
        
        if max_score >= self.CRITICAL_THRESHOLD:
            threat_level = "critical"
        elif max_score >= self.HIGH_THRESHOLD:
            threat_level = "high"
        elif max_score >= self.WARNING_THRESHOLD:
            threat_level = "elevated"
        else:
            threat_level = "normal"
        
        # Generate reasons
        reasons = []
        if join_score >= self.WARNING_THRESHOLD:
            pct = int((current_join_rate / max(join_baseline["average"], 0.01)) * 100) if join_baseline["average"] > 0 else 999
            reasons.append(f"Joins are {pct}% above baseline")
        if msg_score >= self.WARNING_THRESHOLD:
            pct = int((current_msg_rate / max(msg_baseline["average"], 0.01)) * 100) if msg_baseline["average"] > 0 else 999
            reasons.append(f"Messages are {pct}% above baseline")
        if mod_score >= self.WARNING_THRESHOLD:
            pct = int((current_mod_rate / max(mod_baseline["average"], 0.01)) * 100) if mod_baseline["average"] > 0 else 999
            reasons.append(f"Moderation actions are {pct}% above baseline")
        
        if not reasons:
            reasons.append("Activity within normal parameters")
        
        return {
            "guild_id": guild_id,
            "threat_level": threat_level,
            "threat_score": round(max_score, 2),
            "scores": {
                "joins": round(join_score, 2),
                "messages": round(msg_score, 2),
                "moderation": round(mod_score, 2),
            },
            "rates": {
                "joins_per_min": round(current_join_rate, 2),
                "messages_per_min": round(current_msg_rate, 2),
                "mod_actions_per_min": round(current_mod_rate, 2),
            },
            "baseline": {
                "joins": join_baseline,
                "messages": msg_baseline,
                "moderation": mod_baseline,
            },
            "reasons": reasons,
            "suggested_actions": self._get_suggested_actions(threat_level),
        }

    def _calculate_anomaly_score(self, current_rate: float, baseline: Dict[str, float]) -> float:
        """Calculate how many standard deviations above baseline."""
        if baseline["stdev"] == 0:
            return 0.0 if current_rate <= baseline["average"] else 99.0
        
        return (current_rate - baseline["average"]) / baseline["stdev"]

    def _get_suggested_actions(self, threat_level: str) -> List[Dict[str, str]]:
        """Get suggested actions based on threat level."""
        actions = []
        
        if threat_level == "critical":
            actions.append({"label": "Enable Raid Mode", "action": "enable_raid_mode"})
            actions.append({"label": "Lock Server", "action": "lock_server"})
            actions.append({"label": "Enable Verification", "action": "enable_verification"})
        elif threat_level == "high":
            actions.append({"label": "Slowmode All Channels", "action": "slowmode_all_channels"})
            actions.append({"label": "Enable Verification", "action": "enable_verification"})
            actions.append({"label": "Restrict New Members", "action": "restrict_new_members"})
        elif threat_level == "elevated":
            actions.append({"label": "Enable Slowmode", "action": "enable_slowmode"})
            actions.append({"label": "Enable Verification", "action": "enable_verification"})
        
        return actions
