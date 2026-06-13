from fastapi import APIRouter, HTTPException, Request
import aegis.core.utils as utils
import aegis.core.auth as auth
from aegis.core.config_history import create_snapshot, get_history, get_snapshot

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


# Config History Endpoints

@router.get("/api/guilds/{guild_id}/config/history")
async def get_config_history(guild_id: str, request: Request, limit: int = 20, offset: int = 0):
    token, role = _require_guild_access(request, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access configuration history")
    return get_history(guild_id, limit=limit, offset=offset)


@router.get("/api/guilds/{guild_id}/config/history/{snapshot_id}")
async def get_config_snapshot(guild_id: str, snapshot_id: int, request: Request):
    token, role = _require_guild_access(request, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can access configuration snapshots")
    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if snapshot.get("guild_id") != guild_id:
        raise HTTPException(status_code=403, detail="Snapshot does not belong to this server")
    return snapshot


@router.post("/api/guilds/{guild_id}/config/history/{snapshot_id}/rollback")
async def rollback_config(guild_id: str, snapshot_id: int, request: Request):
    token, role = _require_guild_access(request, guild_id)
    if role != "admin":
        raise HTTPException(status_code=403, detail="Only admins can rollback")

    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found")
    if snapshot.get("guild_id") != guild_id:
        raise HTTPException(status_code=403, detail="Snapshot does not belong to this server")

    # Create snapshot of current state before rollback
    current_config = utils.load_config().copy()
    guild_config = current_config.get("guild_configs", {}).get(guild_id, {})
    create_snapshot(guild_id, guild_config, changed_keys=[], created_by="rollback_pre")

    # Apply rollback
    with utils.config_lock:
        config = utils.load_config()
        config.setdefault("guild_configs", {})[guild_id] = snapshot["config"]
        utils.save_config(config)

    return {"status": "success", "rolled_back_to": snapshot_id}


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
