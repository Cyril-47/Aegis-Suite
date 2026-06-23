from fastapi import APIRouter, HTTPException, Request
import aegis.core.auth as auth

router = APIRouter()


def _require_auth(request: Request):
    """Validate auth and return (token, role, guild_id)."""
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    if not token or not auth.validate_session(token):
        raise HTTPException(status_code=401, detail="Unauthorized")
    role = auth.get_session_role(token)
    guild_id = auth.get_session_guild_id(token)
    return token, role, guild_id


def _require_guild_access(request: Request, guild_id: str):
    """Validate auth and ensure the user has access to the specified guild."""
    token, role, session_guild_id = _require_auth(request)
    if role == "tenant" and session_guild_id != guild_id:
        raise HTTPException(status_code=403, detail="Forbidden: Session not authorized for this server")
    return token, role


# Recommendations Endpoint

@router.get("/api/guilds/{guild_id}/intelligence/recommendations")
async def get_recommendations(guild_id: str, request: Request):
    _require_guild_access(request, guild_id)
    from aegis.analytics.recommender import get_recommendation_summary
    return get_recommendation_summary(guild_id)


# Benchmark Endpoint

@router.get("/api/guilds/{guild_id}/intelligence/benchmark")
async def get_benchmark(guild_id: str, request: Request):
    _require_guild_access(request, guild_id)
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        return {"available": False}
    return engine.get_benchmark_comparison(guild_id)


# Health Timeline Endpoint

@router.get("/api/guilds/{guild_id}/intelligence/health-timeline")
async def get_health_timeline(guild_id: str, request: Request, days: int = 30):
    _require_guild_access(request, guild_id)
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        return []
    return engine.get_health_timeline(guild_id, days=days)
