"""
Scheduler Cog - Handles scheduled messages and automations.

Extracted from DiscordOptimizerBot for better maintainability.
"""

import discord
from discord.ext import commands, tasks
import logging
import datetime
import json
import os
import uuid
from aegis.core.utils import get_writeable_path

logger = logging.getLogger("aegis.bot.scheduler")


def parse_interval(interval_str: str) -> datetime.timedelta:
    """Parses interval strings like '30m', '1h', '1d' into timedelta."""
    interval_str = interval_str.strip().lower()
    if interval_str.endswith("m"):
        val = interval_str[:-1]
        if val.isdigit():
            return datetime.timedelta(minutes=int(val))
    elif interval_str.endswith("h"):
        val = interval_str[:-1]
        if val.isdigit():
            return datetime.timedelta(hours=int(val))
    elif interval_str.endswith("d"):
        val = interval_str[:-1]
        if val.isdigit():
            return datetime.timedelta(days=int(val))
    raise ValueError("Invalid interval format. Use '30m', '1h', '2d' etc.")


class SchedulerCog(commands.Cog, name="Scheduler"):
    """Scheduled messages and automations."""

    def __init__(self, bot):
        self.bot = bot
        self.check_scheduled_messages.start()

    def cog_unload(self):
        """Cancel the task when the cog is unloaded."""
        self.check_scheduled_messages.cancel()

    @tasks.loop(minutes=1)
    async def check_scheduled_messages(self):
        """Check for scheduled messages to send."""
        try:
            path = get_writeable_path("scheduled_messages.json")
            if not os.path.exists(path):
                return
                
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                return

            now = datetime.datetime.now(datetime.timezone.utc)
            updated = False
            
            for entry in data:
                try:
                    next_run = datetime.datetime.fromisoformat(entry["next_run"])
                    if now >= next_run:
                        # Send the message
                        channel_id = int(entry["channel_id"])
                        channel = self.bot.get_channel(channel_id)
                        if channel is None:
                            try:
                                channel = await self.bot.fetch_channel(channel_id)
                            except Exception:
                                pass
                        
                        if channel:
                            await channel.send(entry["message"])
                            logger.info(f"Sent scheduled message to channel {channel_id}")
                        
                        # Update times
                        td = parse_interval(entry["interval"])
                        entry["last_sent"] = now.isoformat()
                        entry["next_run"] = (now + td).isoformat()
                        updated = True
                except Exception as e:
                    logger.error(f"Error processing scheduled message {entry.get('id')}: {e}")
            
            if updated:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2)
                    
        except Exception as e:
            logger.error(f"Error checking scheduled messages: {e}")

    @commands.hybrid_command(name="schedule")
    @commands.has_permissions(manage_guild=True)
    async def schedule_command(self, ctx: commands.Context, channel: discord.TextChannel, interval: str, *, message: str):
        """Schedule a recurring message."""
        try:
            td = parse_interval(interval)
        except ValueError as e:
            await ctx.send(f"❌ {e}", ephemeral=True)
            return

        path = get_writeable_path("scheduled_messages.json")
        data = []
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception:
                pass

        now = datetime.datetime.now(datetime.timezone.utc)
        next_run = now + td

        new_entry = {
            "id": str(uuid.uuid4()),
            "guild_id": str(ctx.guild.id) if ctx.guild else None,
            "channel_id": channel.id,
            "interval": interval,
            "message": message,
            "last_sent": None,
            "next_run": next_run.isoformat()
        }
        data.append(new_entry)

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

        await ctx.send(f"✅ Message scheduled in {channel.mention} every {interval}.")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(SchedulerCog(bot))
