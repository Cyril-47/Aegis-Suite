import utils
from typing import List
from aegis.core.permissions.registry import CommandRegistry

class PermissionResolver:
    @staticmethod
    def is_destructive(command_name: str) -> bool:
        destructive = {
            CommandRegistry.UNLINK,
            CommandRegistry.OPTIMIZE_SERVER,
            CommandRegistry.MUSIC_STOP,
            CommandRegistry.MUSIC_CLEARQUEUE,
            CommandRegistry.LEVEL_RESET,
            CommandRegistry.GIVEAWAY_STOP
        }
        return command_name in destructive

    @staticmethod
    async def has_permission(
        guild_id: str,
        user_id: str,
        command_name: str,
        user_roles: List[str],
        is_owner: bool = False,
        has_discord_admin: bool = False
    ) -> bool:
        # 1. Guild Owner & Discord Administrator bypasses
        if is_owner or has_discord_admin:
            return True

        # 2. Retrieve thread-safe configuration cache
        try:
            config = utils.load_config()
        except Exception:
            # Fail-closed if config load completely fails
            return False

        guild_configs = config.get("guild_configs", {})
        if not guild_configs:
            # Fail-closed for destructive commands
            if PermissionResolver.is_destructive(command_name):
                return False
            return True

        guild_conf = guild_configs.get(str(guild_id), {})
        
        # Load permission role mappings
        roles_mapping = guild_conf.get("permission_roles", {})
        admin_role = str(roles_mapping.get("admin_role_id", "")) if roles_mapping else ""
        mod_role = str(roles_mapping.get("moderator_role_id", "")) if roles_mapping else ""
        
        user_roles_str = [str(r) for r in user_roles]
        cmd_rules = guild_conf.get("command_permissions", {})
        
        # Default fallback for unconfigured commands
        if not cmd_rules or command_name not in cmd_rules:
            if PermissionResolver.is_destructive(command_name):
                return admin_role in user_roles_str if admin_role else False
            return True

        rule = cmd_rules[command_name]
        mode = rule.get("mode", "everyone")
        
        if mode == "everyone":
            return True
        elif mode == "owner":
            return False  # Only bypassed by step 1 (Owner/Admin)
        elif mode == "admin":
            return admin_role in user_roles_str if admin_role else False
        elif mode == "moderator":
            return (mod_role in user_roles_str) or (admin_role in user_roles_str)
        elif mode == "role":
            return str(rule.get("role_id", "")) in user_roles_str
        elif mode == "roles":
            target_roles = [str(r) for r in rule.get("role_ids", [])]
            return any(r in user_roles_str for r in target_roles)
            
        return False
