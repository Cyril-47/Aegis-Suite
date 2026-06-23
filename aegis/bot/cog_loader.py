"""
Cog Loader - Loads all cogs into the bot.

This module provides a centralized way to load all cogs
and maintain backward compatibility with the existing bot.
"""

import logging
import importlib
from typing import List

logger = logging.getLogger("aegis.bot.cog_loader")


# List of all cogs to load
COGS = [
    "aegis.bot.cogs.moderation",
    "aegis.bot.cogs.raid",
    "aegis.bot.cogs.welcome",
    "aegis.bot.cogs.ticket",
    "aegis.bot.cogs.giveaway",
    "aegis.bot.cogs.leveling",
    "aegis.bot.cogs.music",
    "aegis.bot.cogs.scheduler",
    "aegis.bot.cogs.backup",
]


async def load_all_cogs(bot):
    """Load all cogs into the bot."""
    loaded = []
    failed = []
    
    for cog_path in COGS:
        try:
            await bot.load_extension(cog_path)
            loaded.append(cog_path)
            logger.info(f"Loaded cog: {cog_path}")
        except Exception as e:
            failed.append((cog_path, str(e)))
            logger.error(f"Failed to load cog {cog_path}: {e}")
    
    logger.info(f"Loaded {len(loaded)} cogs, {len(failed)} failed")
    
    if failed:
        for cog_path, error in failed:
            logger.error(f"  - {cog_path}: {error}")
    
    return loaded, failed


async def unload_all_cogs(bot):
    """Unload all cogs from the bot."""
    for cog_path in COGS:
        try:
            if cog_path in bot.extensions:
                await bot.unload_extension(cog_path)
                logger.info(f"Unloaded cog: {cog_path}")
        except Exception as e:
            logger.error(f"Failed to unload cog {cog_path}: {e}")


def get_cog_list() -> List[str]:
    """Get list of all available cogs."""
    return COGS.copy()
