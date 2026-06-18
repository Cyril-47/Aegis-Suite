import logging
from typing import Dict, Any

logger = logging.getLogger("aegis.bot.config_doctor")


class ConfigDoctor:
    """Checks bot configuration for issues and suggests fixes."""

    def __init__(self, bot):
        self.bot = bot

    async def diagnose_config(self, guild_id: int) -> Dict[str, Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"error": "Guild not found"}

        from aegis.core.utils import get_guild_config
        config = get_guild_config(str(guild_id))

        issues = []
        suggestions = []

        # Check welcome settings
        welcome = config.get("welcome_settings", {})
        if not welcome.get("enabled"):
            issues.append({
                "category": "engagement",
                "severity": "warning",
                "message": "Welcome messages are disabled",
                "fix_action": "enable_welcome",
            })
        elif welcome.get("enabled") and not welcome.get("channel_id"):
            issues.append({
                "category": "engagement",
                "severity": "info",
                "message": "Welcome enabled but no channel configured",
                "fix_action": None,
            })

        # Check automod
        automod = config.get("automod_settings", {})
        if not automod.get("enabled"):
            issues.append({
                "category": "moderation",
                "severity": "critical",
                "message": "AutoMod is completely disabled",
                "fix_action": "enable_automod",
            })

        # Check tickets
        tickets = config.get("ticket_settings", {})
        if not tickets or not tickets.get("enabled"):
            suggestions.append({
                "category": "support",
                "message": "Enable ticket system for member support",
                "impact": "+5 Support score",
            })

        # Check leveling
        leveling = config.get("leveling_settings", {})
        if not leveling or not leveling.get("enabled"):
            suggestions.append({
                "category": "engagement",
                "message": "Enable leveling system for member engagement",
                "impact": "+10 Engagement score",
            })

        # Check scheduled messages
        scheduled = config.get("scheduled_messages", [])
        if not scheduled:
            suggestions.append({
                "category": "automation",
                "message": "Add scheduled messages for regular announcements",
                "impact": "+5 Automation score",
            })

        # Check auto-responders
        auto_resp = config.get("auto_responders", [])
        if not auto_resp:
            suggestions.append({
                "category": "automation",
                "message": "Add auto-responders for common questions",
                "impact": "+3 Automation score",
            })

        # Check for orphaned channel references
        channel_refs = []
        if welcome.get("channel_id"):
            channel_refs.append(("welcome", welcome["channel_id"]))
        if automod.get("log_channel_id"):
            channel_refs.append(("automod_log", automod["log_channel_id"]))

        for ref_name, ch_id in channel_refs:
            try:
                channel = guild.get_channel(int(ch_id))
                if not channel:
                    issues.append({
                        "category": "config",
                        "severity": "warning",
                        "message": f"{ref_name} references non-existent channel ID {ch_id}",
                        "fix_action": f"fix_channel_ref:{ref_name}",
                    })
            except (ValueError, TypeError):
                issues.append({
                    "category": "config",
                    "severity": "warning",
                    "message": f"{ref_name} has invalid channel ID: {ch_id}",
                    "fix_action": f"fix_channel_ref:{ref_name}",
                })

        return {
            "guild_id": str(guild_id),
            "guild_name": guild.name,
            "issues": issues,
            "suggestions": suggestions,
            "total_issues": len(issues),
            "total_suggestions": len(suggestions),
        }
