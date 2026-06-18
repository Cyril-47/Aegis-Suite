import logging
from typing import Dict, Any

logger = logging.getLogger("aegis.bot.auditor")


class ServerAuditor:
    """Scans a Discord guild and produces a health score with actionable recommendations."""

    WEIGHTS = {
        "security": 0.25,
        "moderation": 0.25,
        "structure": 0.20,
        "engagement": 0.15,
        "automation": 0.15,
    }

    def __init__(self, bot):
        self.bot = bot

    async def audit_guild(self, guild_id: int) -> Dict[str, Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"error": "Guild not found"}

        try:
            await guild.fetch_channels()
            await guild.fetch_roles()
        except Exception as e:
            logger.warning(f"Failed to fetch guild data for {guild_id}: {e}")

        config = self._get_guild_config(str(guild_id))

        scores = {}
        findings = []

        scores["security"], sec_findings = self._score_security(guild, config)
        findings.extend(sec_findings)

        scores["moderation"], mod_findings = self._score_moderation(guild, config)
        findings.extend(mod_findings)

        scores["structure"], struct_findings = self._score_structure(guild)
        findings.extend(struct_findings)

        scores["engagement"], eng_findings = self._score_engagement(guild, config)
        findings.extend(eng_findings)

        scores["automation"], auto_findings = self._score_automation(guild, config)
        findings.extend(auto_findings)

        overall = sum(scores[dim] * self.WEIGHTS[dim] for dim in self.WEIGHTS)

        return {
            "guild_id": str(guild_id),
            "guild_name": guild.name,
            "overall_score": round(overall),
            "scores": scores,
            "findings": findings,
            "member_count": guild.member_count,
            "channel_count": len(guild.channels),
            "role_count": len(guild.roles),
        }

    def _get_guild_config(self, guild_id: str) -> dict:
        try:
            from aegis.core.utils import get_guild_config
            return get_guild_config(guild_id)
        except Exception:
            return {}

    def _score_security(self, guild, config: dict) -> tuple:
        score = 100
        findings = []

        if guild.verification_level.value < 2:
            score -= 15
            findings.append({"type": "warning", "dimension": "security", "message": "Verification level is LOW — increase to Medium or High", "impact": -15})

        if not guild.mfa_level:
            score -= 10
            findings.append({"type": "warning", "dimension": "security", "message": "2FA not required for moderators", "impact": -10})

        everyone_role = guild.default_role
        perms = everyone_role.permissions
        dangerous_perms = [
            ("administrator", 20, "@everyone has Administrator permission"),
            ("manage_guild", 10, "@everyone can manage the server"),
            ("manage_roles", 10, "@everyone can manage roles"),
            ("manage_channels", 10, "@everyone can manage channels"),
            ("kick_members", 5, "@everyone can kick members"),
            ("ban_members", 5, "@everyone can ban members"),
        ]
        for perm_name, penalty, msg in dangerous_perms:
            if getattr(perms, perm_name, False):
                score -= penalty
                findings.append({"type": "critical", "dimension": "security", "message": msg, "impact": -penalty})

        for role in guild.roles:
            if role.permissions.administrator and role != guild.default_role and not role.managed:
                if role.position < guild.me.top_role.position:
                    score -= 5
                    findings.append({"type": "warning", "dimension": "security", "message": f"Role '{role.name}' has Administrator — review if needed", "impact": -5})

        return max(0, score), findings

    def _score_moderation(self, guild, config: dict) -> tuple:
        score = 100
        findings = []

        automod = config.get("automod_settings", {})
        if not automod.get("enabled", False):
            score -= 20
            findings.append({"type": "critical", "dimension": "moderation", "message": "AutoMod is disabled", "impact": -20})
        else:
            if not automod.get("block_profanity", False):
                score -= 5
                findings.append({"type": "info", "dimension": "moderation", "message": "Profanity filter is disabled", "impact": -5})
            if not automod.get("block_links", False):
                score -= 5
                findings.append({"type": "info", "dimension": "moderation", "message": "Link filter is disabled", "impact": -5})
            if not automod.get("block_invites", False):
                score -= 5
                findings.append({"type": "info", "dimension": "moderation", "message": "Invite filter is disabled", "impact": -5})

        log_channel = automod.get("log_channel_id") or automod.get("log_channel_name")
        if not log_channel:
            score -= 10
            findings.append({"type": "warning", "dimension": "moderation", "message": "No mod-log channel configured", "impact": -10})

        has_mod_role = any(
            r.name.lower() in ("moderator", "mod", "staff", "admin")
            for r in guild.roles
        )
        if not has_mod_role:
            score -= 10
            findings.append({"type": "warning", "dimension": "moderation", "message": "No moderator role found", "impact": -10})

        return max(0, score), findings

    def _score_structure(self, guild) -> tuple:
        score = 100
        findings = []

        categories = [c for c in guild.categories]
        text_channels = [c for c in guild.text_channels]

        empty_cats = [c for c in categories if len(c.channels) == 0]
        if empty_cats:
            penalty = min(len(empty_cats) * 3, 15)
            score -= penalty
            findings.append({"type": "info", "dimension": "structure", "message": f"{len(empty_cats)} empty categories found", "impact": -penalty})

        default_named = [c for c in text_channels if c.name.startswith("untitled") or c.name == "general"]
        if len(default_named) > 2:
            score -= 5
            findings.append({"type": "info", "dimension": "structure", "message": "Several channels have default names", "impact": -5})

        if not guild.afk_channel:
            score -= 5
            findings.append({"type": "info", "dimension": "structure", "message": "No AFK channel configured", "impact": -5})

        if not guild.system_channel:
            score -= 5
            findings.append({"type": "info", "dimension": "structure", "message": "No system channel configured", "impact": -5})

        return max(0, score), findings

    def _score_engagement(self, guild, config: dict) -> tuple:
        score = 100
        findings = []

        welcome = config.get("welcome_settings", {})
        if not welcome.get("enabled", False):
            score -= 20
            findings.append({"type": "warning", "dimension": "engagement", "message": "Welcome messages are disabled", "impact": -20})

        leveling = config.get("leveling_settings", {})
        if not leveling or not leveling.get("enabled", False):
            score -= 10
            findings.append({"type": "info", "dimension": "engagement", "message": "Leveling system is disabled", "impact": -10})

        return max(0, score), findings

    def _score_automation(self, guild, config: dict) -> tuple:
        score = 100
        findings = []

        scheduled = config.get("scheduled_messages", [])
        if not scheduled:
            score -= 10
            findings.append({"type": "info", "dimension": "automation", "message": "No scheduled messages configured", "impact": -10})

        auto_resp = config.get("auto_responders", [])
        if not auto_resp:
            score -= 5
            findings.append({"type": "info", "dimension": "automation", "message": "No auto-responders configured", "impact": -5})

        tickets = config.get("ticket_settings", {})
        if not tickets or not tickets.get("enabled", False):
            score -= 10
            findings.append({"type": "warning", "dimension": "automation", "message": "Ticket system is disabled", "impact": -10})

        return max(0, score), findings
