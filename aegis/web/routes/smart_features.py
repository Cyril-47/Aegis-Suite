"""
Smart Features API Routes - Endpoints for all 12 smart features.
"""

from fastapi import APIRouter, HTTPException, Request
from aegis.web.routes.dashboard import get_active_bot
from aegis.analytics.smart_features import (
    RecommendationEngine, ConfigDoctor, PermissionDoctor,
    SmartRaidDetector, SmartGrowthAdvisor, SmartWelcomeAnalyzer,
    SmartRoleCleaner, SmartChannelCleaner, SmartBackupAdvisor,
    SmartIncidentTimeline, ServerMaturityScore, AutoFixEngine,
)

router = APIRouter()


# =============================================================================
# Feature 1: Smart Recommendation Center
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/recommendations")
async def get_recommendations(guild_id: str):
    """Get all smart recommendations for a guild."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

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

    fix_engine = AutoFixEngine(bot)
    result = await fix_engine.execute_fix(guild, action, params)

    return vars(result)


# =============================================================================
# Feature 3: Config Doctor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/config-doctor")
async def get_config_doctor(guild_id: str):
    """Get configuration health diagnosis."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    doctor = ConfigDoctor(bot)
    diagnosis = doctor.diagnose(guild)

    return diagnosis


# =============================================================================
# Feature 4: Permission Doctor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/permission-doctor")
async def get_permission_doctor(guild_id: str):
    """Get permission analysis and findings."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    doctor = PermissionDoctor(bot)
    analysis = doctor.analyze(guild)

    return analysis


# =============================================================================
# Feature 5: Smart Raid Detector
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/raid-detector")
async def get_raid_detector(guild_id: str):
    """Analyze recent joins for raid patterns."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    # Get recent member joins
    recent_joins = []
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)

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
# Feature 6: Smart Growth Advisor
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/growth-advisor")
async def get_growth_advisor(guild_id: str):
    """Get growth analysis and recommendations."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    # Get growth data from analytics
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()

    growth_data = {"retention": {}, "avg_active_users": 0}
    if engine:
        try:
            retention = engine.get_member_retention(guild_id)
            overview = engine.get_overview(guild_id)
            growth_data["retention"] = retention
            growth_data["avg_active_users"] = overview.get("active_users_7d", 0)
        except Exception:
            pass

    advisor = SmartGrowthAdvisor(bot)
    analysis = advisor.analyze(guild, growth_data)

    return analysis


# =============================================================================
# Feature 7: Smart Welcome Analyzer
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/welcome-analyzer")
async def get_welcome_analyzer(guild_id: str):
    """Analyze onboarding setup."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    from aegis.core.utils import get_guild_config
    config = get_guild_config(guild_id) or {}

    analyzer = SmartWelcomeAnalyzer(bot)
    analysis = analyzer.analyze(guild, config)

    return analysis


# =============================================================================
# Feature 8: Smart Role Cleaner
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
    # Validate hours parameter
    if hours < 1 or hours > 168:  # Max 7 days
        hours = max(1, min(hours, 168))
    
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    timeline = SmartIncidentTimeline(bot)
    result = timeline.build_timeline(guild_id, hours)

    return result


# =============================================================================
# Feature 12: Server Maturity Score
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/maturity-score")
async def get_maturity_score(guild_id: str):
    """Get comprehensive server maturity score."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()

    scorer = ServerMaturityScore(bot)
    score = scorer.compute(guild, engine)

    return score


# =============================================================================
# Combined Smart Overview
# =============================================================================

@router.get("/api/guilds/{guild_id}/smart/overview")
async def get_smart_overview(guild_id: str):
    """Get a combined overview of all smart features."""
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(int(guild_id))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    from aegis.core.utils import get_guild_config
    config = get_guild_config(guild_id) or {}

    # Run all analyzers
    rec_engine = RecommendationEngine(bot)
    config_doc = ConfigDoctor(bot)
    perm_doc = PermissionDoctor(bot)
    growth_adv = SmartGrowthAdvisor(bot)
    backup_adv = SmartBackupAdvisor(bot)
    maturity = ServerMaturityScore(bot)

    # Get growth data
    growth_data = {"retention": {}, "avg_active_users": 0}
    if engine:
        try:
            retention = engine.get_member_retention(guild_id)
            overview = engine.get_overview(guild_id)
            growth_data["retention"] = retention
            growth_data["avg_active_users"] = overview.get("active_users_7d", 0)
        except Exception:
            pass

    recommendations = rec_engine.analyze(guild)
    config_diagnosis = config_doc.diagnose(guild)
    perm_analysis = perm_doc.analyze(guild)
    growth_analysis = growth_adv.analyze(guild, growth_data)
    backup_analysis = backup_adv.analyze(guild_id)
    maturity_score = maturity.compute(guild, engine)

    return {
        "guild_id": guild_id,
        "maturity_score": maturity_score["overall"],
        "config_health": config_diagnosis["overall"],
        "permission_issues": perm_analysis["critical_count"] + perm_analysis["warning_count"],
        "recommendations_count": len(recommendations),
        "growth_score": growth_analysis["score"],
        "backup_protection": backup_analysis["protection_score"],
        "dimensions": maturity_score["dimensions"],
    }
