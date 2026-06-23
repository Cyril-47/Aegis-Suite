from fastapi import APIRouter, HTTPException
from datetime import datetime, timedelta, timezone
from aegis.web.routes.dashboard import get_active_bot

router = APIRouter()


@router.get("/api/guilds/{guild_id}/ticket-intelligence")
async def get_ticket_intelligence(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import ModerationEvent

    engine = _get_analytics_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    session = engine._session_factory()

    # Ticket events (tracked as moderation events with category "ticket")
    try:
        ticket_events = session.query(ModerationEvent).filter(
            ModerationEvent.guild_id == guild_id,
            ModerationEvent.timestamp >= cutoff,
            ModerationEvent.automod_category == "ticket",
        ).all()

        total_tickets = len(ticket_events)
        opened = sum(1 for e in ticket_events if e.event_type == "ticket_opened")
        closed = sum(1 for e in ticket_events if e.event_type == "ticket_closed")

        # Staff performance (by moderator_id)
        staff = {}
        for e in ticket_events:
            if e.moderator_id:
                if e.moderator_id not in staff:
                    staff[e.moderator_id] = {"handled": 0, "closed": 0}
                staff[e.moderator_id]["handled"] += 1
                if e.event_type == "ticket_closed":
                    staff[e.moderator_id]["closed"] += 1
    except Exception:
        total_tickets = 0
        opened = 0
        closed = 0
        staff = {}

    session.close()

    return {
        "total_tickets": total_tickets,
        "opened": opened,
        "closed": closed,
        "open_rate": f"{(opened / total_tickets * 100):.0f}%" if total_tickets else "0%",
        "staff": [{"user_id": k, **v} for k, v in staff.items()],
    }


@router.get("/api/guilds/{guild_id}/moderator-intelligence")
async def get_moderator_intelligence(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import ModerationEvent

    engine = _get_analytics_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    session = engine._session_factory()

    try:
        mod_events = session.query(ModerationEvent).filter(
            ModerationEvent.guild_id == guild_id,
            ModerationEvent.timestamp >= cutoff,
            ModerationEvent.event_type.in_(["ban", "kick", "timeout", "warn"]),
        ).all()

        # Aggregate by moderator
        mods = {}
        for e in mod_events:
            mid = e.moderator_id or "automod"
            if mid not in mods:
                mods[mid] = {"bans": 0, "kicks": 0, "timeouts": 0, "warns": 0, "total": 0}
            if e.event_type == "ban":
                mods[mid]["bans"] += 1
            elif e.event_type == "kick":
                mods[mid]["kicks"] += 1
            elif e.event_type == "timeout":
                mods[mid]["timeouts"] += 1
            elif e.event_type == "warn":
                mods[mid]["warns"] += 1
            mods[mid]["total"] += 1

        # Sort by total actions
        leaderboard = sorted([{"moderator_id": k, **v} for k, v in mods.items()], key=lambda x: x["total"], reverse=True)

        total_actions = len(mod_events)
    except Exception:
        leaderboard = []
        total_actions = 0

    session.close()

    return {"total_actions": total_actions, "leaderboard": leaderboard[:20]}


@router.get("/api/guilds/{guild_id}/growth-center")
async def get_growth_center(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import DailySnapshot

    engine = _get_analytics_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    session = engine._session_factory()

    try:
        snapshots = session.query(DailySnapshot).filter(
            DailySnapshot.guild_id == guild_id,
            DailySnapshot.date >= cutoff.date() if hasattr(cutoff, 'date') else cutoff,
        ).order_by(DailySnapshot.date).all()

        total_joins = sum(s.new_members for s in snapshots)
        total_leaves = sum(s.left_members for s in snapshots)
        net_growth = total_joins - total_leaves
        avg_active = sum(s.unique_active_users for s in snapshots) // max(len(snapshots), 1)

        daily = []
        for s in snapshots:
            daily.append({
                "date": s.date.isoformat() if hasattr(s.date, 'isoformat') else str(s.date),
                "joins": s.new_members,
                "leaves": s.left_members,
                "active_users": s.unique_active_users,
            })
    except Exception:
        total_joins = 0
        total_leaves = 0
        net_growth = 0
        avg_active = 0
        daily = []

    session.close()

    return {
        "total_joins": total_joins,
        "total_leaves": total_leaves,
        "net_growth": net_growth,
        "avg_active_users": avg_active,
        "daily": daily,
    }


@router.get("/api/guilds/{guild_id}/retention")
async def get_retention(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import MemberEvent

    engine = _get_analytics_session()
    session = engine._session_factory()

    try:
        now = datetime.now(timezone.utc)
        day1 = now - timedelta(days=1)
        day7 = now - timedelta(days=7)
        day30 = now - timedelta(days=30)

        joins_1d = session.query(MemberEvent).filter(
            MemberEvent.guild_id == guild_id,
            MemberEvent.event_type == "join",
            MemberEvent.timestamp >= day1,
        ).count()
        joins_7d = session.query(MemberEvent).filter(
            MemberEvent.guild_id == guild_id,
            MemberEvent.event_type == "join",
            MemberEvent.timestamp >= day7,
        ).count()
        joins_30d = session.query(MemberEvent).filter(
            MemberEvent.guild_id == guild_id,
            MemberEvent.event_type == "join",
            MemberEvent.timestamp >= day30,
        ).count()

        leaves_1d = session.query(MemberEvent).filter(
            MemberEvent.guild_id == guild_id,
            MemberEvent.event_type == "leave",
            MemberEvent.timestamp >= day1,
        ).count()
        leaves_7d = session.query(MemberEvent).filter(
            MemberEvent.guild_id == guild_id,
            MemberEvent.event_type == "leave",
            MemberEvent.timestamp >= day7,
        ).count()
        leaves_30d = session.query(MemberEvent).filter(
            MemberEvent.guild_id == guild_id,
            MemberEvent.event_type == "leave",
            MemberEvent.timestamp >= day30,
        ).count()

        def ret(joined, left):
            return max(0, round((1 - left / max(joined, 1)) * 100)) if joined > 0 else 100

        session.close()

        return {
            "retention_1d": ret(joins_1d, leaves_1d),
            "retention_7d": ret(joins_7d, leaves_7d),
            "retention_30d": ret(joins_30d, leaves_30d),
            "joins_1d": joins_1d, "joins_7d": joins_7d, "joins_30d": joins_30d,
            "leaves_1d": leaves_1d, "leaves_7d": leaves_7d, "leaves_30d": leaves_30d,
        }
    except Exception:
        session.close()
        return {"retention_1d": 0, "retention_7d": 0, "retention_30d": 0}


@router.get("/api/guilds/{guild_id}/permission-heatmap")
async def get_permission_heatmap(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id) if guild_id.isdigit() else 0)
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    PERM_MAPPING = {
        "Administrator": "administrator",
        "Manage Server": "manage_guild",
        "Manage Roles": "manage_roles",
        "Manage Channels": "manage_channels",
        "Ban Members": "ban_members",
        "Kick Members": "kick_members",
        "Manage Messages": "manage_messages",
        "Timeout": "moderate_members",
        "Send Messages": "send_messages",
        "View Channels": "view_channel",
        "Connect": "connect",
        "Speak": "speak",
    }

    roles_data = []
    for role in guild.roles:
        if role.is_default():
            continue
        perm_flags = {}
        for display_name, attr_name in PERM_MAPPING.items():
            perm_flags[display_name] = getattr(role.permissions, attr_name, False)
        roles_data.append({
            "id": str(role.id),
            "name": role.name,
            "color": f"#{role.color.value:06X}" if role.color.value else "#99AAB5",
            "permissions": perm_flags,
        })

    return {"roles": roles_data, "perm_names": list(PERM_MAPPING.keys())}


@router.get("/api/guilds/{guild_id}/mod-response-times")
async def get_mod_response_times(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import ModerationEvent

    engine = _get_analytics_session()
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    session = engine._session_factory()

    try:
        events = session.query(ModerationEvent).filter(
            ModerationEvent.guild_id == guild_id,
            ModerationEvent.timestamp >= cutoff,
            ModerationEvent.event_type.in_(["ban", "kick", "timeout", "warn"]),
        ).order_by(ModerationEvent.timestamp).all()

        # Group by moderator and compute average time between events
        mod_actions = {}
        for e in events:
            mid = e.moderator_id or "automod"
            if mid not in mod_actions:
                mod_actions[mid] = []
            mod_actions[mid].append(e.timestamp)

        leaderboard = []
        for mid, timestamps in mod_actions.items():
            if len(timestamps) < 2:
                avg_gap = 0
            else:
                gaps = [(timestamps[i+1] - timestamps[i]).total_seconds() for i in range(len(timestamps)-1)]
                avg_gap = sum(gaps) / len(gaps) / 60  # minutes

            leaderboard.append({
                "moderator_id": mid,
                "total_actions": len(timestamps),
                "avg_gap_minutes": round(avg_gap, 1),
            })

        leaderboard.sort(key=lambda x: x["total_actions"], reverse=True)
        session.close()

        return {"leaderboard": leaderboard[:20]}
    except Exception:
        session.close()
        return {"leaderboard": []}


def _get_analytics_session():
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Analytics engine not available")
    return engine
