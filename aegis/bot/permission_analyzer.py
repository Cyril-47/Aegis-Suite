import logging
from typing import Dict, Any

logger = logging.getLogger("aegis.bot.permission_analyzer")


class PermissionAnalyzer:
    """Scans Discord role permissions for dangerous configurations."""

    DANGEROUS_PERMS = {
        "administrator": {"severity": "critical", "message": "Grants full server control"},
        "manage_guild": {"severity": "high", "message": "Can change server settings"},
        "manage_roles": {"severity": "high", "message": "Can create/edit/delete roles"},
        "manage_channels": {"severity": "high", "message": "Can create/edit/delete channels"},
        "manage_webhooks": {"severity": "medium", "message": "Can create webhooks for message spoofing"},
        "kick_members": {"severity": "medium", "message": "Can kick members"},
        "ban_members": {"severity": "medium", "message": "Can ban members"},
        "manage_messages": {"severity": "medium", "message": "Can delete others' messages"},
        "mention_everyone": {"severity": "low", "message": "Can ping @everyone"},
        "manage_emojis": {"severity": "low", "message": "Can add/remove emojis"},
    }

    def __init__(self, bot):
        self.bot = bot

    async def analyze_permissions(self, guild_id: int) -> Dict[str, Any]:
        guild = self.bot.get_guild(guild_id)
        if not guild:
            return {"error": "Guild not found"}

        try:
            await guild.fetch_roles()
        except Exception as e:
            logger.warning(f"Failed to fetch roles for {guild_id}: {e}")

        role_findings = []
        user_findings = []

        # Analyze roles
        for role in guild.roles:
            if role == guild.default_role or role.managed:
                continue

            role_perms = []
            for perm_name, info in self.DANGEROUS_PERMS.items():
                if getattr(role.permissions, perm_name, False):
                    role_perms.append({
                        "permission": perm_name,
                        "severity": info["severity"],
                        "message": info["message"],
                    })

            if role_perms:
                role_findings.append({
                    "role_id": str(role.id),
                    "role_name": role.name,
                    "role_position": role.position,
                    "dangerous_permissions": role_perms,
                    "member_count": len(role.members),
                })

        # Check for users with dangerous role combinations
        admin_roles = [r for r in guild.roles if r.permissions.administrator and not r.managed]
        if admin_roles:
            for role in admin_roles:
                if role != guild.default_role:
                    for member in role.members:
                        user_findings.append({
                            "user_id": str(member.id),
                            "username": member.name,
                            "role": role.name,
                            "warning": f"User has Administrator via role '{role.name}'",
                        })

        return {
            "guild_id": str(guild_id),
            "guild_name": guild.name,
            "role_findings": role_findings,
            "user_findings": user_findings,
            "total_roles_scanned": len([r for r in guild.roles if not r.managed]),
            "roles_with_issues": len(role_findings),
        }
