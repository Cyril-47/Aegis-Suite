"""
Welcome Cog - Handles welcome messages, auto-roles, and member events.

Extracted from DiscordOptimizerBot for better maintainability.
"""

import discord
from discord.ext import commands
import logging
import datetime
from typing import Optional

logger = logging.getLogger("aegis.bot.welcome")


class WelcomeCog(commands.Cog, name="Welcome"):
    """Welcome messages, auto-roles, and member event handling."""

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        """Handle member join events."""
        if member.bot:
            return
        
        # Record analytics
        if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
            self.bot.analytics_engine.record_member_event(
                str(member.guild.id),
                str(member.id),
                "join"
            )
        
        # Update stats
        self.bot.check_stats_reset()
        self.bot.stats["joins_today"] += 1
        
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(member.guild.id), {})
        
        # Send welcome message
        welcome_config = guild_config.get("welcome", {})
        if welcome_config.get("enabled", False):
            await self._send_welcome_message(member, welcome_config)
        
        # Assign auto-role
        auto_role_config = guild_config.get("autorole", {})
        if auto_role_config.get("enabled", False):
            await self._assign_auto_role(member, auto_role_config)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member):
        """Handle member leave events."""
        if member.bot:
            return
        
        # Record analytics
        if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
            self.bot.analytics_engine.record_member_event(
                str(member.guild.id),
                str(member.id),
                "leave"
            )

    async def _send_welcome_message(self, member: discord.Member, config: dict):
        """Send welcome message to the welcome channel."""
        channel_id = config.get("channel")
        if not channel_id:
            return
        
        channel = member.guild.get_channel(int(channel_id))
        if not channel:
            return
        
        # Get welcome message template
        message_template = config.get("message", "Welcome to the server, {user}!")
        
        # Replace placeholders
        message = message_template.replace("{user}", member.mention)
        message = message.replace("{server}", member.guild.name)
        message = message.replace("{membercount}", str(member.guild.member_count))
        
        # Create welcome embed if configured
        if config.get("use_embed", False):
            embed = discord.Embed(
                title=config.get("embed_title", f"Welcome to {member.guild.name}!"),
                description=message,
                color=discord.Color.green()
            )
            
            if config.get("embed_color"):
                try:
                    embed.color = discord.Color(int(config["embed_color"], 16))
                except ValueError:
                    pass
            
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.set_footer(text=f"Member #{member.guild.member_count}")
            
            try:
                await channel.send(embed=embed)
            except discord.Forbidden:
                pass
        else:
            try:
                await channel.send(message)
            except discord.Forbidden:
                pass

    async def _assign_auto_role(self, member: discord.Member, config: dict):
        """Assign auto-role to new member."""
        role_id = config.get("role_id")
        if not role_id:
            return
        
        role = member.guild.get_role(int(role_id))
        if not role:
            return
        
        try:
            await member.add_roles(role, reason="Auto-role assignment")
            logger.info(f"Assigned auto-role {role.name} to {member.name} in {member.guild.name}")
        except discord.Forbidden:
            logger.error(f"Failed to assign auto-role in {member.guild.name}: Missing permissions")
        except Exception as e:
            logger.error(f"Failed to assign auto-role: {e}")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(WelcomeCog(bot))
