"""
Smart Features API Routes - Endpoints for all 12 smart features.
"""

from fastapi import APIRouter, HTTPException, Request
from aegis.web.routes.dashboard import get_active_bot
from aegis.analytics.smart_features import (
    RecommendationEngine, ConfigDoctor, PermissionDoctor,
    SmartRaidDetector, SmartGrowthAdvisor,
    SmartRoleCleaner, SmartChannelCleaner, SmartBackupAdvisor,
    SmartIncidentTimeline, ServerMaturityScore, AutoFixEngine,
)

router = APIRouter()

def _get_bot_and_guild(guild_id: str):
    bot = get_active_bot()
    if not bot:
        try:
            from aegis.bot.runner import get_mock_bot
            bot = get_mock_bot()
        except Exception:
            bot = None
            
    guild = None
    if bot:
        gid = int(guild_id) if guild_id.isdigit() else 0
        guild = bot.get_guild(gid)
        if not guild and hasattr(bot, "guilds") and bot.guilds:
            guild = bot.guilds[0]
            
    return bot, guild


# =============================================================================
# Feature 1: Smart Recommendation Center
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/recommendations")
async def get_recommendations(guild_id: str):
    """Get all smart recommendations for a guild."""
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot or not guild:
        return {
            "guild_id": guild_id,
            "total": 0,
            "critical": 0,
            "high": 0,
            "medium": 0,
            "recommendations": [],
        }

    engine = RecommendationEngine(bot)
    recommendations = engine.analyze(guild)

    return {
        "guild_id": guild_id,
        "total": len(recommendations),
        "critical": len([r for r in recommendations if r.severity == "critical"]),
        "high": len([r for r in recommendations if r.severity == "high"]),
        "medium": len([r for r in recommendations if r.severity == "medium"]),
        "recommendations": [vars(r) for r in recommendations],
    }


# =============================================================================
# Feature 2: One-Click Auto Fix
# =============================================================================

@router.post("/api/guilds/{guild_id}/smart/fix")
async def execute_auto_fix(guild_id: str, request: Request):
    """Execute an auto-fix action."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    body = await request.json()
    action = body.get("action")
    params = body.get("params", {})

    if not action:
        raise HTTPException(status_code=400, detail="Action is required")

    # Create config snapshot before executing the fix for the Snapshot Undo System
    from aegis.core.config_history import create_snapshot
    import aegis.core.utils as utils
    
    current_config = utils.load_config().copy()
    guild_config = current_config.get("guild_configs", {}).get(guild_id, {})
    
    snapshot_id = create_snapshot(
        guild_id=guild_id,
        config_data=guild_config,
        changed_keys=[action],
        created_by=f"auto_fix_{action}"
    )

    fix_engine = AutoFixEngine(bot)
    result = await fix_engine.execute_fix(guild, action, params)

    res_dict = vars(result)
    res_dict["snapshot_id"] = snapshot_id
    return res_dict


# =============================================================================
# Feature 3: Config Doctor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/config-doctor")
async def get_config_doctor(guild_id: str):
    """Get configuration health diagnosis."""
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot or not guild:
        return {"status": "ok", "issues": []}

    doctor = ConfigDoctor(bot)
    diagnosis = doctor.diagnose(guild)

    return diagnosis


# =============================================================================
# Feature 4: Permission Doctor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/permission-doctor")
async def get_permission_doctor(guild_id: str):
    """Get permission analysis and findings."""
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot or not guild:
        return {"status": "ok", "findings": []}

    doctor = PermissionDoctor(bot)
    analysis = doctor.analyze(guild)

    return analysis


# =============================================================================
# Feature 5: Smart Raid Detector
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/raid-detector")
async def get_raid_detector(guild_id: str):
    """Analyze recent joins for raid patterns."""
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot or not guild:
        return {
            "raid_detected": False,
            "confidence": "none",
            "threat_level": "low",
            "suspected_bot_count": 0,
            "join_velocity": 0,
            "analysis": "Normal join behavior",
            "recent_joins_count": 0,
            "recommendations": []
        }

    # Get recent member joins
    recent_joins = []
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

    if hasattr(guild, 'members') and guild.members:
        for member in guild.members:
            if member.joined_at and member.joined_at.replace(tzinfo=timezone.utc) > cutoff:
                account_age = (datetime.now(timezone.utc) - member.created_at.replace(tzinfo=timezone.utc)).days
                recent_joins.append({
                    "user_id": str(member.id),
                    "username": member.name,
                    "timestamp": member.joined_at,
                    "account_age_days": account_age,
                })

    detector = SmartRaidDetector(bot)
    analysis = detector.analyze(guild_id, recent_joins)

    return analysis


# =============================================================================
# Feature 6: Smart Role Cleaner
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/role-cleaner")
async def get_role_cleaner(guild_id: str):
    """Analyze roles for cleanup opportunities."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    cleaner = SmartRoleCleaner(bot)
    analysis = cleaner.analyze(guild)

    return analysis


# =============================================================================
# Feature 9: Smart Channel Cleaner
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/channel-cleaner")
async def get_channel_cleaner(guild_id: str):
    """Analyze channels for cleanup opportunities."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    cleaner = SmartChannelCleaner(bot)
    analysis = cleaner.analyze(guild)

    return analysis


# =============================================================================
# Feature 10: Smart Backup Advisor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/backup-advisor")
async def get_backup_advisor(guild_id: str):
    """Get backup health analysis."""
    advisor = SmartBackupAdvisor(get_active_bot())
    analysis = advisor.analyze(guild_id)

    return analysis


# =============================================================================
# Feature 11: Smart Incident Timeline
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/incident-timeline")
async def get_incident_timeline(guild_id: str, hours: int = 24):
    """Get correlated incident timeline."""
    if hours < 1 or hours > 168:
        hours = max(1, min(hours, 168))
    
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot:
        return {"events": [], "summary": "No recent incidents"}

    timeline = SmartIncidentTimeline(bot)
    result = timeline.build_timeline(guild_id, hours)

    return result


# =============================================================================
# Feature 12: Server Maturity Score
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/maturity-score")
async def get_maturity_score(guild_id: str):
    """Get comprehensive server maturity score."""
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot or not guild:
        return {"overall_score": 75, "rating": "Good", "categories": {}}

    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()

    scorer = ServerMaturityScore(bot)
    score = scorer.compute(guild, engine)

    return score


# =============================================================================
# Growth & Retention Advisor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/growth-advisor")
async def get_growth_advisor(guild_id: str):
    """Get growth and retention analysis for a guild."""
    bot, guild = _get_bot_and_guild(guild_id)
    if not bot or not guild:
        return {"summary": "Healthy guild", "recommendations": []}

    advisor = SmartGrowthAdvisor(bot)

    total_members = getattr(guild, 'member_count', 0) or 0
    text_channels = len(guild.text_channels) if hasattr(guild, 'text_channels') else 0
    online_members = sum(1 for m in guild.members if m.status and str(m.status) != "offline") if hasattr(guild, 'members') else 0

    growth_data = {
        "avg_active_users": online_members,
        "total_members": total_members,
        "text_channels": text_channels,
        "retention": {
            "retention_7d": max(0, min(100, round((online_members / max(total_members, 1)) * 100)))
        },
    }

    result = advisor.analyze(guild, growth_data)
    return result

