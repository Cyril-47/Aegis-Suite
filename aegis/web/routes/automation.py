from fastapi import APIRouter, HTTPException, Request
from aegis.web.routes.dashboard import get_active_bot, parse_id

router = APIRouter()


@router.get("/api/guilds/{guild_id}/automation-center")
async def get_automation_center(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    # Check what automation features are active
    features = []
    config = {}

    try:
        from aegis.core.utils import get_guild_config
        config = get_guild_config(guild_id) if hasattr(get_guild_config, '__call__') else {}
    except Exception:
        pass

    # Auto-raid protection
    raid_cfg = config.get("anti_raid_settings", {})
    features.append({
        "name": "Anti-Raid Protection",
        "icon": "fa-shield-halved",
        "active": raid_cfg.get("enabled", False),
        "description": "Join burst detection and auto-response",
    })

    # Welcome system
    welcome_cfg = config.get("welcome_settings", {})
    features.append({
        "name": "Welcome Messages",
        "icon": "fa-door-open",
        "active": bool(welcome_cfg.get("channel_id")),
        "description": "Auto-greet new members with messages and roles",
    })

    # Auto-moderation
    automod_cfg = config.get("automod_settings", {})
    features.append({
        "name": "Auto-Moderation",
        "icon": "fa-gavel",
        "active": automod_cfg.get("enabled", False),
        "description": "Spam protection, link blocking, word filters",
    })

    # Ticket system
    ticket_cfg = config.get("ticket_settings", {})
    features.append({
        "name": "Support Tickets",
        "icon": "fa-ticket",
        "active": ticket_cfg.get("enabled", False),
        "description": "Ticket creation and management panels",
    })

    # Scheduled messages
    features.append({
        "name": "Scheduled Messages",
        "icon": "fa-clock",
        "active": config.get("scheduled_messages", []) != [],
        "description": "Automated timed announcements and broadcasts",
    })

    # Auto-responders
    features.append({
        "name": "Auto-Responders",
        "icon": "fa-robot",
        "active": config.get("auto_responders", []) != [],
        "description": "Keyword-triggered automatic replies",
    })

    # Nightly backups
    features.append({
        "name": "Nightly Backups",
        "icon": "fa-box-archive",
        "active": True,
        "description": "Automatic database backup every night",
    })

    active_count = sum(1 for f in features if f["active"])

    return {
        "features": features,
        "active_count": active_count,
        "total_count": len(features),
    }


@router.get("/api/trend-forecast/{guild_id}")
async def get_trend_forecast(guild_id: str, days: int = 30):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.db.analytics_models import DailySnapshot

    engine = _get_analytics_engine()
    session = engine._session_factory()

    try:
        snapshots = session.query(DailySnapshot).filter(
            DailySnapshot.guild_id == guild_id,
        ).order_by(DailySnapshot.date.desc()).limit(days).all()

        if len(snapshots) < 3:
            session.close()
            return {"forecasts": [], "message": "Not enough data for forecasting (need at least 3 days)."}

        snapshots.reverse()

        # Simple linear regression for messages
        msgs = [s.total_messages for s in snapshots]
        active = [s.unique_active_users for s in snapshots]
        joins = [s.new_members for s in snapshots]

        msg_forecast = _linear_forecast(msgs, 7)
        active_forecast = _linear_forecast(active, 7)
        join_forecast = _linear_forecast(joins, 7)

        session.close()

        return {
            "forecasts": [
                {"metric": "Messages/day", "current": msgs[-1], "forecast_7d": msg_forecast, "trend": "up" if msg_forecast > msgs[-1] else "down"},
                {"metric": "Active Users", "current": active[-1], "forecast_7d": active_forecast, "trend": "up" if active_forecast > active[-1] else "down"},
                {"metric": "Daily Joins", "current": joins[-1], "forecast_7d": join_forecast, "trend": "up" if join_forecast > joins[-1] else "down"},
            ],
        }
    except Exception:
        session.close()
        return {"forecasts": [], "message": "Error computing forecast."}


def _linear_forecast(values, future_days):
    """Simple linear regression forecast."""
    n = len(values)
    if n < 2:
        return values[-1] if values else 0
    x_mean = (n - 1) / 2
    y_mean = sum(values) / n
    num = sum((i - x_mean) * (v - y_mean) for i, v in enumerate(values))
    den = sum((i - x_mean) ** 2 for i in range(n))
    slope = num / den if den != 0 else 0
    intercept = y_mean - slope * x_mean
    return max(0, int(intercept + slope * (n - 1 + future_days)))


def _get_analytics_engine():
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Analytics engine not available")
    return engine


@router.get("/api/guilds/{guild_id}/slowmode/status")
async def get_slowmode_status(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    from aegis.bot.slowmode_tracker import slowmode_tracker
    import aegis.core.utils as utils
    config = utils.load_config()
    slowmode_settings = utils.get_guild_slowmode_settings(config, guild_id)

    rates = slowmode_tracker.get_status()

    channels = []
    for ch in guild.text_channels:
        ch_id = str(ch.id)
        ch_rate = rates.get(ch_id, {"rate": 0, "count_10s": 0})
        channels.append({
            "id": ch_id,
            "name": ch.name,
            "current_slowmode": ch.slowmode_delay,
            "message_rate": round(ch_rate["rate"], 1),
            "messages_10s": ch_rate["count_10s"],
        })

    return {
        "settings": slowmode_settings,
        "channels": channels,
    }


@router.get("/api/maintenance/settings")
async def get_maintenance_settings():
    import aegis.core.utils as utils
    config = utils.load_config()
    return {
        "backup_settings": config.get("backup_settings", {}),
        "maintenance_settings": config.get("maintenance_settings", {}),
    }


@router.post("/api/maintenance/settings")
async def save_maintenance_settings(request: Request):
    body = await request.json()
    import aegis.core.utils as utils
    config = utils.load_config()
    if "backup_settings" in body:
        config["backup_settings"] = body["backup_settings"]
    if "maintenance_settings" in body:
        config["maintenance_settings"] = body["maintenance_settings"]
    utils.save_config(config)
    return {"status": "saved"}
