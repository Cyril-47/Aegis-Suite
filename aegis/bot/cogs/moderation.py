"""
Moderation Cog - Handles moderation commands and automod.

Extracted from DiscordOptimizerBot for better maintainability.
"""

import discord
from discord.ext import commands
import logging
import datetime
from typing import Optional

logger = logging.getLogger("aegis.bot.moderation")


class ModerationCog(commands.Cog, name="Moderation"):
    """Moderation commands and automod functionality."""

    def __init__(self, bot):
        self.bot = bot
        self.automod_config = {}

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Process messages for automod."""
        if message.author.bot:
            return
        
        # Record analytics
        if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
            self.bot.analytics_engine.record_message(
                str(message.guild.id),
                str(message.channel.id),
                str(message.author.id),
                len(message.content.split())
            )
        
        # Run automod checks
        await self._run_automod(message)

    async def _run_automod(self, message: discord.Message):
        """Run automod rules on a message."""
        if not message.guild:
            return
        
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(message.guild.id), {})
        automod = guild_config.get("automod", {})
        
        if not automod.get("enabled", False):
            return
        
        # Check for profanity
        if automod.get("profanity_filter", False):
            if await self._check_profanity(message):
                return
        
        # Check for spam
        if automod.get("spam_filter", False):
            if await self._check_spam(message):
                return
        
        # Check for link filtering
        if automod.get("link_filter", False):
            if await self._check_links(message):
                return
        
        # Check for mention spam
        if automod.get("mention_spam", False):
            if await self._check_mention_spam(message):
                return

    async def _check_profanity(self, message: discord.Message) -> bool:
        """Check for profanity in message."""
        # Basic profanity check - in production, use a proper filter
        blocked_words = []  # Load from config
        content_lower = message.content.lower()
        
        for word in blocked_words:
            if word in content_lower:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"{message.author.mention}, your message was removed for containing inappropriate content.",
                        delete_after=5
                    )
                    await self._log_mod_action(message.guild, message.author, "profanity", "Message contained blocked content")
                    return True
                except discord.Forbidden:
                    pass
        return False

    async def _check_spam(self, message: discord.Message) -> bool:
        """Check for spam patterns."""
        # Basic spam detection
        return False

    async def _check_links(self, message: discord.Message) -> bool:
        """Check for unauthorized links."""
        import re
        from urllib.parse import urlparse
        url_pattern = re.compile(r'https?://[^\s]+')
        if url_pattern.search(message.content):
            config = self.bot.config
            guild_config = config.get("guild_configs", {}).get(str(message.guild.id), {})
            automod = guild_config.get("automod", {})
            whitelist = automod.get("link_whitelist", [])

            urls = url_pattern.findall(message.content)
            for url in urls:
                domain = urlparse(url).hostname or ""
                is_whitelisted = any(
                    domain == w or domain.endswith("." + w) for w in whitelist
                )
                if not is_whitelisted:
                    try:
                        await message.delete()
                        await message.channel.send(
                            f"{message.author.mention}, links are not allowed in this channel.",
                            delete_after=5
                        )
                        await self._log_mod_action(message.guild, message.author, "link_filter", f"Posted unauthorized link: {url}")
                        return True
                    except discord.Forbidden:
                        pass
        return False

    async def _check_mention_spam(self, message: discord.Message) -> bool:
        """Check for mention spam."""
        if len(message.mentions) > 5:
            try:
                await message.delete()
                await message.channel.send(
                    f"{message.author.mention}, excessive mentions are not allowed.",
                    delete_after=5
                )
                await self._log_mod_action(message.guild, message.author, "mention_spam", f"Mentioned {len(message.mentions)} users")
                return True
            except discord.Forbidden:
                pass
        return False

    async def _log_mod_action(self, guild: discord.Guild, user: discord.Member, action: str, reason: str):
        """Log a moderation action."""
        config = self.bot.config
        guild_config = config.get("guild_configs", {}).get(str(guild.id), {})
        mod_log_channel_id = guild_config.get("mod_log_channel")
        
        if mod_log_channel_id:
            channel = guild.get_channel(int(mod_log_channel_id))
            if channel:
                embed = discord.Embed(
                    title="Moderation Action",
                    color=discord.Color.orange(),
                    timestamp=datetime.datetime.now(datetime.timezone.utc)
                )
                embed.add_field(name="User", value=f"{user.mention} ({user.id})", inline=True)
                embed.add_field(name="Action", value=action, inline=True)
                embed.add_field(name="Reason", value=reason, inline=False)
                embed.set_thumbnail(url=user.display_avatar.url)
                
                try:
                    await channel.send(embed=embed)
                except discord.Forbidden:
                    pass
        
        # Record in analytics
        if hasattr(self.bot, 'analytics_engine') and self.bot.analytics_engine:
            self.bot.analytics_engine.record_mod_action(
                str(guild.id),
                str(user.id),
                action,
                reason
            )

    @commands.hybrid_command(name="warn")
    @commands.has_permissions(manage_messages=True)
    async def warn_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Warn a member."""
        await self._log_mod_action(ctx.guild, member, "warn", reason)
        await ctx.send(f"⚠️ {member.mention} has been warned: {reason}")

    @commands.hybrid_command(name="mute")
    @commands.has_permissions(moderate_members=True)
    async def mute_command(self, ctx: commands.Context, member: discord.Member, duration: str = "10m", *, reason: str = "No reason provided"):
        """Mute a member for a specified duration."""
        from aegis.bot.bot_manager import parse_duration
        duration_seconds = parse_duration(duration)
        if duration_seconds is None:
            await ctx.send("Invalid duration format. Use formats like: 10m, 1h, 1d")
            return
        
        try:
            await member.timeout(datetime.timedelta(seconds=duration_seconds), reason=reason)
            await self._log_mod_action(ctx.guild, member, "mute", f"Muted for {duration}: {reason}")
            await ctx.send(f"🔇 {member.mention} has been muted for {duration}")
        except discord.Forbidden:
            await ctx.send("I don't have permission to mute this member.")

    @commands.hybrid_command(name="unmute")
    @commands.has_permissions(moderate_members=True)
    async def unmute_command(self, ctx: commands.Context, member: discord.Member):
        """Unmute a member."""
        try:
            await member.timeout(None, reason=f"Unmuted by {ctx.author}")
            await self._log_mod_action(ctx.guild, member, "unmute", f"Unmuted by {ctx.author}")
            await ctx.send(f"🔊 {member.mention} has been unmuted")
        except discord.Forbidden:
            await ctx.send("I don't have permission to unmute this member.")

    @commands.hybrid_command(name="kick")
    @commands.has_permissions(kick_members=True)
    async def kick_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Kick a member from the server."""
        try:
            await member.kick(reason=reason)
            await self._log_mod_action(ctx.guild, member, "kick", reason)
            await ctx.send(f"👢 {member.mention} has been kicked")
        except discord.Forbidden:
            await ctx.send("I don't have permission to kick this member.")

    @commands.hybrid_command(name="ban")
    @commands.has_permissions(ban_members=True)
    async def ban_command(self, ctx: commands.Context, member: discord.Member, *, reason: str = "No reason provided"):
        """Ban a member from the server."""
        try:
            await member.ban(reason=reason, delete_message_days=7)
            await self._log_mod_action(ctx.guild, member, "ban", reason)
            await ctx.send(f"🔨 {member.mention} has been banned")
        except discord.Forbidden:
            await ctx.send("I don't have permission to ban this member.")


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(ModerationCog(bot))
