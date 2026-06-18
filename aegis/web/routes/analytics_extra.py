from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from aegis.web.routes.dashboard import get_active_bot

router = APIRouter()


@router.get("/api/guilds/{guild_id}/channel-heatmap")
async def get_channel_heatmap(guild_id: str, days: int = 14):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import MessageEvent

    engine = _get_engine()
    session = engine._session_factory()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        events = session.query(MessageEvent).filter(
            MessageEvent.guild_id == guild_id,
            MessageEvent.timestamp >= cutoff,
        ).all()

        # Build 24x7 heatmap (hour x day_of_week)
        heatmap = [[0] * 7 for _ in range(24)]
        for e in events:
            if e.timestamp:
                hour = e.timestamp.hour
                dow = e.timestamp.weekday()
                heatmap[hour][dow] += 1

        session.close()
        return {"heatmap": heatmap, "days": days}
    except Exception:
        session.close()
        return {"heatmap": [[0] * 7 for _ in range(24)], "days": days}


@router.get("/api/guilds/{guild_id}/ticket-sla")
async def get_ticket_sla(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import ModerationEvent

    engine = _get_engine()
    session = engine._session_factory()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    try:
        opens = session.query(ModerationEvent).filter(
            ModerationEvent.guild_id == guild_id,
            ModerationEvent.event_type == "ticket_opened",
            ModerationEvent.timestamp >= cutoff,
        ).order_by(ModerationEvent.timestamp).all()

        closes = session.query(ModerationEvent).filter(
            ModerationEvent.guild_id == guild_id,
            ModerationEvent.event_type == "ticket_closed",
            ModerationEvent.timestamp >= cutoff,
        ).order_by(ModerationEvent.timestamp).all()

        total = len(opens)
        closed = len(closes)

        # Compute average resolution time
        avg_resolution = 0
        if opens and closes:
            # Simple: avg time between consecutive open/close pairs
            times = []
            for o in opens:
                for c in closes:
                    if c.timestamp and o.timestamp and c.timestamp > o.timestamp:
                        diff = (c.timestamp - o.timestamp).total_seconds() / 3600
                        times.append(diff)
                        break
            if times:
                avg_resolution = round(sum(times) / len(times), 1)

        # Staff metrics
        staff = {}
        for c in closes:
            mid = c.moderator_id or "unknown"
            if mid not in staff:
                staff[mid] = {"resolved": 0, "total_time": 0}
            staff[mid]["resolved"] += 1

        session.close()

        return {
            "total_opened": total,
            "total_closed": closed,
            "open_rate": f"{((total - closed) / max(total, 1) * 100):.0f}%",
            "avg_resolution_hours": avg_resolution,
            "staff": [{"user_id": k, **v} for k, v in staff.items()],
        }
    except Exception:
        session.close()
        return {"total_opened": 0, "total_closed": 0, "open_rate": "0%", "avg_resolution_hours": 0, "staff": []}


@router.get("/api/guilds/{guild_id}/growth-recommendations")
async def get_growth_recommendations(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import DailySnapshot

    engine = _get_engine()
    session = engine._session_factory()

    recommendations = []

    try:
        snapshots = session.query(DailySnapshot).filter(
            DailySnapshot.guild_id == guild_id,
        ).order_by(DailySnapshot.date.desc()).limit(14).all()

        if not snapshots:
            recommendations.append({"type": "info", "title": "No analytics data yet", "description": "Enable event tracking to get recommendations.", "impact": "Start tracking"})
            session.close()
            return {"recommendations": recommendations}

        recent = snapshots[:7]
        older = snapshots[7:14] if len(snapshots) >= 14 else snapshots

        # Check retention
        total_recent_joins = sum(s.new_members for s in recent)
        total_recent_leaves = sum(s.left_members for s in recent)
        if total_recent_joins > 0:
            retention = (1 - total_recent_leaves / total_recent_joins) * 100
            if retention < 50:
                recommendations.append({
                    "type": "warning",
                    "title": "Low retention rate",
                    "description": f"Only {retention:.0f}% of new members stay. Consider enabling welcome messages and auto-roles.",
                    "impact": "+15 retention"
                })

        # Check activity trend
        recent_msgs = sum(s.total_messages for s in recent) / max(len(recent), 1)
        older_msgs = sum(s.total_messages for s in older) / max(len(older), 1) if older else recent_msgs
        if older_msgs > 0 and recent_msgs < older_msgs * 0.7:
            recommendations.append({
                "type": "warning",
                "title": "Activity declining",
                "description": f"Messages dropped {((1 - recent_msgs/older_msgs) * 100):.0f}%. Schedule events or add engagement features.",
                "impact": "+10 engagement"
            })

        # Check if welcome is configured
        try:
            from aegis.core.utils import get_guild_config
            config = get_guild_config(guild_id)
            if not config.get("welcome_settings", {}).get("channel_id"):
                recommendations.append({
                    "type": "info",
                    "title": "Welcome messages not configured",
                    "description": "Enable welcome messages to greet new members and improve retention.",
                    "impact": "+7 retention"
                })
        except Exception:
            pass

        # Check peak activity times
        if recent:
            recommendations.append({
                "type": "info",
                "title": "Schedule events during peak hours",
                "description": "Based on your activity data, schedule events when members are most active.",
                "impact": "+5 engagement"
            })

    except Exception:
        pass

    session.close()

    if not recommendations:
        recommendations.append({"type": "success", "title": "Server looks healthy!", "description": "No critical recommendations at this time.", "impact": "Maintain"})

    return {"recommendations": recommendations}


@router.get("/api/guilds/{guild_id}/benchmark")
async def get_benchmark(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        return {"percentile": {}, "total_servers": 0, "message": "Analytics engine not available."}

    try:
        comparison = engine.get_benchmark_comparison(guild_id)
        return comparison
    except Exception:
        return {"percentile": {}, "total_servers": 0, "message": "Not enough data for benchmarking."}


def _get_engine():
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Analytics engine not available")
    return engine
