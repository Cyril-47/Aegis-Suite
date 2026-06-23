"""
Ticket Cog - Handles support ticket system.

Extracted from DiscordOptimizerBot for better maintainability.
"""

import discord
from discord.ext import commands
import logging
import datetime
from typing import Optional

logger = logging.getLogger("aegis.bot.ticket")


class TicketCog(commands.Cog, name="Ticket"):
    """Support ticket system."""

    def __init__(self, bot):
        self.bot = bot
        self.active_tickets = {}

    @commands.hybrid_command(name="ticket")
    async def ticket_command(self, ctx: commands.Context, *, issue: str = "No issue specified"):
        """Create a support ticket."""
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(ctx.guild.id), {})
        ticket_config = guild_config.get("tickets", {})
        
        if not ticket_config.get("enabled", False):
            await ctx.send("Ticket system is not enabled for this server.")
            return
        
        # Create ticket channel
        category_id = ticket_config.get("category_id")
        category = ctx.guild.get_channel(int(category_id)) if category_id else None
        
        try:
            channel = await ctx.guild.create_text_channel(
                f"ticket-{ctx.author.name}",
                category=category,
                reason=f"Ticket created by {ctx.author}"
            )
            
            # Set permissions
            await channel.set_permissions(ctx.guild.default_role, read_messages=False)
            await channel.set_permissions(ctx.author, read_messages=True, send_messages=True)
            
            # Send ticket message
            embed = discord.Embed(
                title="Support Ticket",
                description=f"**Issue:** {issue}\n**Created by:** {ctx.author.mention}",
                color=discord.Color.blue(),
                timestamp=datetime.datetime.now(datetime.timezone.utc)
            )
            embed.set_footer(text=f"Ticket ID: {channel.id}")
            
            await channel.send(embed=embed)
            await ctx.send(f"✅ Ticket created: {channel.mention}")
            
            # Record in analytics
            if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
                self.bot.analytics_engine.record_mod_action(
                    guild_id=str(ctx.guild.id),
                    user_id=str(ctx.author.id),
                    moderator_id=str(ctx.author.id),
                    event_type="ticket_opened",
                    reason=issue,
                    automod_category="ticket",
                )
            
            self.bot.check_stats_reset()
            self.bot.stats["tickets_today"] += 1
            
        except discord.Forbidden:
            await ctx.send("I don't have permission to create channels.")
        except Exception as e:
            logger.error(f"Failed to create ticket: {e}")
            await ctx.send("Failed to create ticket. Please try again.")

    @commands.hybrid_command(name="close")
    async def close_command(self, ctx: commands.Context, *, reason: str = "No reason provided"):
        """Close the current ticket."""
        if not ctx.channel.name.startswith("ticket-"):
            await ctx.send("This command can only be used in ticket channels.")
            return
        
        # Archive the channel
        try:
            await ctx.channel.edit(name=f"closed-{ctx.channel.name}")
            await ctx.send(f"✅ Ticket closed by {ctx.author.mention}. Reason: {reason}")
            
            # Record in analytics
            if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
                self.bot.analytics_engine.record_mod_action(
                    guild_id=str(ctx.guild.id),
                    user_id=str(ctx.author.id),
                    moderator_id=str(ctx.author.id),
                    event_type="ticket_closed",
                    reason=reason,
                    automod_category="ticket",
                )
            
            # Delete after 10 seconds
            import asyncio
            await asyncio.sleep(10)
            await ctx.channel.delete(reason=f"Ticket closed: {reason}")
            
        except discord.Forbidden:
            await ctx.send("I don't have permission to modify this channel.")
        except Exception as e:
            logger.error(f"Failed to close ticket: {e}")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(TicketCog(bot))
