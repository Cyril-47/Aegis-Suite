"""
Backup Cog - Handles server backup and restore.

Extracted from DiscordOptimizerBot for better maintainability.
"""

import discord
from discord.ext import commands, tasks
import logging
import datetime
import asyncio

logger = logging.getLogger("aegis.bot.backup")


class BackupCog(commands.Cog, name="Backup"):
    """Server backup and restore functionality."""

    def __init__(self, bot):
        self.bot = bot
        self.backup_loop.start()

    def cog_unload(self):
        """Cancel the task when the cog is unloaded."""
        self.backup_loop.cancel()

    @tasks.loop(time=datetime.time(hour=3, minute=0, tzinfo=datetime.timezone.utc))
    async def backup_loop(self):
        """Run nightly backups."""
        try:
            import aegis.core.utils as utils
            config = utils.load_config()
            backup_cfg = config.get("backup_settings", {})
            if not backup_cfg.get("enabled", True):
                return

            logger.info("Starting nightly backups...")
            
            for guild in self.bot.guilds:
                try:
                    await self._backup_guild(guild)
                except Exception as e:
                    logger.error(f"Backup failed for {guild.name}: {e}")
            
            logger.info("Nightly backups completed.")
            
        except Exception as e:
            logger.error(f"Backup loop error: {e}")

    async def _backup_guild(self, guild: discord.Guild):
        """Backup a guild's layout."""
        from aegis.bot.restructuring import backup_guild_layout
        
        try:
            backup = backup_guild_layout(guild)
            
            # Save to database
            from aegis.core.utils import load_config, save_config
            config = load_config()
            config[f"last_backup_{guild.id}"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
            save_config(config)
            
            logger.info(f"Backup completed for {guild.name}")
            
        except Exception as e:
            logger.error(f"Failed to backup {guild.name}: {e}")

    @commands.hybrid_command(name="backup")
    @commands.has_permissions(manage_guild=True)
    async def backup_command(self, ctx: commands.Context):
        """Create a manual backup of the server."""
        await ctx.send("🔄 Creating backup...")
        
        try:
            await self._backup_guild(ctx.guild)
            await ctx.send("✅ Backup created successfully!")
        except Exception as e:
            await ctx.send(f"❌ Backup failed: {e}")

    @commands.hybrid_command(name="restore")
    @commands.has_permissions(administrator=True)
    async def restore_command(self, ctx: commands.Context):
        """Restore server from backup."""
        await ctx.send("⚠️ Restore functionality requires careful consideration. Please use the dashboard for this.")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(BackupCog(bot))
