from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from aegis.web.routes.dashboard import get_active_bot, parse_id

router = APIRouter()


def _get_analytics_session():
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Analytics engine not available")
    return engine


@router.get("/api/guilds/{guild_id}/incidents")
async def get_incidents(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import ModerationEvent
    from aegis.db.models import RaidEvent

    engine = _get_analytics_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    incidents = []

    # Raid events
    try:
        session = engine._session_factory()
        raids = session.query(RaidEvent).filter(
            RaidEvent.guild_id == guild_id,
            RaidEvent.detected_at >= cutoff,
        ).order_by(RaidEvent.detected_at.desc()).limit(50).all()

        for r in raids:
            incidents.append({
                "id": r.id,
                "type": "raid",
                "severity": "critical",
                "title": f"Raid detected — {r.join_count} joins in {r.window_seconds}s",
                "action_taken": r.response_action,
                "timestamp": r.detected_at.isoformat() if r.detected_at else None,
                "resolved": bool(r.resolved),
            })
        session.close()
    except Exception:
        pass

    # Moderation events
    try:
        session = engine._session_factory()
        mods = session.query(ModerationEvent).filter(
            ModerationEvent.guild_id == guild_id,
            ModerationEvent.timestamp >= cutoff,
            ModerationEvent.event_type.in_(["ban", "kick", "timeout", "warn", "spam_detected"]),
        ).order_by(ModerationEvent.timestamp.desc()).limit(50).all()

        for m in mods:
            sev = "warning"
            if m.event_type in ("ban", "kick"):
                sev = "high"
            elif m.event_type == "timeout":
                sev = "medium"

            incidents.append({
                "id": m.id,
                "type": m.event_type,
                "severity": sev,
                "title": f"{m.event_type.replace('_', ' ').title()}: User {m.user_id}",
                "reason": m.reason or "",
                "timestamp": m.timestamp.isoformat() if m.timestamp else None,
                "resolved": True,
            })
        session.close()
    except Exception:
        pass

    # Sort by timestamp descending
    incidents.sort(key=lambda x: x.get("timestamp") or "", reverse=True)

    # Stats
    critical = sum(1 for i in incidents if i["severity"] == "critical")
    high = sum(1 for i in incidents if i["severity"] == "high")
    medium = sum(1 for i in incidents if i["severity"] == "medium")
    warning = sum(1 for i in incidents if i["severity"] == "warning")

    return {
        "incidents": incidents[:50],
        "stats": {"total": len(incidents), "critical": critical, "high": high, "medium": medium, "warning": warning},
    }


@router.get("/api/guilds/{guild_id}/cleanup-preview")
async def get_cleanup_preview(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    unused_roles = []
    empty_channels = []
    empty_categories = []

    # Unused roles (0 members, not @everyone, not managed)
    for role in guild.roles:
        if role.is_default() or role.managed:
            continue
        if len(role.members) == 0:
            unused_roles.append({"id": str(role.id), "name": role.name, "color": f"#{role.color.value:06X}" if role.color.value else "#99AAB5"})

    # Empty channels (no messages — approximated by no recent activity)
    for ch in guild.text_channels:
        if len(ch.members) <= 1:  # Only bot or nobody
            empty_channels.append({"id": str(ch.id), "name": ch.name, "type": "text"})

    # Empty categories
    for cat in guild.categories:
        if len(cat.channels) == 0:
            empty_categories.append({"id": str(cat.id), "name": cat.name})

    score = 100
    score -= len(unused_roles) * 3
    score -= len(empty_channels) * 2
    score -= len(empty_categories) * 2
    score = max(0, score)

    return {
        "unused_roles": unused_roles,
        "empty_channels": empty_channels,
        "empty_categories": empty_categories,
        "cleanup_score": score,
        "potential_improvement": 100 - score,
    }


@router.delete("/api/guilds/{guild_id}/cleanup/role/{role_id}")
async def cleanup_delete_role(guild_id: str, role_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    role = guild.get_role(parse_id(role_id, "role_id"))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found")

    if role.managed or role.is_default():
        raise HTTPException(status_code=400, detail="Cannot delete this role.")

    try:
        await role.delete(reason="Cleanup Wizard — unused role")
        from aegis.core import audit_log
        audit_log.log_action("admin", "CLEANUP_ACTION", f"Deleted unused role '{role.name}'", guild_id)
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
