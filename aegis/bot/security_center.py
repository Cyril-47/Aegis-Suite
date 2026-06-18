import logging
from typing import Dict, Any

logger = logging.getLogger("aegis.bot.security_center")


class SecurityCenter:
    """Unified security dashboard combining auditor, permissions, and config checks."""

    def __init__(self, bot):
        self.bot = bot

    async def get_security_overview(self, guild_id: int) -> Dict[str, Any]:
        from aegis.bot.auditor import ServerAuditor
        from aegis.bot.permission_analyzer import PermissionAnalyzer
        from aegis.bot.config_doctor import ConfigDoctor

        auditor = ServerAuditor(self.bot)
        perm_analyzer = PermissionAnalyzer(self.bot)
        config_doctor = ConfigDoctor(self.bot)

        audit_result = await auditor.audit_guild(guild_id)
        perm_result = await perm_analyzer.analyze_permissions(guild_id)
        config_result = await config_doctor.diagnose_config(guild_id)

        # Combine scores
        overall_score = audit_result.get("overall_score", 0)
        perm_issues = len(perm_result.get("role_findings", []))
        config_issues = config_result.get("total_issues", 0)

        # Adjust score based on permission and config issues
        if perm_issues > 5:
            overall_score = max(0, overall_score - 10)
        if config_issues > 3:
            overall_score = max(0, overall_score - 5)

        return {
            "guild_id": str(guild_id),
            "overall_score": overall_score,
            "audit": audit_result,
            "permissions": perm_result,
            "config": config_result,
            "summary": {
                "audit_score": audit_result.get("overall_score", 0),
                "permission_issues": perm_issues,
                "config_issues": config_issues,
                "config_suggestions": config_result.get("total_suggestions", 0),
            },
        }
