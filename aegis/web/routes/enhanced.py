from fastapi import APIRouter, HTTPException
from aegis.web.routes.dashboard import get_active_bot, parse_id

router = APIRouter()


@router.get("/api/guilds/{guild_id}/security-checks")
async def get_security_checks(guild_id: str):
    bot = get_active_bot()
    if not bot:
        raise HTTPException(status_code=503, detail="Bot not connected")

    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found")

    checks = []

    # @everyone audit
    everyone_perms = guild.default_role.permissions
    dangerous_everyone = []
    if everyone_perms.mention_everyone:
        dangerous_everyone.append("@everyone can mention everyone")
    if everyone_perms.ban_members:
        dangerous_everyone.append("@everyone can ban members")
    if everyone_perms.kick_members:
        dangerous_everyone.append("@everyone can kick members")
    if everyone_perms.manage_channels:
        dangerous_everyone.append("@everyone can manage channels")
    if everyone_perms.administrator:
        dangerous_everyone.append("@everyone has Administrator")
    checks.append({
        "name": "@everyone Permissions",
        "status": "critical" if dangerous_everyone else "safe",
        "details": dangerous_everyone or ["@everyone permissions are safe"],
    })

    # Admin role audit
    admin_roles = [r for r in guild.roles if r.permissions.administrator and not r.is_default()]
    if len(admin_roles) > 3:
        checks.append({
            "name": "Admin Role Count",
            "status": "warning",
            "details": [f"{len(admin_roles)} roles have Administrator permission. Consider reducing to 1-2."],
        })
    else:
        checks.append({
            "name": "Admin Role Count",
            "status": "safe",
            "details": [f"{len(admin_roles)} admin role(s) — within recommended range."],
        })

    # Webhook audit
    try:
        webhooks = await guild.webhooks()
        if len(webhooks) > 5:
            checks.append({
                "name": "Webhook Count",
                "status": "warning",
                "details": [f"{len(webhooks)} webhooks found. Unused webhooks can be a security risk."],
            })
        else:
            checks.append({
                "name": "Webhook Count",
                "status": "safe",
                "details": [f"{len(webhooks)} webhook(s) — acceptable."],
            })
    except Exception:
        checks.append({"name": "Webhook Count", "status": "unknown", "details": ["Could not check webhooks."]})

    # Invite audit
    try:
        invites = await guild.invites()
        active_invites = [i for i in invites if not i.max_uses or i.uses < i.max_uses]
        if len(active_invites) > 10:
            checks.append({
                "name": "Active Invites",
                "status": "warning",
                "details": [f"{len(active_invites)} active invites. Expired or unused invites should be revoked."],
            })
        else:
            checks.append({
                "name": "Active Invites",
                "status": "safe",
                "details": [f"{len(active_invites)} active invite(s)."],
            })
    except Exception:
        checks.append({"name": "Active Invites", "status": "unknown", "details": ["Could not check invites."]})

    # Verification level
    vlevel = guild.verification_level.name
    if vlevel in ("none", "low"):
        checks.append({
            "name": "Verification Level",
            "status": "warning",
            "details": [f"Verification level is '{vlevel}'. Consider raising to 'Medium' or 'High'."],
        })
    else:
        checks.append({
            "name": "Verification Level",
            "status": "safe",
            "details": [f"Verification level is '{vlevel}'."],
        })

    # Bot permission audit
    bot_member = guild.me
    if bot_member:
        missing = []
        needed = ["manage_roles", "manage_channels", "send_messages", "embed_links", "read_message_history"]
        for perm_name in needed:
            if not getattr(bot_member.guild_permissions, perm_name, False):
                missing.append(perm_name.replace("_", " ").title())
        if missing:
            checks.append({
                "name": "Bot Permissions",
                "status": "warning",
                "details": [f"Bot is missing: {', '.join(missing)}"],
            })
        else:
            checks.append({
                "name": "Bot Permissions",
                "status": "safe",
                "details": ["Bot has all recommended permissions."],
            })

    score = 100
    for c in checks:
        if c["status"] == "critical":
            score -= 25
        elif c["status"] == "warning":
            score -= 10
    score = max(0, score)

    return {"checks": checks, "score": score}


@router.get("/api/guilds/{guild_id}/config-history")
async def get_config_history(guild_id: str, limit: int = 20):
    from aegis.core.config_history import get_history
    return get_history(guild_id, limit=limit)


@router.post("/api/guilds/{guild_id}/config-rollback/{snapshot_id}")
async def rollback_config(guild_id: str, snapshot_id: int):
    from aegis.core.config_history import get_snapshot
    from aegis.core.utils import save_guild_config

    snapshot = get_snapshot(snapshot_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="Snapshot not found.")
    if snapshot.get("guild_id") != guild_id:
        raise HTTPException(status_code=403, detail="Snapshot does not belong to this server.")

    import json
    config_data = json.loads(snapshot.get("config_json", "{}"))
    save_guild_config(guild_id, config_data)

    from aegis.core import audit_log
    audit_log.log_action("admin", "CONFIG_ACTION", f"Rolled back to snapshot #{snapshot_id}", guild_id)
    return {"status": "success", "message": f"Rolled back to snapshot #{snapshot_id}."}


@router.get("/api/guilds/{guild_id}/score-history")
async def get_score_history(guild_id: str, days: int = 30):
    from aegis.db.analytics_models import ServerScore
    from datetime import datetime, timedelta, timezone

    engine = _get_analytics_engine()
    session = engine._session_factory()

    try:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        scores = session.query(ServerScore).filter(
            ServerScore.guild_id == guild_id,
            ServerScore.timestamp >= cutoff,
        ).order_by(ServerScore.timestamp).all()

        history = []
        for s in scores:
            history.append({
                "timestamp": s.timestamp.isoformat() if s.timestamp else None,
                "overall": s.overall,
                "security": s.security,
                "moderation": s.moderation,
                "structure": s.structure,
                "engagement": s.engagement,
                "automation": s.automation,
            })

        session.close()
        return {"history": history}
    except Exception:
        session.close()
        return {"history": []}


def _get_analytics_engine():
    from aegis.analytics.engine import get_analytics_engine
    engine = get_analytics_engine()
    if not engine:
        raise HTTPException(status_code=503, detail="Analytics engine not available")
    return engine
