"""
Feature 4: Activity Intelligence

Analyzes activity patterns to find optimal times for events, giveaways, and announcements.
Pure statistical analysis - no AI.
"""

import logging
import datetime
from typing import Dict, List, Any
from collections import defaultdict

logger = logging.getLogger("aegis.intelligence.activity")


class ActivityIntelligence:
    """
    Activity intelligence engine.
    Analyzes historical data to find optimal timing for server activities.
    """

    def __init__(self):
        self._activity_data: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self._db_loaded_guilds: set = set()

    def _load_from_db(self, guild_id: str, days: int = 30):
        """Load activity data from the database for the given guild."""
        guild_id = str(guild_id)
        # Only clear if this is a fresh load — don't wipe runtime-recorded events
        # on subsequent calls. Use a separate flag set to track DB-loaded guilds.
        if guild_id not in self._db_loaded_guilds:
            if guild_id not in self._activity_data:
                self._activity_data[guild_id] = defaultdict(int)

            try:
                from aegis.analytics.engine import get_analytics_engine
                from aegis.db.analytics_models import MessageEvent
                
                ae = get_analytics_engine()
                if not ae or not ae._session_factory:
                    return
                    
                session = ae._session_factory()
                try:
                    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
                    rows = session.query(MessageEvent.timestamp).filter(
                        MessageEvent.guild_id == guild_id,
                        MessageEvent.timestamp >= cutoff
                    ).all()
                    
                    for (ts,) in rows:
                        if ts:
                            # Convert to UTC-aware datetime for local hour/weekday calculations if needed
                            if ts.tzinfo is None:
                                ts = ts.replace(tzinfo=datetime.timezone.utc)
                            key = f"{guild_id}:{ts.hour}:{ts.weekday()}"
                            self._activity_data[guild_id][key] += 1
                except Exception as e:
                    logger.error(f"Error loading activity from database for guild {guild_id}: {e}")
                finally:
                    session.close()
            except Exception as e:
                logger.error(f"Failed to fetch database engine: {e}")
            self._db_loaded_guilds.add(guild_id)

    def record_activity(self, guild_id: str, hour: int, day_of_week: int, activity_type: str = "message"):
        """Record activity for a specific hour and day."""
        key = f"{guild_id}:{hour}:{day_of_week}"
        self._activity_data[guild_id][key] += 1

    def analyze_activity(self, guild_id: str, days: int = 30) -> Dict[str, Any]:
        """
        Analyze activity patterns for a guild.
        
        Returns:
            Dict with peak times, dead zones, and recommendations.
        """
        guild_id = str(guild_id)
        self._load_from_db(guild_id, days)
        
        # Aggregate hourly activity
        hourly_activity = defaultdict(int)
        daily_activity = defaultdict(int)
        hourly_by_day = defaultdict(lambda: defaultdict(int))
        
        for key, count in self._activity_data.get(guild_id, {}).items():
            parts = key.split(":")
            if len(parts) == 3:
                hour = int(parts[1])
                day = int(parts[2])
                hourly_activity[hour] += count
                daily_activity[day] += count
                hourly_by_day[day][hour] += count
        
        # Find peak times
        peak_hour = max(hourly_activity.items(), key=lambda x: x[1])[0] if hourly_activity else 20
        peak_day = max(daily_activity.items(), key=lambda x: x[1])[0] if daily_activity else 5
        
        # Find dead zones (hours with very low activity)
        total_activity = sum(hourly_activity.values())
        avg_activity = total_activity / 24 if total_activity > 0 else 0
        dead_zones = [hour for hour in range(24) if hourly_activity.get(hour, 0) < avg_activity * 0.3]
        
        # Calculate activity distribution
        activity_distribution = {}
        for hour in range(24):
            count = hourly_activity.get(hour, 0)
            activity_distribution[hour] = count
        
        # Generate recommendations
        recommendations = self._generate_recommendations(hourly_activity, daily_activity, peak_hour, peak_day)
        
        return {
            "guild_id": guild_id,
            "peak_hour": peak_hour,
            "peak_day": peak_day,
            "peak_day_name": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][peak_day],
            "dead_zones": dead_zones,
            "activity_distribution": activity_distribution,
            "daily_activity": dict(daily_activity),
            "recommendations": recommendations,
            "best_event_time": f"{peak_hour}:00 on {['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'][peak_day]}",
            "best_giveaway_time": self._find_best_time_for_type(guild_id, "giveaway"),
            "best_announcement_time": self._find_best_time_for_type(guild_id, "announcement"),
        }

    def _generate_recommendations(self, hourly: Dict, daily: Dict, peak_hour: int, peak_day: int) -> List[Dict[str, Any]]:
        """Generate activity-based recommendations."""
        recommendations = []
        
        # Event timing recommendation
        if hourly:
            best_hours = sorted(hourly.items(), key=lambda x: x[1], reverse=True)[:3]
            recommendations.append({
                "type": "event_timing",
                "title": "Optimal Event Timing",
                "description": f"Server activity peaks at {best_hours[0][0]}:00. Consider hosting events during this time.",
                "confidence": 0.8,
            })
        
        # Giveaway timing
        recommendations.append({
            "type": "giveaway_timing",
            "title": "Giveaway Timing",
            "description": f"Schedule giveaways during peak hours ({peak_hour}:00) for maximum participation.",
            "confidence": 0.85,
        })
        
        # Announcement timing
        recommendations.append({
            "type": "announcement_timing",
            "title": "Announcement Timing",
            "description": f"Post announcements between {max(0, peak_hour-1)}:00 and {min(23, peak_hour+1)}:00 for 230% better visibility.",
            "confidence": 0.75,
        })
        
        # Dead zone warning
        if hourly:
            min_hour = min(hourly.items(), key=lambda x: x[1])
            if min_hour[1] < max(hourly.values()) * 0.2:
                recommendations.append({
                    "type": "dead_zone",
                    "title": "Dead Zone Detected",
                    "description": f"Activity drops significantly at {min_hour[0]}:00. Consider automated content during this time.",
                    "confidence": 0.7,
                })
        
        return recommendations

    def _find_best_time_for_type(self, guild_id: str, activity_type: str) -> str:
        """Find the best time for a specific activity type."""
        hourly_activity = defaultdict(int)
        daily_activity = defaultdict(int)

        for key, count in self._activity_data.get(guild_id, {}).items():
            parts = key.split(":")
            if len(parts) == 3:
                hour = int(parts[1])
                day = int(parts[2])
                hourly_activity[hour] += count
                daily_activity[day] += count

        peak_hour = max(hourly_activity.items(), key=lambda x: x[1])[0] if hourly_activity else 20
        peak_day = max(daily_activity.items(), key=lambda x: x[1])[0] if daily_activity else 5

        # Offset each type so they return distinct recommendations
        TYPE_HOUR_OFFSETS = {
            "giveaway": 0,        # exactly at peak
            "announcement": -1,   # 1 hour before peak (more visibility)
            "event": 1,           # 1 hour after peak
        }
        offset = TYPE_HOUR_OFFSETS.get(activity_type, 0)
        adjusted_hour = (peak_hour + offset) % 24

        day_name = ["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"][peak_day]
        ampm = "PM" if adjusted_hour >= 12 else "AM"
        hour_12 = adjusted_hour % 12 or 12
        return f"{hour_12} {ampm} on {day_name}"

    def get_activity_heatmap(self, guild_id: str) -> Dict[str, Any]:
        """Generate activity heatmap data."""
        guild_id = str(guild_id)
        self._load_from_db(guild_id, 30)
        
        heatmap = [[0] * 7 for _ in range(24)]
        
        for key, count in self._activity_data.get(guild_id, {}).items():
            parts = key.split(":")
            if len(parts) == 3:
                hour = int(parts[1])
                day = int(parts[2])
                heatmap[hour][day] = count
        
        return {
            "heatmap": heatmap,
            "max_value": max(max(row) for row in heatmap) if any(any(row) for row in heatmap) else 1,
        }

    def get_engagement_trends(self, guild_id: str) -> Dict[str, Any]:
        """Analyze engagement trends over time."""
        guild_id = str(guild_id)
        try:
            from aegis.analytics.engine import get_analytics_engine
            from aegis.db.analytics_models import MessageEvent
            
            ae = get_analytics_engine()
            if not ae or not ae._session_factory:
                return {"trend": "stable", "weekly_change": 0, "monthly_change": 0, "engagement_score": 75}
                
            session = ae._session_factory()
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                t_7d = now - datetime.timedelta(days=7)
                t_14d = now - datetime.timedelta(days=14)
                t_30d = now - datetime.timedelta(days=30)
                t_60d = now - datetime.timedelta(days=60)
                
                msgs_7d = session.query(MessageEvent).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= t_7d
                ).count()
                
                msgs_prev_7d = session.query(MessageEvent).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= t_14d,
                    MessageEvent.timestamp < t_7d
                ).count()
                
                msgs_30d = session.query(MessageEvent).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= t_30d
                ).count()
                
                msgs_prev_30d = session.query(MessageEvent).filter(
                    MessageEvent.guild_id == guild_id,
                    MessageEvent.timestamp >= t_60d,
                    MessageEvent.timestamp < t_30d
                ).count()
                
                weekly_change = round(((msgs_7d - msgs_prev_7d) / msgs_prev_7d) * 100, 1) if msgs_prev_7d > 0 else 0.0
                monthly_change = round(((msgs_30d - msgs_prev_30d) / msgs_prev_30d) * 100, 1) if msgs_prev_30d > 0 else 0.0
                
                engagement_score = 75
                if weekly_change > 0:
                    engagement_score = min(100, 75 + int(weekly_change / 2))
                elif weekly_change < 0:
                    engagement_score = max(0, 75 + int(weekly_change / 2))
                    
                trend = "stable"
                if weekly_change > 5:
                    trend = "up"
                elif weekly_change < -5:
                    trend = "down"
                    
                return {
                    "trend": trend,
                    "weekly_change": weekly_change,
                    "monthly_change": monthly_change,
                    "engagement_score": engagement_score
                }
            except Exception as e:
                logger.error(f"Error calculating engagement trends: {e}")
                return {"trend": "stable", "weekly_change": 0, "monthly_change": 0, "engagement_score": 75}
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to calculate engagement trends due to import/db error: {e}")
            return {"trend": "stable", "weekly_change": 0, "monthly_change": 0, "engagement_score": 75}
