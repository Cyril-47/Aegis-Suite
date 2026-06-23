"""
Giveaway Cog - Handles giveaway system.
"""

import discord
from discord.ext import commands
from discord import app_commands
import logging
from typing import Optional
from aegis.core.permissions.registry import CommandRegistry
from aegis.core.permissions.resolver import PermissionResolver

logger = logging.getLogger("aegis.bot.giveaway")


class GiveawayCog(commands.Cog, name="Giveaway"):
    """Giveaway management system."""

    def __init__(self, bot):
        self.bot = bot

    @commands.hybrid_command(name="giveaway", description="Manage giveaways.")
    @app_commands.describe(
        action="Action (start, end, reroll)",
        target="Target: For start: duration (e.g. 10m). For end/reroll: message ID",
        winners="Number of winners (For start)",
        prize="Prize description (For start)",
        channel="Destination channel (For start, optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def giveaway_command(
        self,
        ctx: commands.Context,
        action: str,
        target: str,
        winners: Optional[int] = 1,
        prize: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None
    ):
        from aegis.bot.bot_manager import parse_duration, start_giveaway_bot, reroll_giveaway_bot
        action = action.lower().strip()

        # Giveaway command permission check mapping
        action_map = {
            "start": CommandRegistry.GIVEAWAY_CREATE,
            "end": CommandRegistry.GIVEAWAY_STOP,
            "reroll": CommandRegistry.GIVEAWAY_REROLL
        }
        gw_cmd = action_map.get(action, CommandRegistry.GIVEAWAY_CREATE)
        user_roles = [str(role.id) for role in ctx.author.roles]
        is_owner = ctx.author.id == ctx.guild.owner_id
        has_admin = ctx.author.guild_permissions.administrator

        allowed = await PermissionResolver.has_permission(
            guild_id=str(ctx.guild.id),
            user_id=str(ctx.author.id),
            command_name=gw_cmd,
            user_roles=user_roles,
            is_owner=is_owner,
            has_discord_admin=has_admin
        )
        if not allowed:
            raise commands.MissingPermissions([f"Missing permissions to run command {gw_cmd}"])
        import aegis.core.utils as utils
        if action == "start":
            if not prize:
                await ctx.send("❌ You must specify a prize to start a giveaway.", ephemeral=True)
                return
            duration_secs = parse_duration(target)
            if not duration_secs:
                await ctx.send("❌ Invalid duration. Use format: e.g. 30s, 10m, 2h, 1d", ephemeral=True)
                return
                
            dest_channel = channel or ctx.channel
            await ctx.defer(ephemeral=True)
            try:
                msg_id = await start_giveaway_bot(
                    dest_channel,
                    prize,
                    winners,
                    duration_secs,
                    ctx.author.id
                )
                import aegis.core.audit_log as audit_log
                audit_log.log_action(
                    f"discord:{ctx.author.id}",
                    "GIVEAWAY_ACTION",
                    f"Started giveaway for '{prize}' (winners: {winners}, duration: {target})",
                    str(ctx.guild.id)
                )
                await ctx.send(f"✅ Giveaway started in {dest_channel.mention}! Message ID: `{msg_id}`", ephemeral=True)
            except Exception as e:
                await ctx.send(f"❌ Failed to start giveaway: {e}", ephemeral=True)
                
        elif action == "end":
            try:
                msg_id = int(target)
            except ValueError:
                await ctx.send("❌ Target must be a numeric Message ID for 'end' action.", ephemeral=True)
                return
                
            await ctx.defer(ephemeral=True)
            async with utils.giveaways_lock:
                giveaways = await utils.load_giveaways()
                if str(msg_id) not in giveaways:
                    await ctx.send("❌ Giveaway message ID not found in record.", ephemeral=True)
                    return
                    
                gw = giveaways[str(msg_id)]
                if gw.get("ended", False):
                    await ctx.send("❌ This giveaway has already ended.", ephemeral=True)
                    return
                    
                guild_id = int(gw["guild_id"])
                channel_id = int(gw["channel_id"])
                guild = self.bot.get_guild(guild_id)
                if guild:
                    ch = guild.get_channel(channel_id)
                    if ch:
                        try:
                            message = await ch.fetch_message(msg_id)
                            await self.bot.end_giveaway_action(message, gw, giveaways)
                            await utils.save_giveaways(giveaways)
                            import aegis.core.audit_log as audit_log
                            audit_log.log_action(
                                f"discord:{ctx.author.id}",
                                "GIVEAWAY_ACTION",
                                f"Force ended giveaway '{gw.get('prize')}' early",
                                str(ctx.guild.id)
                            )
                            await ctx.send("✅ Giveaway ended early successfully!", ephemeral=True)
                            return
                        except Exception as e:
                            await ctx.send(f"❌ Failed to end giveaway: {e}", ephemeral=True)
                            return
            await ctx.send("❌ Could not locate guild or channel for the giveaway.", ephemeral=True)
            
        elif action == "reroll":
            try:
                msg_id = int(target)
            except ValueError:
                await ctx.send("❌ Target must be a numeric Message ID for 'reroll' action.", ephemeral=True)
                return
                
            await ctx.defer(ephemeral=True)
            async with utils.giveaways_lock:
                giveaways = await utils.load_giveaways()
                if str(msg_id) not in giveaways:
                    await ctx.send("❌ Giveaway message ID not found in record.", ephemeral=True)
                    return
                    
                gw = giveaways[str(msg_id)]
                if not gw.get("ended", False):
                    await ctx.send("❌ This giveaway is still active. End it first before rerolling.", ephemeral=True)
                    return
                    
                guild_id = int(gw["guild_id"])
                channel_id = int(gw["channel_id"])
                guild = self.bot.get_guild(guild_id)
                if guild:
                    ch = guild.get_channel(channel_id)
                    if ch:
                        res = await reroll_giveaway_bot(ch, msg_id)
                        if res == "success":
                            import aegis.core.audit_log as audit_log
                            audit_log.log_action(
                                f"discord:{ctx.author.id}",
                                "GIVEAWAY_ACTION",
                                f"Rerolled winners for giveaway '{gw.get('prize')}'",
                                str(ctx.guild.id)
                            )
                            await ctx.send("✅ Rerolled winners successfully!", ephemeral=True)
                        else:
                            await ctx.send(f"❌ Failed to reroll: {res}", ephemeral=True)
                        return
            await ctx.send("❌ Could not locate channel for the giveaway.", ephemeral=True)
        else:
            await ctx.send("❌ Unknown action. Use 'start', 'end', or 'reroll'.", ephemeral=True)


async def setup(bot):
    """Add the cog to the bot."""
    await bot.add_cog(GiveawayCog(bot))
