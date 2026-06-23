from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
import asyncio
import json
import logging
from aegis.web.routes.dashboard import get_active_bot
async def _get_notifications(guild_id: str) -> list:
    """Generate smart notifications based on guild state."""
    from aegis.bot.permission_analyzer import PermissionAnalyzer
    from aegis.bot.config_doctor import ConfigDoctor
    from aegis.core.config_history import get_history

    bot = get_active_bot()
    notifications = []

    if not bot:
        return notifications

    perm_result = {}
    config_result = {}

    async def _run_perm_analysis():
        nonlocal perm_result
        try:
            perm_analyzer = PermissionAnalyzer(bot)
            perm_result = await perm_analyzer.analyze_permissions(int(guild_id))
        except Exception:
            pass

    async def _run_config_diagnosis():
        nonlocal config_result
        try:
            config_doctor = ConfigDoctor(bot)
            config_result = await config_doctor.diagnose_config(int(guild_id))
        except Exception:
            pass

    history_result, _, _ = await asyncio.gather(
        asyncio.to_thread(get_history, guild_id, 1),
        _run_perm_analysis(),
        _run_config_diagnosis(),
    )

    if "role_findings" in perm_result:
        critical = [f for f in perm_result["role_findings"] if f.get("severity") == "critical"]
        if critical:
            notifications.append({
                "type": "critical",
                "title": f"{len(critical)} dangerous permission(s) detected",
                "description": "Roles with @everyone-level access found. Review permissions immediately.",
                "action": "fix_permissions",
                "icon": "fa-shield-halved",
            })
        warnings = [f for f in perm_result["role_findings"] if f.get("severity") == "warning"]
        if warnings:
            notifications.append({
                "type": "warning",
                "title": f"{len(warnings)} permission warning(s)",
                "description": "Some roles have potentially risky configurations.",
                "action": "fix_permissions",
                "icon": "fa-triangle-exclamation",
            })

    total_issues = config_result.get("total_issues", 0)
    if total_issues > 0:
        issues = config_result.get("issues", [])
        first_issue = issues[0] if issues else "Configuration issues found"
        notifications.append({
            "type": "warning" if total_issues <= 3 else "critical",
            "title": f"{total_issues} configuration issue(s)",
            "description": first_issue if isinstance(first_issue, str) else first_issue.get("message", "Config issues found"),
            "action": "fix_config",
            "icon": "fa-gear",
        })

    if not history_result.get("snapshots"):
        notifications.append({
            "type": "info",
            "title": "No config backups yet",
            "description": "Config snapshots will be created automatically when settings are saved.",
            "action": None,
            "icon": "fa-box-archive",
        })

    return notifications

logger = logging.getLogger("aegis.web.live_alerts")

# In-memory cache for guild audit results to prevent rate limits
_audit_cache = {}
_audit_cache_lock = asyncio.Lock()

async def get_cached_audit_result(bot, guild_id: int) -> dict:
    import time
    from aegis.bot.auditor import ServerAuditor
    
    async with _audit_cache_lock:
        now = time.time()
        if guild_id in _audit_cache:
            ts, cached_result = _audit_cache[guild_id]
            if now - ts < 30.0:  # 30-second cooldown
                return cached_result
                
        auditor = ServerAuditor(bot)
        result = await auditor.audit_guild(guild_id)
        _audit_cache[guild_id] = (now, result)
        return result


router = APIRouter()

@router.get("/api/alerts/stream")
async def alerts_stream(request: Request, guild_id: str):
    """Server-Sent Events stream for live command center updates."""
    
    async def event_generator():
        last_notification_titles = None
        last_health = None
        last_timeline_actions = []
        
        # Initial wait to let connection establish
        await asyncio.sleep(0.5)
        
        while True:
            if await request.is_disconnected():
                break
                
            try:
                bot = get_active_bot()
                if bot and bot.is_ready():
                    # 1. Live Notifications (event: alert)
                    notifications = await _get_notifications(guild_id)
                    current_titles = {n["title"] for n in notifications}
                    
                    if last_notification_titles is None:
                        # First run: establish baseline notifications without sending live toasts
                        last_notification_titles = current_titles
                    else:
                        new_items = [n for n in notifications if n["title"] not in last_notification_titles]
                        if new_items:
                            for item in new_items:
                                yield f"event: alert\ndata: {json.dumps(item)}\n\n"
                            last_notification_titles = current_titles
                        
                    # 2. Health Score Updates (event: health_update)
                    audit_result = await get_cached_audit_result(bot, int(guild_id))
                    health_score = audit_result.get("overall_score", 0)
                    
                    if last_health is not None and health_score != last_health:
                        yield f"event: health_update\ndata: {json.dumps({'health_score': health_score, 'old_score': last_health})}\n\n"
                    last_health = health_score
                    
                    # 3. Rule Triggers & Guardian Mode Logs (event: guardian_action)
                    try:
                        from aegis.intelligence.registry import get_automation_engine
                        _eng = get_automation_engine()
                        log_entries = _eng.get_execution_log(5) if _eng and hasattr(_eng, 'get_execution_log') else []
                    except Exception:
                        log_entries = []
                    current_entry_timestamps = [entry.get("timestamp") for entry in log_entries if "timestamp" in entry]
                    
                    if last_timeline_actions:
                        for entry in log_entries:
                            ts = entry.get("timestamp")
                            if ts and ts not in last_timeline_actions:
                                yield f"event: guardian_action\ndata: {json.dumps(entry)}\n\n"
                    last_timeline_actions = current_entry_timestamps
                    
            except Exception as e:
                logger.warning(f"Error in SSE stream loop: {e}", exc_info=True)
                
            await asyncio.sleep(5)
            
    return StreamingResponse(event_generator(), media_type="text/event-stream")
