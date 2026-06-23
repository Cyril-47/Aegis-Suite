"""
Aegis Bot Cogs Package.

Modular cog system for DiscordOptimizerBot.
Each cog handles a specific feature set.
"""

from aegis.bot.cogs.moderation import ModerationCog
from aegis.bot.cogs.raid import RaidCog
from aegis.bot.cogs.welcome import WelcomeCog
from aegis.bot.cogs.ticket import TicketCog
from aegis.bot.cogs.giveaway import GiveawayCog
from aegis.bot.cogs.leveling import LevelingCog
from aegis.bot.cogs.music import MusicCog
from aegis.bot.cogs.scheduler import SchedulerCog
from aegis.bot.cogs.backup import BackupCog
from aegis.bot.cogs.maintenance import MaintenanceCog

__all__ = [
    "ModerationCog",
    "RaidCog",
    "WelcomeCog",
    "TicketCog",
    "GiveawayCog",
    "LevelingCog",
    "MusicCog",
    "SchedulerCog",
    "BackupCog",
    "MaintenanceCog",
]
