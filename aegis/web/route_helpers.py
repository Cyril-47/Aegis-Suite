"""
Route Helpers for Aegis Suite.

Provides cached config access and performance utilities for routes.
"""

import logging
from typing import Dict, Any, Optional
from aegis.core.config_manager import get_config_manager

logger = logging.getLogger("aegis.web.route_helpers")


def get_cached_config() -> Dict[str, Any]:
    """Get cached configuration (fast path)."""
    return get_config_manager().load()


def get_cached_guild_config(guild_id: str) -> Dict[str, Any]:
    """Get cached guild configuration (fast path)."""
    return get_config_manager().get_guild_config(guild_id)


def set_cached_guild_config(guild_id: str, config: Dict[str, Any]) -> bool:
    """Set guild configuration (fast path)."""
    return get_config_manager().set_guild_config(guild_id, config)


def invalidate_config():
    """Invalidate config cache after changes."""
    from aegis.core.config_manager import get_config_manager
    get_config_manager()._invalidate_cache()
    from aegis.core.performance import invalidate_config_cache
    invalidate_config_cache()


def get_bot_stats() -> Dict[str, Any]:
    """Get bot statistics (cached)."""
    from aegis.bot.bot_manager import get_bot_stats as _get_bot_stats
    return _get_bot_stats()


def get_active_bot():
    """Get the active bot instance."""
    from aegis.web.routes.dashboard import get_active_bot as _get_active_bot
    return _get_active_bot()
