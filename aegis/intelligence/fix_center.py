"""
Feature 7: One-Click Fix Center

Provides preview and execution of automated fixes. Delegates to central AutoFixEngine.
"""

import logging
import datetime
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
from aegis.analytics.smart_features import AutoFixEngine

logger = logging.getLogger("aegis.intelligence.fix_center")


@dataclass
class FixResult:
    """Result of a fix operation."""
    success: bool
    action: str
    details: str
    changes: List[Dict[str, Any]]


class OneClickFixCenter:
    """One-click fix center that delegates execution to the central AutoFixEngine."""

    def __init__(self, bot):
        self.bot = bot
        self._engine = AutoFixEngine(bot)
        self._audit_log: List[Dict[str, Any]] = []

    def preview_fix(self, guild, action: str, params: Dict = None) -> Dict[str, Any]:
        """Preview what a fix would do without executing."""
        params = params or {}
        
        previews = {
            "set_verification_level": self._preview_verification,
            "archive_inactive_channels": self._preview_archive_channels,
            "remove_unused_roles": self._preview_remove_roles,
            "create_mod_log_channel": self._preview_create_channel,
            "enable_raid_mode": self._preview_raid_mode,
            "slowmode_all_channels": self._preview_slowmode,
        }
        
        if action in previews:
            return previews[action](guild, params)
        
        return {"action": action, "changes": [], "risk": "unknown"}

    def _preview_verification(self, guild, params: Dict) -> Dict[str, Any]:
        return {
            "action": "set_verification_level",
            "changes": [{"type": "verification", "from": getattr(guild.verification_level, "name", "UNKNOWN"), "to": "LOW"}],
            "risk": "safe",
        }

    def _preview_archive_channels(self, guild, params: Dict) -> Dict[str, Any]:
        channels = params.get("channels", [])
        return {
            "action": "archive_channels",
            "changes": [{"type": "channel", "name": ch, "action": "move to archive"} for ch in channels[:10]],
            "risk": "safe",
        }

    def _preview_remove_roles(self, guild, params: Dict) -> Dict[str, Any]:
        roles = params.get("roles", [])
        return {
            "action": "remove_roles",
            "changes": [{"type": "role", "name": r, "action": "delete"} for r in roles[:10]],
            "risk": "destructive",
        }

    def _preview_create_channel(self, guild, params: Dict) -> Dict[str, Any]:
        name = params.get("channel_name", "mod-log")
        return {
            "action": "create_channel",
            "changes": [{"type": "channel", "name": name, "action": "create"}],
            "risk": "safe",
        }

    def _preview_raid_mode(self, guild, params: Dict) -> Dict[str, Any]:
        return {
            "action": "enable_raid_mode",
            "changes": [{"type": "settings", "action": "enable verification level HIGH"}],
            "risk": "safe",
        }

    def _preview_slowmode(self, guild, params: Dict) -> Dict[str, Any]:
        return {
            "action": "slowmode_all_channels",
            "changes": [{"type": "channels", "action": "set slowmode to 10 seconds"}],
            "risk": "safe",
        }

    async def execute_fix(self, guild, action: str, params: Dict = None) -> FixResult:
        """Execute a fix action by delegating to central AutoFixEngine."""
        params = params or {}
        try:
            res = await self._engine.execute_fix(guild, action, params)
            changes = []
            if res.success:
                # Log to local audit log
                self._log_audit(action, guild.id, res.details)
                changes.append({"type": "action", "action": action, "status": "executed"})
                
            return FixResult(
                success=res.success,
                action=action,
                details=res.details,
                changes=changes,
            )
        except Exception as e:
            logger.error(f"Error in OneClickFixCenter executing fix {action}: {e}")
            return FixResult(
                success=False,
                action=action,
                details=str(e),
                changes=[],
            )

    def _log_audit(self, action: str, guild_id: str, details: str):
        """Log an audit entry."""
        self._audit_log.append({
            "action": action,
            "guild_id": str(guild_id),
            "details": details,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        })

    def get_audit_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Get recent audit log entries."""
        return self._audit_log[-limit:]
