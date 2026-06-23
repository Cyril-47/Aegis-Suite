"""
Maintenance Cog - Scheduled maintenance tasks.

Handles: role cleanup, DB vacuum, channel archive.
Reads maintenance_settings from config on each loop iteration.
"""

import discord
from discord.ext import commands, tasks
import logging
import datetime
import asyncio

logger = logging.getLogger("aegis.bot.maintenance")


class MaintenanceCog(commands.Cog, name="Maintenance"):
    """Scheduled maintenance tasks."""

    def __init__(self, bot):
        self.bot = bot
        self._role_cleanup_day = None
        self._vacuum_week = None
        self._archive_day = None
        self.maintenance_loop.start()

    def cog_unload(self):
        self.maintenance_loop.cancel()

    @tasks.loop(minutes=5)
    async def maintenance_loop(self):
        """Check and run maintenance tasks every 5 minutes."""
        try:
            import aegis.core.utils as utils
            config = utils.load_config()
            mt = config.get("maintenance_settings", {})
            now = datetime.datetime.now(datetime.timezone.utc)

            # Role Cleanup - daily at configured hour
            if mt.get("role_cleanup_enabled", False):
                target_hour = mt.get("role_cleanup_hour", 4)
                if now.hour == target_hour and self._role_cleanup_day != now.date():
                    self._role_cleanup_day = now.date()
                    await self._run_role_cleanup()

            # DB Vacuum - weekly on Sunday at configured hour
            if mt.get("db_vacuum_enabled", False):
                target_hour = mt.get("db_vacuum_hour", 5)
                week_key = now.isocalendar()[:2]
                if now.hour == target_hour and now.weekday() == 6 and self._vacuum_week != week_key:
                    self._vacuum_week = week_key
                    await self._run_db_vacuum()

            # Channel Archive - daily at 6 UTC
            if mt.get("channel_archive_enabled", False):
                if now.hour == 6 and self._archive_day != now.date():
                    self._archive_day = now.date()
                    inactive_days = mt.get("inactive_days", 30)
                    await self._run_channel_archive(inactive_days)

        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"Maintenance loop error: {e}")

    async def _run_role_cleanup(self):
        """Delete empty, unmanaged roles from all guilds."""
        logger.info("Starting role cleanup...")
        cleaned = 0
        for guild in self.bot.guilds:
            for role in guild.roles:
                if role.is_default() or role.managed:
                    continue
                if len(role.members) == 0:
                    try:
                        await role.delete(reason="Maintenance: empty role cleanup")
                        cleaned += 1
                        logger.info(f"Deleted empty role: {role.name} in {guild.name}")
                    except discord.Forbidden:
                        logger.warning(f"No permission to delete role {role.name} in {guild.name}")
                    except Exception as e:
                        logger.error(f"Failed to delete role {role.name}: {e}")
        logger.info(f"Role cleanup complete. Deleted {cleaned} empty roles.")

    async def _run_db_vacuum(self):
        """Run VACUUM on the SQLite database to reclaim space."""
        logger.info("Starting DB vacuum...")
        try:
            from aegis.core.app_core import _active_cores
            if _active_cores:
                engine = _active_cores[-1].db
                with engine.connect() as conn:
                    conn.execute(conn.default_dialect.statement_compiler(conn.dialect, None).process(
                        __import__('sqlalchemy').text("VACUUM")
                    ))
                logger.info("DB vacuum complete.")
            else:
                logger.warning("No active core found, skipping vacuum.")
        except Exception as e:
            logger.error(f"DB vacuum failed: {e}")

    async def _run_channel_archive(self, inactive_days: int):
        """Archive text channels with no messages in inactive_days."""
        logger.info(f"Starting channel archive check (inactive > {inactive_days} days)...")
        archived = 0
        cutoff = discord.utils.utcnow() - datetime.timedelta(days=inactive_days)

        for guild in self.bot.guilds:
            archive_category = discord.utils.get(guild.categories, name="ARCHIVED")
            if not archive_category:
                try:
                    archive_category = await guild.create_category("ARCHIVED", reason="Maintenance: archive category")
                except Exception:
                    continue

            for channel in guild.text_channels:
                if channel.category and channel.category.name == "ARCHIVED":
                    continue
                try:
                    last_message = None
                    async for msg in channel.history(limit=1, oldest_first=False):
                        last_message = msg
                    if last_message and last_message.created_at < cutoff:
                        await channel.edit(
                            category=archive_category,
                            sync_permissions=True,
                            reason=f"Maintenance: archived after {inactive_days} days inactive"
                        )
                        archived += 1
                        logger.info(f"Archived #{channel.name} in {guild.name}")
                except discord.Forbidden:
                    pass
                except Exception as e:
                    logger.error(f"Failed to check channel {channel.name}: {e}")

        logger.info(f"Channel archive complete. Archived {archived} channels.")


async def setup(bot):
    await bot.add_cog(MaintenanceCog(bot))
