import logging
import random
import string
import time
from typing import Optional
import discord
from discord.ext import commands
from discord import app_commands
from aegis.core.permissions.registry import CommandRegistry
from aegis.bot.permissions import universal_permission_check
from aegis.bot.music_permissions import music_permission_gate
from aegis.core.permissions.resolver import PermissionResolver

logger = logging.getLogger("aegis.bot.commands")

def register_commands(bot: commands.Bot) -> None:
    """Relocates and registers all Discord hybrid and slash commands to the bot."""
    
    # linkdashboard command
    @bot.hybrid_command(name="linkdashboard", description="Generates a temporary linking code for the web dashboard.")
    @app_commands.default_permissions(administrator=True)
    @universal_permission_check(CommandRegistry.LINK_DASHBOARD)
    async def slash_linkdashboard(ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used inside a Discord server.", ephemeral=True)
            return
            
        import aegis.core.utils as utils
        if not utils.can_generate_code(ctx.guild.id):
            await ctx.send("❌ A connection code was already generated for this server recently. Please use that code or wait 5 minutes before generating a new one.", ephemeral=True)
            return
            
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        embed = discord.Embed(
            title="🔗 Dashboard Connection Link",
            description=(
                f"Use this code to connect **{ctx.guild.name}** to your web dashboard:\n\n"
                f"### **`{code}`**\n\n"
                "⚠️ *This code is temporary and will expire in 10 minutes.*"
            ),
            color=discord.Color.blue()
        )
        
        if ctx.interaction:
            await ctx.defer(ephemeral=True)
            with utils.config_lock:
                config = utils.load_config()
                pending = config.setdefault("pending_pairings", {})
                pending[code] = {
                    "guild_id": str(ctx.guild.id),
                    "guild_name": ctx.guild.name,
                    "expires_at": time.time() + 600,
                    "attempts": 0
                }
                utils.save_config(config)
            await ctx.send(embed=embed, ephemeral=True)
        else:
            try:
                await ctx.author.send(embed=embed)
                with utils.config_lock:
                    config = utils.load_config()
                    pending = config.setdefault("pending_pairings", {})
                    pending[code] = {
                        "guild_id": str(ctx.guild.id),
                        "guild_name": ctx.guild.name,
                        "expires_at": time.time() + 600,
                        "attempts": 0
                    }
                    utils.save_config(config)
                await ctx.send("I've sent your dashboard connection code via DM.")
            except discord.Forbidden:
                await ctx.send("I couldn't send you a DM.\nPlease enable Direct Messages and try again.")

    # unlink command
    @bot.hybrid_command(name="unlink", description="Revokes the web dashboard link for this server.")
    @app_commands.describe(purge="Whether to completely wipe this server's dashboard configurations from the bot.")
    @app_commands.default_permissions(administrator=True)
    @universal_permission_check(CommandRegistry.UNLINK)
    async def slash_unlink(ctx: commands.Context, purge: bool = False):
        if not ctx.guild:
            await ctx.send("This command can only be used inside a Discord server.", ephemeral=True)
            return
            
        guild_id = str(ctx.guild.id)
        import aegis.core.auth as auth
        auth.revoke_guild_sessions(guild_id)
        
        details = "Sessions revoked."
        import aegis.core.utils as utils
        if purge:
            with utils.config_lock:
                config = utils.load_config()
                guild_configs = config.get("guild_configs", {})
                guild_configs.pop(guild_id, None)
                
                sched = config.get("scheduled_messages", [])
                config["scheduled_messages"] = [m for m in sched if m.get("guild_id") != guild_id]
                
                responders = config.get("auto_responders", [])
                config["auto_responders"] = [r for r in responders if r.get("guild_id") != guild_id]
                
                utils.save_config(config)
            
            import aegis.core.utils as bot_utils
            async with bot_utils.giveaways_lock:
                giveaways = await bot_utils.load_giveaways()
                to_delete = [msg_id for msg_id, gw in giveaways.items() if gw.get("guild_id") == guild_id]
                for msg_id in to_delete:
                    giveaways.pop(msg_id, None)
                await bot_utils.save_giveaways(giveaways)
            
            details += " Guild configuration, custom commands, scheduled messages, auto-responders, and giveaways purged."
            
        import aegis.core.audit_log as audit_log
        audit_log.log_action(f"discord_admin:{ctx.author.id}", "DEAUTHORIZE_ACTION", f"Unlinked server {guild_id}. Purge={purge}", guild_id)
        
        embed = discord.Embed(
            title="🔌 Dashboard Unlinked Successfully",
            description=(
                f"The web dashboard link for **{ctx.guild.name}** has been revoked.\n\n"
                f"**Details:** {details}\n\n"
                "To reconnect, run `/linkdashboard` to generate a new connection code."
            ),
            color=discord.Color.orange()
        )
        await ctx.send(embed=embed)

    # audit command
    @bot.hybrid_command(name="audit", description="Scans and audits the server structure and permissions.")
    @app_commands.default_permissions(administrator=True)
    @universal_permission_check(CommandRegistry.AUDIT_SERVER)
    async def slash_audit(ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            from aegis.bot.bot_manager import audit_guild_data
            
            online_count = None
            member_count = None
            try:
                # Fetch approximate counts using REST API to bypass disabled presence intent
                fetched = await ctx.bot.fetch_guild(ctx.guild.id, with_counts=True)
                if fetched:
                    online_count = fetched.approximate_presence_count
                    member_count = fetched.approximate_member_count
            except Exception as e:
                logger.warning(f"REST fetch_guild with counts failed in command: {e}", exc_info=True)

            audit_report = audit_guild_data(ctx.guild, online_count=online_count, member_count=member_count)
            score = audit_report["score"]
            
            embed = discord.Embed(
                title=f"🛡️ Server Audit Report for {ctx.guild.name}",
                description=f"**Optimization Score: {score}/100**",
                color=discord.Color.green() if score >= 80 else discord.Color.orange() if score >= 50 else discord.Color.red()
            )
            
            for item in audit_report["checklist"][:5]:
                status_emoji = "✅" if item["status"] == "SUCCESS" else "⚠️" if item["status"] == "WARNING" else "❌"
                embed.add_field(
                    name=f"{status_emoji} {item['name']}",
                    value=f"Status: **{item['value']}**\n{item['message']}",
                    inline=False
                )
            
            embed.set_footer(text="Manage detailed settings and optimization presets via the local Web Dashboard.")
            await ctx.send(embed=embed)
        except Exception as e:
            await ctx.send(f"An error occurred during audit: {e}")

    # optimize_server command
    @bot.hybrid_command(name="optimize_server", description="Optimizes the server. Warning: will reorganize channels.")
    @app_commands.describe(preset="Select a preset layout (gaming, community, developer)", handling="How to handle existing channels (archive, keep, delete)")
    @app_commands.default_permissions(administrator=True)
    @universal_permission_check(CommandRegistry.OPTIMIZE_SERVER)
    async def slash_optimize(ctx: commands.Context, preset: str, handling: str):
        if preset.lower() not in ["gaming", "community", "developer"]:
            await ctx.send("❌ Invalid preset. Use gaming, community, or developer.", ephemeral=True)
            return
        if handling.lower() not in ["archive", "keep", "delete"]:
            await ctx.send("❌ Invalid handling option. Use archive, keep, or delete.", ephemeral=True)
            return

        await ctx.send(f"⚙️ Starting server optimization under preset **{preset}** and handling **{handling}**... (This will take a moment)", ephemeral=True)
        try:
            from aegis.bot.bot_manager import optimize_guild_structure
            success = await optimize_guild_structure(ctx.guild, preset, handling)
            if success:
                await ctx.send("✅ Server optimization complete! Welcome and logs channels have been successfully established.", ephemeral=True)
            else:
                await ctx.send("❌ Server optimization failed. See console logs for details.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error during slash optimization: {e}")
            await ctx.send(f"❌ Error during optimization: {e}", ephemeral=True)

