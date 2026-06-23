"""
Local Intelligence Engine API Routes.

Endpoints for all 8 intelligence features.
"""

from fastapi import APIRouter, HTTPException, Request
from aegis.web.routes.dashboard import get_active_bot
import datetime

from aegis.intelligence.registry import (
    get_raid_detector as reg_get_raid_detector,
    get_sentiment_analyzer as reg_get_sentiment_analyzer,
    get_spam_detector as reg_get_spam_detector,
    get_activity_intelligence as reg_get_activity_intelligence,
    get_automation_engine as reg_get_automation_engine
)

router = APIRouter()

# Singleton proxies
def _raid_detector():
    return reg_get_raid_detector()

def _sentiment_analyzer():
    return reg_get_sentiment_analyzer()

def _spam_detector():
    return reg_get_spam_detector()

def _activity_intelligence():
    return reg_get_activity_intelligence()

def _automation_engine():
    return reg_get_automation_engine()


# =============================================================================
# Feature 1: Adaptive Raid Detection
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/raid-monitor")
async def get_raid_monitor(guild_id: str):
    """Get adaptive raid detection analysis."""
    try:
        analysis = _raid_detector().analyze(guild_id)
        return analysis
    except Exception as e:
        return {"threat_level": "normal", "threat_score": 0, "scores": {"joins": 0, "messages": 0, "moderation": 0}, "reasons": [], "suggested_actions": [], "error": str(e)}



# =============================================================================
# Feature 2: Smart Sentiment Moderation
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/community-health")
async def get_community_health(guild_id: str):
    """Get community health metrics."""
    try:
        health = _sentiment_analyzer().get_community_health(guild_id)
        return health
    except Exception as e:
        return {"overall_score": 0, "positivity_rate": 0, "toxicity_rate": 0, "harassment_detected": False, "trend": "stable", "error": str(e)}


@router.get("/api/guilds/{guild_id}/intelligence/toxic-channels")
async def get_toxic_channels(guild_id: str, limit: int = 5):
    """Get channels with highest toxicity."""
    try:
        channels = _sentiment_analyzer().get_most_toxic_channels(limit)
        return {"channels": channels}
    except Exception as e:
        return {"channels": [], "error": str(e)}



# =============================================================================
# Feature 3: Fuzzy Spam Detection
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/spam-intelligence")
async def get_spam_intelligence(guild_id: str):
    """Get spam intelligence overview."""
    try:
        intelligence = _spam_detector().get_spam_intelligence(guild_id)
        return intelligence
    except Exception as e:
        return {"campaigns": [], "total_campaigns": 0, "affected_channels": [], "error": str(e)}


@router.post("/api/guilds/{guild_id}/intelligence/spam-check")
async def check_spam(guild_id: str, request: Request):
    """Check a message for spam."""
    body = await request.json()
    user_id = body.get("user_id")
    channel_id = body.get("channel_id")
    content = body.get("content")
    
    if not user_id or not channel_id or not content:
        raise HTTPException(status_code=400, detail="Missing required fields")
    
    result = _spam_detector().analyze(user_id, channel_id, content)
    return result


# =============================================================================
# Feature 4: Activity Intelligence
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/activity")
async def get_activity_intelligence(guild_id: str):
    """Get activity intelligence analysis."""
    try:
        analysis = _activity_intelligence().analyze_activity(guild_id)
        return analysis
    except Exception as e:
        return {"peak_hour": 12, "peak_day": 0, "best_event_time": "Unknown", "recommendations": [], "error": str(e)}


# =============================================================================
# Feature 5: Automation Engine
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/automation/rules")
async def get_automation_rules(guild_id: str):
    """Get all automation rules."""
    try:
        rules = _automation_engine().get_all_rules(guild_id)
        return {"rules": [vars(r) for r in rules]}
    except Exception as e:
        return {"rules": [], "error": str(e)}


@router.post("/api/guilds/{guild_id}/intelligence/automation/rules")
async def create_automation_rule(guild_id: str, request: Request):
    """Create a new automation rule."""
    body = await request.json()
    
    # Validate rule
    validation = _automation_engine().validate_rule(body)
    if not validation["valid"]:
        raise HTTPException(status_code=400, detail={"errors": validation["errors"]})
    
    rule = _automation_engine().create_rule(guild_id, body)
    return vars(rule)


@router.put("/api/guilds/{guild_id}/intelligence/automation/rules/{rule_id}")
async def update_automation_rule(guild_id: str, rule_id: str, request: Request):
    """Update an automation rule."""
    body = await request.json()
    rule = _automation_engine().update_rule(guild_id, rule_id, body)
    
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    return vars(rule)


@router.delete("/api/guilds/{guild_id}/intelligence/automation/rules/{rule_id}")
async def delete_automation_rule(guild_id: str, rule_id: str):
    """Delete an automation rule."""
    success = _automation_engine().delete_rule(guild_id, rule_id)
    if not success:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"status": "deleted"}


@router.get("/api/guilds/{guild_id}/intelligence/automation/log")
async def get_automation_log(guild_id: str):
    """Get automation execution log."""
    try:
        log = _automation_engine().get_execution_log(20)
        return {"log": log}
    except Exception as e:
        return {"log": [], "error": str(e)}


# =============================================================================
# Feature 6: Smart Recommendations
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/recommendations")
async def get_recommendations(guild_id: str):
    """Get smart recommendations."""
    try:
        bot = get_active_bot()
        if not bot:
            return {"total": 0, "recommendations": [], "error": "Bot not connected"}
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return {"total": 0, "recommendations": [], "error": "Guild not found"}
        
        # Use existing recommendation engine from smart_features
        from aegis.analytics.smart_features import RecommendationEngine
        engine = RecommendationEngine(bot)
        recommendations = engine.analyze(guild)
        
        return {
            "total": len(recommendations),
            "recommendations": [vars(r) for r in recommendations],
        }
    except Exception as e:
        return {"total": 0, "recommendations": [], "error": str(e)}


# =============================================================================
# Feature 7: One-Click Fix Center
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/fix-center")
async def get_fix_center(guild_id: str):
    """Get all available fixes."""
    try:
        bot = get_active_bot()
        if not bot:
            return {"issues": [], "error": "Bot not connected"}
        
        guild = bot.get_guild(int(guild_id))
        if not guild:
            return {"issues": [], "error": "Guild not found"}
        
        # Collect issues from all analyzers
        issues = []
        
        # Raid detection issues
        raid_analysis = _raid_detector().analyze(guild_id)
        if raid_analysis["threat_level"] != "normal":
            issues.append({
                "id": "raid_threat",
                "title": f"Raid Threat: {raid_analysis['threat_level'].title()}",
                "description": "Elevated activity detected",
                "risk": "high",
                "fix_action": "enable_raid_mode",
                "preview_available": True,
            })
        
        # Sentiment issues
        health = _sentiment_analyzer().get_community_health(guild_id)
        if health["toxicity_rate"] > 0.1:
            issues.append({
                "id": "toxicity",
                "title": "High Toxicity Detected",
                "description": f"{health['toxicity_rate']*100:.1f}% toxicity rate",
                "risk": "medium",
                "fix_action": "increase_moderation",
                "preview_available": True,
            })
        
        # Spam issues
        spam = _spam_detector().get_spam_intelligence(guild_id)
        if spam["total_campaigns"] > 0:
            issues.append({
                "id": "spam_campaigns",
                "title": f"{spam['total_campaigns']} Spam Campaigns Detected",
                "description": "Active spam campaigns found",
                "risk": "high",
                "fix_action": "enable_anti_spam",
                "preview_available": True,
            })
        
        # Recommendation issues
        from aegis.analytics.smart_features import RecommendationEngine
        rec_engine = RecommendationEngine(bot)
        recommendations = rec_engine.analyze(guild)
        
        for rec in recommendations[:5]:
            issues.append({
                "id": rec.id,
                "title": rec.title,
                "description": rec.description,
                "risk": rec.severity,
                "fix_action": rec.auto_fix_action,
                "preview_available": rec.auto_fix_available,
            })
        
        return {"issues": issues}
    except Exception as e:
        return {"issues": [], "error": str(e)}


# =============================================================================
# Feature 8: Intelligence Timeline
# =============================================================================

@router.get("/api/guilds/{guild_id}/intelligence/timeline")
async def get_intelligence_timeline(guild_id: str, days: int = 7):
    """Get intelligence timeline."""
    try:
        # Build timeline from various sources
        events = []
        
        # Add raid events
        raid_analysis = _raid_detector().analyze(guild_id)
        if raid_analysis["threat_level"] != "normal":
            events.append({
                "type": "raid_detected",
                "severity": raid_analysis["threat_level"],
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "details": f"Threat level: {raid_analysis['threat_level']}",
            })
        
        # Add spam events
        spam_intel = _spam_detector().get_spam_intelligence(guild_id)
        for campaign in spam_intel["campaigns"][:3]:
            events.append({
                "type": "spam_detected",
                "severity": "warning",
                "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "details": f"Spam campaign: {campaign['content'][:30]}...",
            })
        
        # Add automation executions
        automation_log = _automation_engine().get_execution_log(10)
        for entry in automation_log:
            events.append({
                "type": "automation_executed",
                "severity": "info",
                "timestamp": entry["timestamp"],
                "details": f"Rule '{entry['rule_name']}' triggered",
            })
        
        # Sort by timestamp
        events.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return {
            "events": events[:50],
            "total_events": len(events),
        }
    except Exception as e:
        return {"events": [], "total_events": 0, "error": str(e)}
