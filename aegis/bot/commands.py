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
            
        import utils
        if not utils.can_generate_code(ctx.guild.id):
            await ctx.send("❌ A connection code was already generated for this server recently. Please use that code or wait 5 minutes before generating a new one.", ephemeral=True)
            return
            
        await ctx.defer(ephemeral=True)
        
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
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
            
        embed = discord.Embed(
            title="🔗 Dashboard Connection Link",
            description=(
                f"Use this code to connect **{ctx.guild.name}** to your web dashboard:\n\n"
                f"### **`{code}`**\n\n"
                "⚠️ *This code is temporary and will expire in 10 minutes.*"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed, ephemeral=True)

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
        import auth
        auth.revoke_guild_sessions(guild_id)
        
        details = "Sessions revoked."
        import utils
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
            
            import utils as bot_utils
            giveaways = await bot_utils.load_giveaways()
            to_delete = [msg_id for msg_id, gw in giveaways.items() if gw.get("guild_id") == guild_id]
            for msg_id in to_delete:
                giveaways.pop(msg_id, None)
            await bot_utils.save_giveaways(giveaways)
            
            details += " Guild configuration, custom commands, scheduled messages, auto-responders, and giveaways purged."
            
        import audit_log
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
            from bot_manager import audit_guild_data
            audit_report = audit_guild_data(ctx.guild)
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
            from bot_manager import optimize_guild_structure
            success = await optimize_guild_structure(ctx.guild, preset, handling)
            if success:
                await ctx.send("✅ Server optimization complete! Welcome and logs channels have been successfully established.", ephemeral=True)
            else:
                await ctx.send("❌ Server optimization failed. See console logs for details.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error during slash optimization: {e}")
            await ctx.send(f"❌ Error during optimization: {e}", ephemeral=True)

    # Music Bot commands
    @bot.hybrid_command(name="play", description="Plays a song from YouTube URL or search query.")
    @app_commands.describe(query="Song URL or YouTube search keywords")
    @music_permission_gate(CommandRegistry.MUSIC_PLAY)
    async def music_play(ctx: commands.Context, query: str):
        await ctx.defer()
        if not ctx.author.voice:
            await ctx.send("❌ You must be in a voice channel to use this command.")
            return
            
        player = bot.get_music_player(ctx.guild.id)
        if not player:
            await ctx.send("❌ Failed to initialize music player.")
            return
            
        try:
            if not player.voice_client or not player.voice_client.is_connected():
                await player.join_channel(ctx.author.voice.channel.id)
                
            song = await player.add_to_queue(query)
            await ctx.send(f"➕ Added **{song['title']}** to the queue!")
        except Exception as e:
            await ctx.send(f"❌ Error: {e}")

    @bot.hybrid_command(name="pause", description="Pauses current playback.")
    @music_permission_gate(CommandRegistry.MUSIC_PAUSE)
    async def music_pause(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if player and player.pause():
            await ctx.send("⏸️ Paused playback.")
        else:
            await ctx.send("❌ Music is not playing or already paused.")

    @bot.hybrid_command(name="resume", description="Resumes current playback.")
    @music_permission_gate(CommandRegistry.MUSIC_RESUME)
    async def music_resume(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if player and player.resume():
            await ctx.send("▶️ Resumed playback.")
        else:
            await ctx.send("❌ Playback is not paused.")

    @bot.hybrid_command(name="skip", description="Skips the current song.")
    @music_permission_gate(CommandRegistry.MUSIC_SKIP)
    async def music_skip(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if player and player.skip():
            await ctx.send("⏭️ Skipped current song.")
        else:
            await ctx.send("❌ Nothing is playing.")

    @bot.hybrid_command(name="stop", description="Stops music and clears queue.")
    @music_permission_gate(CommandRegistry.MUSIC_STOP)
    async def music_stop(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if player and player.stop():
            await ctx.send("⏹️ Playback stopped and queue cleared.")
        else:
            await ctx.send("❌ Nothing is playing.")

    @bot.hybrid_command(name="queue", description="Shows the current music queue.")
    @music_permission_gate(CommandRegistry.MUSIC_QUEUE)
    async def music_queue(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if not player or (not player.current and len(player.queue) == 0):
            await ctx.send("📭 The queue is empty.")
            return
            
        embed = discord.Embed(title="🎶 Music Queue", color=discord.Color.blurple())
        if player.current:
            embed.description = f"**Now Playing:** {player.current['title']}\n\n"
        else:
            embed.description = ""
            
        if len(player.queue) > 0:
            queue_list = []
            for idx, song in enumerate(player.queue[:10]):
                queue_list.append(f"`{idx+1}.` {song['title']}")
            if len(player.queue) > 10:
                queue_list.append(f"...and {len(player.queue) - 10} more songs.")
            embed.add_field(name="Upcoming:", value="\n".join(queue_list), inline=False)
        else:
            embed.add_field(name="Upcoming:", value="No songs in queue.", inline=False)
            
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="volume", description="Adjusts player volume.")
    @app_commands.describe(level="Volume level from 0 to 100")
    @music_permission_gate(CommandRegistry.MUSIC_VOLUME)
    async def music_volume(ctx: commands.Context, level: int):
        if level < 0 or level > 100:
            await ctx.send("❌ Volume must be between 0 and 100.")
            return
        player = bot.get_music_player(ctx.guild.id)
        if player:
            vol = player.set_volume(level / 100.0)
            await ctx.send(f"🔊 Volume set to **{int(vol * 100)}%**")
        else:
            await ctx.send("❌ Music player is not active.")

    @bot.hybrid_command(name="nowplaying", description="Shows details of the now playing song.")
    @music_permission_gate(CommandRegistry.MUSIC_NOWPLAYING)
    async def music_nowplaying(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if player and player.current:
            song = player.current
            embed = discord.Embed(title="📻 Now Playing", description=f"[{song['title']}]({song['webpage_url']})", color=discord.Color.green())
            if song.get("thumbnail"):
                embed.set_thumbnail(url=song["thumbnail"])
            duration_str = f"{song['duration'] // 60}:{song['duration'] % 60:02d}" if song.get("duration") else "Live Stream"
            embed.add_field(name="Duration", value=duration_str, inline=True)
            embed.add_field(name="Volume", value=f"{int(player.volume * 100)}%", inline=True)
            await ctx.send(embed=embed)
        else:
            await ctx.send("❌ Nothing is playing.")

    @bot.hybrid_command(name="shuffle", description="Shuffles the queue.")
    @music_permission_gate(CommandRegistry.MUSIC_SHUFFLE)
    async def music_shuffle(ctx: commands.Context):
        player = bot.get_music_player(ctx.guild.id)
        if player and len(player.queue) > 1:
            random.shuffle(player.queue)
            await ctx.send("🔀 Shuffled the queue.")
        else:
            await ctx.send("❌ Queue has fewer than 2 songs to shuffle.")

    # Leveling System commands
    @bot.hybrid_command(name="rank", description="Shows rank information.")
    @app_commands.describe(member="Select a member (optional)")
    @universal_permission_check(CommandRegistry.LEVEL_RANK)
    async def level_rank(ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        from aegis.bot.leveling import leveling_system
        rank_data = leveling_system.get_user_rank(ctx.guild.id, target.id)
        
        embed = discord.Embed(title=f"🏆 Rank Card for {target.name}", color=discord.Color.gold())
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="Level", value=f"**{rank_data['level']}**", inline=True)
        embed.add_field(name="Server Rank", value=f"**#{rank_data['rank']}**", inline=True)
        embed.add_field(name="Total XP", value=f"**{rank_data['xp']}**", inline=True)
        embed.add_field(name="Messages", value=f"**{rank_data['messages']}**", inline=True)
        
        pct = int((rank_data['xp_progress'] / max(1, rank_data['xp_needed_for_next'])) * 100)
        filled = int(pct / 10)
        bar = "🟩" * filled + "⬜" * (10 - filled)
        embed.add_field(name="XP Progress", value=f"{bar} ({pct}%)", inline=False)
        
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="leaderboard", description="Shows the server XP leaderboard.")
    @universal_permission_check(CommandRegistry.LEVEL_LEADERBOARD)
    async def level_leaderboard(ctx: commands.Context):
        from aegis.bot.leveling import leveling_system
        leaderboard = leveling_system.get_leaderboard(ctx.guild.id, 10)
        if not leaderboard:
            await ctx.send("📭 Leaderboard is empty. Start typing to earn XP!")
            return
            
        embed = discord.Embed(title=f"🏆 Server Leaderboard - {ctx.guild.name}", color=discord.Color.gold())
        desc = []
        for item in leaderboard:
            member = ctx.guild.get_member(int(item["user_id"]))
            m_name = member.name if member else f"User ID {item['user_id']}"
            desc.append(f"`#{item['rank']}` **{m_name}** - Level {item['level']} (XP: {item['xp']}, Messages: {item['messages']})")
            
        embed.description = "\n".join(desc)
        await ctx.send(embed=embed)

    @bot.hybrid_command(name="setlevelrole", description="Configures role reward for reaching a level.")
    @app_commands.describe(level="Level required", role="Role to reward")
    @app_commands.default_permissions(administrator=True)
    @universal_permission_check(CommandRegistry.LEVEL_SET_ROLE)
    async def level_setrole(ctx: commands.Context, level: int, role: discord.Role):
        import utils
        config = utils.load_config()
        if "leveling_settings" not in config:
            config["leveling_settings"] = {}
        if "level_roles" not in config["leveling_settings"]:
            config["leveling_settings"]["level_roles"] = {}
            
        config["leveling_settings"]["level_roles"][str(level)] = str(role.id)
        utils.save_config(config)
        bot.config = config
        
        await ctx.send(f"✅ Users reaching Level **{level}** will now automatically receive the **{role.name}** role!")

    # Giveaway command
    @bot.hybrid_command(name="giveaway", description="Manage giveaways.")
    @app_commands.describe(
        action="Action (start, end, reroll)",
        target="Target: For start: duration (e.g. 10m). For end/reroll: message ID",
        winners="Number of winners (For start)",
        prize="Prize description (For start)",
        channel="Destination channel (For start, optional)"
    )
    @app_commands.default_permissions(administrator=True)
    async def slash_giveaway(
        ctx: commands.Context,
        action: str,
        target: str,
        winners: Optional[int] = 1,
        prize: Optional[str] = None,
        channel: Optional[discord.TextChannel] = None
    ):
        from bot_manager import parse_duration, start_giveaway_bot, reroll_giveaway_bot
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
        import utils
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
                guild = bot.get_guild(guild_id)
                if guild:
                    ch = guild.get_channel(channel_id)
                    if ch:
                        try:
                            message = await ch.fetch_message(msg_id)
                            await bot.end_giveaway_action(message, gw, giveaways)
                            await utils.save_giveaways(giveaways)
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
                guild = bot.get_guild(guild_id)
                if guild:
                    ch = guild.get_channel(channel_id)
                    if ch:
                        res = await reroll_giveaway_bot(ch, msg_id)
                        if res == "success":
                            await ctx.send("✅ Rerolled winners successfully!", ephemeral=True)
                        else:
                            await ctx.send(f"❌ Failed to reroll: {res}", ephemeral=True)
                        return
            await ctx.send("❌ Could not locate channel for the giveaway.", ephemeral=True)
        else:
            await ctx.send("❌ Unknown action. Use 'start', 'end', or 'reroll'.", ephemeral=True)
