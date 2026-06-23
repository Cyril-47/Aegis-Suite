from fastapi import APIRouter, HTTPException, Request
from aegis.web.routes.dashboard import get_active_bot
from aegis.core.config_history import get_history

router = APIRouter()


async def _get_notifications(guild_id: str) -> list:
    """Generate smart notifications based on guild state."""
    from aegis.bot.permission_analyzer import PermissionAnalyzer
    from aegis.bot.config_doctor import ConfigDoctor

    bot = get_active_bot()
    notifications = []

    if not bot:
        return notifications

    # Check security — dangerous permissions
    try:
        perm_analyzer = PermissionAnalyzer(bot)
        perm_result = await perm_analyzer.analyze_permissions(int(guild_id))
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
    except Exception:
        pass

    # Check config health — missing channels, broken refs
    try:
        config_doctor = ConfigDoctor(bot)
        config_result = await config_doctor.diagnose_config(int(guild_id))
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
    except Exception:
        pass

    # Check backup freshness
    from aegis.core.config_history import get_history
    history = get_history(guild_id, limit=1)
    if not history.get("snapshots"):
        notifications.append({
            "type": "info",
            "title": "No config backups yet",
            "description": "Config snapshots will be created automatically when settings are saved.",
            "action": None,
            "icon": "fa-box-archive",
        })

    return notifications


@router.get("/api/guilds/{guild_id}/command-center")
async def get_command_center(guild_id: str, request: Request):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    from aegis.bot.auditor import ServerAuditor

    auditor = ServerAuditor(bot)

    audit_result = await auditor.audit_guild(int(guild_id))
    notifications = await _get_notifications(guild_id)
    history = get_history(guild_id, limit=10)

    # Build activity summary from guild info
    guild = bot.get_guild(int(guild_id))
    activity = {}
    if guild:
        activity["member_count"] = guild.member_count
        activity["channel_count"] = len(guild.channels)
        activity["role_count"] = len(guild.roles)
        activity["online_count"] = sum(1 for m in guild.members if m.status != "off" and not m.bot)

    # Build timeline from config history
    timeline = []
    for snap in history.get("snapshots", []):
        changed = snap.get("changed_keys", [])
        if isinstance(changed, str):
            import json
            try:
                changed = json.loads(changed)
            except Exception:
                changed = [changed] if changed else []
        timeline.append({
            "timestamp": snap.get("created_at"),
            "actor": snap.get("created_by", "system"),
            "action": f"Config updated: {', '.join(changed)}" if changed else "Config snapshot created",
            "type": "config",
        })

    # Bot permissions for this guild
    bot_permissions = {}
    if guild and guild.me and guild.me.guild_permissions:
        perms = guild.me.guild_permissions
        bot_permissions = {
            "manage_guild": perms.manage_guild,
            "manage_channels": perms.manage_channels,
            "manage_roles": perms.manage_roles,
            "manage_webhooks": perms.manage_webhooks,
            "manage_emojis": perms.manage_emojis,
            "kick_members": perms.kick_members,
            "ban_members": perms.ban_members,
            "administrator": perms.administrator,
        }

    return {
        "guild_id": guild_id,
        "health_score": audit_result.get("overall_score", 0),
        "dimension_scores": audit_result.get("scores", {}),
        "findings": audit_result.get("findings", []),
        "member_count": activity.get("member_count", 0),
        "channel_count": activity.get("channel_count", 0),
        "role_count": activity.get("role_count", 0),
        "online_count": activity.get("online_count", 0),
        "notifications": notifications,
        "timeline": timeline[:5],
        "recommendations_count": len(audit_result.get("findings", [])),
        "bot_permissions": bot_permissions,
    }


@router.get("/api/guilds/{guild_id}/notifications")
async def get_notifications(guild_id: str, request: Request):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    notifications = await _get_notifications(guild_id)
    return {"notifications": notifications}
