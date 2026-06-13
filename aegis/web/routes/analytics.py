from fastapi import APIRouter, HTTPException
from aegis.analytics.engine import get_analytics_engine

router = APIRouter(prefix="/api/guilds/{guild_id}/analytics", tags=["analytics"])


def _get_engine():
    engine = get_analytics_engine()
    if engine is None:
        raise HTTPException(status_code=503, detail="Analytics engine not initialized")
    return engine


def _resolve_channel_name(guild_id: str, channel_id: str) -> str:
    try:
        from aegis.web.routes.dashboard import get_active_bot
        bot = get_active_bot()
        if bot:
            guild = bot.get_guild(int(guild_id))
            if guild:
                channel = guild.get_channel(int(channel_id))
                if channel:
                    return channel.name
    except Exception:
        pass
    return channel_id


def _resolve_username(guild_id: str, user_id: str) -> str:
    try:
        from aegis.web.routes.dashboard import get_active_bot
        bot = get_active_bot()
        if bot:
            guild = bot.get_guild(int(guild_id))
            if guild:
                member = guild.get_member(int(user_id))
                if member:
                    return member.display_name or member.name
                # Fallback to general user lookup
                user = bot.get_user(int(user_id))
                if user:
                    return user.name
    except Exception:
        pass
    return f"User {user_id}"


@router.get("/overview")
async def analytics_overview(guild_id: str):
    engine = _get_engine()
    return engine.get_overview(guild_id)


@router.get("/messages")
async def analytics_messages(guild_id: str, days: int = 30):
    engine = _get_engine()
    return engine.get_daily_stats(guild_id, days=days)


@router.get("/channels")
async def analytics_channels(guild_id: str, days: int = 7):
    engine = _get_engine()
    raw = engine.get_channel_activity(guild_id, days=days)
    resolved = {}
    for ch_id, count in raw.items():
        name = _resolve_channel_name(guild_id, ch_id)
        resolved[name] = count
    return resolved


@router.get("/members")
async def analytics_members(guild_id: str):
    engine = _get_engine()
    return engine.get_member_retention(guild_id, days=30)


@router.get("/voice")
async def analytics_voice(guild_id: str, days: int = 7):
    engine = _get_engine()
    leaders = engine.get_voice_leaders(guild_id, days=days)
    for leader in leaders:
        leader["username"] = _resolve_username(guild_id, leader["user_id"])
    return leaders


@router.get("/moderation")
async def analytics_moderation(guild_id: str, days: int = 7):
    engine = _get_engine()
    return engine.get_mod_summary(guild_id, days=days)


@router.get("/top-users")
async def analytics_top_users(guild_id: str, days: int = 7, limit: int = 20):
    engine = _get_engine()
    users = engine.get_top_users(guild_id, days=days, limit=limit)
    for u in users:
        u["username"] = _resolve_username(guild_id, u["user_id"])
    return users
