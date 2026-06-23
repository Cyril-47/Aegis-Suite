"""
Raid Cog - Handles anti-raid detection and response.

Extracted from DiscordOptimizerBot for better maintainability.
"""

import discord
from discord.ext import commands
import logging
import datetime
from typing import Dict, List, Set

logger = logging.getLogger("aegis.bot.raid")


class RaidCog(commands.Cog, name="Raid"):
    """Anti-raid detection and response."""

    def __init__(self, bot):
        self.bot = bot
        self.recent_joins: Dict[int, List[datetime.datetime]] = {}
        self.raid_active: Set[int] = set()

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Track member joins for raid detection."""
        guild_id = member.guild.id
        
        # Initialize tracking for this guild
        if guild_id not in self.recent_joins:
            self.recent_joins[guild_id] = []
        
        # Record join time
        now = datetime.datetime.now(datetime.timezone.utc)
        self.recent_joins[guild_id].append(now)
        
        # Clean up old joins (keep last 5 minutes)
        cutoff = now - datetime.timedelta(minutes=5)
        self.recent_joins[guild_id] = [
            join_time for join_time in self.recent_joins[guild_id]
            if join_time > cutoff
        ]
        
        # Check for raid
        join_count = len(self.recent_joins[guild_id])
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(guild_id), {})
        anti_raid = guild_config.get("anti_raid", {})
        
        if anti_raid.get("enabled", False):
            threshold = anti_raid.get("threshold", 10)
            
            if join_count >= threshold and guild_id not in self.raid_active:
                await self._handle_raid_detected(member.guild, join_count)

    async def _handle_raid_detected(self, guild: discord.Guild, join_count: int):
        """Handle detected raid."""
        self.raid_active.add(guild.id)
        
        logger.warning(f"Raid detected in {guild.name}: {join_count} joins in 5 minutes")
        
        # Get anti-raid config
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(guild.id), {})
        anti_raid = guild_config.get("anti_raid", {})
        
        response_mode = anti_raid.get("response_mode", "alert")
        
        if response_mode == "lock":
            await self._lock_server(guild)
        elif response_mode == "verify":
            await self._enable_verification(guild)
        elif response_mode == "alert":
            await self._alert_admins(guild, join_count)
        
        # Record in analytics
        if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
            self.bot.analytics_engine.record_mod_action(
                str(guild.id),
                "system",
                "raid_detected",
                f"{join_count} joins in 5 minutes"
            )
        
        # Log incident
        await self._log_raid_incident(guild, join_count)

    async def _lock_server(self, guild: discord.Guild):
        """Lock server during raid."""
        try:
            # Lock all channels
            for channel in guild.text_channels:
                try:
                    overwrite = channel.overwrites_for(guild.default_role)
                    overwrite.send_messages = False
                    await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Anti-raid: Server locked")
                except discord.Forbidden:
                    pass
            
            # Send alert
            await self._send_raid_alert(guild, "Server has been locked due to raid detection.")
            
            # Auto-unlock after 10 minutes
            import asyncio
            await asyncio.sleep(600)
            await self._unlock_server(guild)
            
        except Exception as e:
            logger.error(f"Failed to lock server {guild.name}: {e}")

    async def _unlock_server(self, guild: discord.Guild):
        """Unlock server after raid."""
        try:
            for channel in guild.text_channels:
                try:
                    overwrite = channel.overwrites_for(guild.default_role)
                    overwrite.send_messages = None
                    await channel.set_permissions(guild.default_role, overwrite=overwrite, reason="Anti-raid: Server unlocked")
                except discord.Forbidden:
                    pass
            
            self.raid_active.discard(guild.id)
            await self._send_raid_alert(guild, "Server has been unlocked.")
            
        except Exception as e:
            logger.error(f"Failed to unlock server {guild.name}: {e}")

    async def _enable_verification(self, guild: discord.Guild):
        """Enable verification during raid."""
        try:
            import discord as discord_module
            await guild.edit(verification_level=discord_module.VerificationLevel.HIGH)
            await self._send_raid_alert(guild, "Verification level set to HIGH due to raid detection.")
        except Exception as e:
            logger.error(f"Failed to enable verification in {guild.name}: {e}")

    async def _alert_admins(self, guild: discord.Guild, join_count: int):
        """Alert admins about potential raid."""
        await self._send_raid_alert(guild, f"Potential raid detected: {join_count} joins in 5 minutes")

    async def _send_raid_alert(self, guild: discord.Guild, message: str):
        """Send raid alert to admin channel."""
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(guild.id), {})
        alert_channel_id = guild_config.get("alert_channel")
        
        if alert_channel_id:
            channel = guild.get_channel(int(alert_channel_id))
            if channel:
                embed = discord.Embed(
                    title="🚨 Raid Alert",
                    description=message,
                    color=discord.Color.red(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass

    async def _log_raid_incident(self, guild: discord.Guild, join_count: int):
        """Log raid incident to database."""
        try:
            from aegis.db.models import RaidEvent
            session = self.bot.db.session_factory()
            try:
                event = RaidEvent(
                    guild_id=str(guild.id),
                    detected_at=datetime.datetime.now(datetime.timezone.utc),
                    join_count=join_count,
                    window_seconds=300,
                    response_action="alert"
                )
                session.add(event)
                session.commit()
            finally:
                session.close()
        except Exception as e:
            logger.error(f"Failed to log raid incident: {e}")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(RaidCog(bot))
