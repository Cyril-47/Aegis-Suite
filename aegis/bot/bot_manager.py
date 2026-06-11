import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands
import utils
import re
import time
import json
import datetime
from typing import Optional
import auth
import audit_log

logger = logging.getLogger("DiscordBot")

# Global reference to the bot instance and background task
bot_instance = None
bot_task = None

# Regular Expressions for Safe AutoMod Enforcement (Backtracking Protected)
DISCORD_INVITE_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li|club)|discord(?:app)?\.com/invite)/([a-zA-Z0-9_-]{1,32})',
    re.IGNORECASE
)

URL_DOMAIN_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?([a-zA-Z0-9](?:[-a-zA-Z0-9]*[a-zA-Z0-9])?\.[a-zA-Z]{2,24}(?:\.[a-zA-Z]{2,24})*)',
    re.IGNORECASE
)

def get_bot():
    return bot_instance

from aegis.bot.tickets import TicketCloseView, TicketPanelView

from aegis.bot.giveaways import GiveawayJoinView, start_giveaway_bot, reroll_giveaway_bot

class DiscordOptimizerBot(commands.Bot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.config = utils.load_config()
        self.stats_date = datetime.datetime.now(datetime.timezone.utc).date()
        self.stats = {
            "messages_today": 0,
            "commands_today": 0,
            "tickets_today": 0,
            "joins_today": 0,
            "uptime_start": datetime.datetime.now(datetime.timezone.utc).isoformat()
        }
        self.music_players = {}
        self.scheduler_task = None

    def check_stats_reset(self):
        """Resets daily stats if the UTC date has changed (Tier 3.5)"""
        now = datetime.datetime.now(datetime.timezone.utc).date()
        if now != self.stats_date:
            self.stats_date = now
            self.stats["messages_today"] = 0
            self.stats["commands_today"] = 0
            self.stats["tickets_today"] = 0
            self.stats["joins_today"] = 0

    def get_music_player(self, guild_id: int):
        if guild_id not in self.music_players:
            guild = self.get_guild(guild_id)
            if guild:
                from music_manager import MusicPlayer
                self.music_players[guild_id] = MusicPlayer(guild)
        return self.music_players.get(guild_id)

    async def setup_hook(self):
        # Register events & commands
        logger.info("Setting up bot hooks and syncing slash commands...")
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        self.add_view(GiveawayJoinView())
        
        # Start scheduled messages background scheduler and watchdog
        self.scheduler_task = self.loop.create_task(self.scheduler_loop())
        self.giveaway_task = self.loop.create_task(self.giveaway_scheduler_loop())
        self.watchdog_task = self.loop.create_task(self.watchdog_loop())
        
        # Only sync when requested or on dev guild to protect rate limits (Tier 3.14)
        dev_guild_id = self.config.get("dev_guild_id")
        if dev_guild_id:
            try:
                await self.tree.sync(guild=discord.Object(id=int(dev_guild_id)))
                logger.info(f"Slash command tree synced to dev guild: {dev_guild_id}")
            except Exception as e:
                logger.error(f"Failed to sync slash commands to dev guild: {e}")
        else:
            try:
                if self.config.get("sync_commands", True):
                    await self.tree.sync()
                    logger.info("Slash command tree synced globally.")
                    self.config["sync_commands"] = False
                    utils.save_config(self.config)
                else:
                    logger.info("Slash command tree sync skipped (already synced).")
            except Exception as e:
                logger.error(f"Failed to sync slash commands globally: {e}")

    async def watchdog_loop(self):
        logger.info("Watchdog loop started.")
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                # Monitor scheduler_loop
                if self.scheduler_task is None or self.scheduler_task.done():
                    if self.scheduler_task and self.scheduler_task.done() and self.scheduler_task.exception():
                        exc = self.scheduler_task.exception()
                        logger.error(f"Scheduler loop crashed with exception: {exc}. Restarting...")
                    else:
                        logger.warning("Scheduler loop is not running. Restarting...")
                    self.scheduler_task = self.loop.create_task(self.scheduler_loop())

                # Monitor giveaway_scheduler_loop
                if self.giveaway_task is None or self.giveaway_task.done():
                    if self.giveaway_task and self.giveaway_task.done() and self.giveaway_task.exception():
                        exc = self.giveaway_task.exception()
                        logger.error(f"Giveaway loop crashed with exception: {exc}. Restarting...")
                    else:
                        logger.warning("Giveaway loop is not running. Restarting...")
                    self.giveaway_task = self.loop.create_task(self.giveaway_scheduler_loop())
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")
            await asyncio.sleep(30)

    async def scheduler_loop(self):
        logger.info("Scheduled messages background scheduler loop started.")
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                config = utils.load_config()
                scheduled = config.get("scheduled_messages", [])
                
                config_changed = False
                for msg in scheduled:
                    if not msg.get("enabled", True):
                        continue
                    
                    try:
                        msg_id = msg.get("id")
                        guild_id_str = msg.get("guild_id")
                        channel_id_str = msg.get("channel_id")
                        
                        if not msg_id or not guild_id_str or not channel_id_str:
                            logger.error(f"Scheduled message is missing critical fields (id, guild_id, channel_id). Disabling: {msg}")
                            msg["enabled"] = False
                            config_changed = True
                            continue
                            
                        next_run_str = msg.get("next_run")
                        if not next_run_str:
                            continue
                            
                        next_run = datetime.datetime.fromisoformat(next_run_str)
                        if next_run.tzinfo is None:
                            next_run = next_run.replace(tzinfo=datetime.timezone.utc)
                        if now >= next_run:
                            # Message is due! Send it.
                            guild_id = int(guild_id_str)
                            channel_id = int(channel_id_str)
                            guild = self.get_guild(guild_id)
                            if guild:
                                channel = guild.get_channel(channel_id)
                                if channel:
                                    try:
                                        embed_data = msg.get("embed")
                                        if embed_data:
                                            embed = discord.Embed.from_dict(embed_data)
                                            await channel.send(content=msg.get("content") or None, embed=embed)
                                        else:
                                            await channel.send(content=msg["content"])
                                        logger.info(f"Fired scheduled message '{msg['id']}' in #{channel.name}")
                                    except Exception as e:
                                        logger.error(f"Failed to send scheduled message '{msg['id']}': {e}")
                                        
                            # Update next_run or disable if once
                            if msg["schedule_type"] == "once":
                                msg["enabled"] = False
                                msg["next_run"] = None
                            else:
                                interval = msg.get("interval_type", "daily")
                                val = int(msg.get("interval_value", 1))
                                if interval == "hourly":
                                    next_run = next_run + datetime.timedelta(hours=val)
                                elif interval == "daily":
                                    next_run = next_run + datetime.timedelta(days=val)
                                elif interval == "weekly":
                                    next_run = next_run + datetime.timedelta(weeks=val)
                                else:
                                    next_run = next_run + datetime.timedelta(days=1)
                                    
                                msg["next_run"] = next_run.isoformat()
                                msg["last_run"] = now.isoformat()
                                
                            config_changed = True
                    except Exception as e:
                        logger.error(f"Error processing scheduled message '{msg.get('id', 'unknown')}': {e}")
                        
                if config_changed:
                    # Reload config under config_lock to avoid overwriting concurrent API edits
                    with utils.config_lock:
                        new_config = utils.load_config()
                        new_scheduled = new_config.get("scheduled_messages", [])
                        new_sched_map = {m["id"]: m for m in new_scheduled}
                        for msg in scheduled:
                            if msg.get("id") in new_sched_map:
                                new_sched_map[msg["id"]]["enabled"] = msg["enabled"]
                                new_sched_map[msg["id"]]["next_run"] = msg["next_run"]
                                if "last_run" in msg:
                                    new_sched_map[msg["id"]]["last_run"] = msg["last_run"]
                        new_config["scheduled_messages"] = new_scheduled
                        utils.save_config(new_config)
                        self.config = new_config
                    
            except Exception as e:
                logger.error(f"Error in scheduler loop: {e}")
                
            await asyncio.sleep(10)

    async def giveaway_scheduler_loop(self):
        logger.info("Giveaways background scheduler loop started.")
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                import time
                now = time.time()
                async with utils.giveaways_lock:
                    giveaways = await utils.load_giveaways()
                    config_changed = False
                    
                    for msg_id, gw in list(giveaways.items()):
                        if gw.get("ended", False):
                            continue
                        
                        if now >= gw.get("end_time", 0):
                            guild_id = int(gw["guild_id"])
                            channel_id = int(gw["channel_id"])
                            guild = self.get_guild(guild_id)
                            if guild:
                                channel = guild.get_channel(channel_id)
                                if channel:
                                    try:
                                        message = await channel.fetch_message(int(msg_id))
                                        await self.end_giveaway_action(message, gw, giveaways)
                                        config_changed = True
                                    except Exception as e:
                                        logger.error(f"Failed to automatically end giveaway {msg_id}: {e}")
                                        gw["ended"] = True
                                        config_changed = True
                                        
                    if config_changed:
                        await utils.save_giveaways(giveaways)
            except Exception as e:
                logger.error(f"Error in giveaway scheduler: {e}")
            await asyncio.sleep(10)

    async def end_giveaway_action(self, message, gw, giveaways):
        import random
        entrants = gw.get("entrants", [])
        winners_count = gw.get("winners_count", 1)
        prize = gw.get("prize", "Unknown Prize")
        
        winners = []
        if entrants:
            actual_winners_count = min(len(entrants), winners_count)
            winners = random.sample(entrants, actual_winners_count)
            
        gw["winners"] = winners
        gw["ended"] = True
        
        giveaways[str(message.id)] = gw
        
        host_id = gw.get("host_id")
        host_name = gw.get("host_name")
        if not host_name:
            host_name = "Aegis Suite"
            if host_id:
                try:
                    host_member = await message.guild.fetch_member(int(host_id))
                    host_name = host_member.display_name
                except Exception:
                    host_member = message.guild.get_member(int(host_id))
                    if host_member:
                        host_name = host_member.display_name
                    elif int(host_id) == message.guild.me.id:
                        host_name = message.guild.me.display_name
                    else:
                        host_name = f"User (ID: {host_id})"
        
        embeds = message.embeds
        if embeds:
            embed = embeds[0]
            new_embed = discord.Embed.from_dict(embed.to_dict())
            new_embed.title = "🎉 GIVEAWAY ENDED 🎉"
            new_embed.color = discord.Color.dark_gray()
            
            new_embed.clear_fields()
            new_embed.add_field(name="🎁 Prize", value=prize, inline=True)
            
            winners_mentions = ", ".join([f"<@{w}>" for w in winners]) if winners else "No entrants."
            new_embed.add_field(name="🏆 Winners", value=winners_mentions, inline=True)
            new_embed.add_field(name="👥 Total Participants", value=f"**{len(entrants)}** entrant(s)", inline=True)
            new_embed.set_footer(text=f"Hosted by {host_name}")
            
            view = discord.ui.View()
            btn = discord.ui.Button(label=f"Giveaway Ended ({len(entrants)})", style=discord.ButtonStyle.secondary, disabled=True, custom_id="giveaway_ended_btn")
            view.add_item(btn)
            
            await message.edit(embed=new_embed, view=view)
            
            if winners:
                await message.channel.send(
                    f"🎉 Congratulations to {winners_mentions}! You won **{prize}**! 🎁"
                )
            else:
                await message.channel.send(
                    f"😭 The giveaway for **{prize}** ended, but there were no participants."
                )

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        # Unwrap CommandInvokeError to get the original exception
        if isinstance(error, commands.CommandInvokeError):
            error = error.original

        if isinstance(error, commands.CommandNotFound):
            # Check if this message was actually a custom command
            msg_clean = ctx.message.content.strip()
            custom_cmds = utils.get_guild_custom_commands(self.config, ctx.guild.id) if ctx.guild else {}
            custom_cmds_lower = {k.lower(): v for k, v in custom_cmds.items()}
            if msg_clean.lower() in custom_cmds_lower:
                return
            logger.warning(f"Command not found: {ctx.message.content}")
            return

        if isinstance(error, commands.MissingPermissions):
            try:
                msg = "❌ You do not have permission to run this command."
                if error.missing_permissions:
                    custom_msg = error.missing_permissions[0]
                    if any(x in custom_msg for x in ["Missing permissions", "Universal Permission"]):
                        msg = f"❌ {custom_msg}"
                await ctx.send(msg, delete_after=5.0)
            except Exception:
                pass
            return
        
        # Log other errors
        logger.error(f"Error executing command: {error}", exc_info=error)

    async def on_ready(self):
        logger.info(f"Bot logged in successfully as {self.user} (ID: {self.user.id})")
        logger.info(f"Currently connected to {len(self.guilds)} guilds.")

    async def on_member_join(self, member: discord.Member):
        logger.info(f"New member joined: {member.name} in guild '{member.guild.name}'")
        self.stats["joins_today"] = self.stats.get("joins_today", 0) + 1
        config = utils.load_config()
        welcome = utils.get_guild_welcome_settings(config, member.guild.id)
        
        if not welcome.get("enabled", False):
            return

        # 1. Post Welcome Embed
        channel = None
        # Attempt by configured ID first
        if welcome.get("channel_id"):
            channel = member.guild.get_channel(int(welcome["channel_id"]))
        
        # Fallback to channel by name
        if not channel:
            channel_name = welcome.get("channel_name", "welcome").lstrip("#").lower()
            for ch in member.guild.text_channels:
                if ch.name.lower() == channel_name:
                    channel = ch
                    break

        if channel:
            try:
                title = welcome.get("message_title", "Welcome to the Server, {user}!").replace("{user}", member.name).replace("{server}", member.guild.name)
                desc = welcome.get("message_description", "").replace("{user}", member.mention).replace("{server}", member.guild.name)
                color_hex = welcome.get("embed_color", "#6366F1").replace("#", "")
                
                try:
                    color = discord.Color(int(color_hex, 16))
                except ValueError:
                    color = discord.Color.blurple()

                embed = discord.Embed(
                    title=title,
                    description=desc,
                    color=color
                )
                embed.set_thumbnail(url=member.display_avatar.url)
                embed.set_footer(text=f"Member #{member.guild.member_count}")
                
                await channel.send(embed=embed)
                logger.info(f"Sent welcome embed to #{channel.name}")
            except Exception as e:
                logger.error(f"Error sending welcome message: {e}")
        else:
            logger.warning("Welcome channel not found. Could not send welcome embed.")

        # 2. Auto-Assign Roles
        auto_roles = welcome.get("auto_assign_roles", [])
        if auto_roles:
            for role_identifier in auto_roles:
                role = None
                # Check if identifier is numerical ID or string name
                if str(role_identifier).isdigit():
                    role = member.guild.get_role(int(role_identifier))
                if not role:
                    role = discord.utils.find(lambda r: r.name.lower() == str(role_identifier).lower(), member.guild.roles)

                if role:
                    try:
                        await member.add_roles(role)
                        logger.info(f"Auto-assigned role '{role.name}' to {member.name}")
                    except Exception as e:
                        logger.error(f"Failed to auto-assign role '{role.name}': {e}")
                else:
                    logger.warning(f"Auto-assign role '{role_identifier}' not found in guild.")

    async def on_member_remove(self, member: discord.Member):
        logger.info(f"Member left: {member.name} from guild '{member.guild.name}'")

    async def on_guild_remove(self, guild: discord.Guild):
        logger.info(f"Bot was removed from guild: {guild.name} (ID: {guild.id})")
        # Revoke sessions
        auth.revoke_guild_sessions(guild.id)
        
        # Idempotently clear layout config
        with utils.config_lock:
            config = utils.load_config()
            guild_configs = config.get("guild_configs", {})
            guild_configs.pop(str(guild.id), None)
            
            # Clean up pending pairings for this guild
            pending = config.get("pending_pairings", {})
            for code, data in list(pending.items()):
                if data.get("guild_id") == str(guild.id):
                    pending.pop(code, None)
                    
            utils.save_config(config)
            
        # Clean up in-memory music players
        self.music_players.pop(guild.id, None)
        audit_log.log_action("discord_system", "DEAUTHORIZE_ACTION", f"Bot kicked/removed from server {guild.id}", str(guild.id))

    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState):
        # Clean up music player when bot leaves voice (Tier 4.2)
        if member.id == self.user.id:
            player = self.music_players.get(member.guild.id)
            if after.channel is None:
                player = self.music_players.pop(member.guild.id, None)
                if player:
                    if player.disconnect_task and not player.disconnect_task.done():
                        player.disconnect_task.cancel()
                    player.disconnect_task = None
                    player.auto_leave_reason = None
                return
            elif before.channel is None and after.channel is not None:
                # Bot joined a channel. Check if alone
                if player:
                    if player.disconnect_task and not player.disconnect_task.done():
                        player.disconnect_task.cancel()
                        player.disconnect_task = None
                        player.auto_leave_reason = None
                    human_members = [m for m in after.channel.members if not m.bot]
                    if len(human_members) == 0:
                        player._start_auto_leave_timer(60, "alone")
                        logger.info(f"Bot joined voice channel '{after.channel.name}' alone. Will auto-disconnect in 60s.")

        # Handle auto-disconnect when bot is alone in a voice channel
        player = self.music_players.get(member.guild.id)
        if player and player.voice_client and player.voice_client.is_connected():
            bot_channel = player.voice_client.channel
            
            # Check if someone joined or left the bot's channel
            member_joined = (after.channel == bot_channel and before.channel != bot_channel)
            member_left = (before.channel == bot_channel and after.channel != bot_channel)
            
            if member_joined or member_left:
                # Add a tiny delay to let the discord.py cache catch up with the voice state update
                await asyncio.sleep(0.5)
                
                # Check current voice client and channel state again in case bot disconnected during sleep
                if not player.voice_client or not player.voice_client.is_connected() or player.voice_client.channel != bot_channel:
                    return
                    
                human_members = [m for m in bot_channel.members if not m.bot]
                if len(human_members) == 0:
                    player._start_auto_leave_timer(60, "alone")
                    logger.info(f"Bot is alone in voice channel '{bot_channel.name}'. Will auto-disconnect in 60 seconds.")
                else:
                    # Cancel disconnect timer if humans returned/are present
                    if player.disconnect_task and not player.disconnect_task.done():
                        player.disconnect_task.cancel()
                        player.disconnect_task = None
                        player.auto_leave_reason = None
                        logger.info(f"Cancelled auto-disconnect for voice channel '{bot_channel.name}' because members joined.")

    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type == discord.InteractionType.application_command:
            self.check_stats_reset()
            self.stats["commands_today"] = self.stats.get("commands_today", 0) + 1
            
        custom_id = interaction.data.get("custom_id") if interaction.data else None
        if not custom_id or not custom_id.startswith("role_toggle:"):
            return
            
        await interaction.response.defer(ephemeral=True)
        role_id_str = custom_id.split(":", 1)[1]
        try:
            role_id = int(role_id_str)
        except ValueError:
            await interaction.followup.send("❌ Invalid role configuration.", ephemeral=True)
            return
            
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("❌ Guild not found.", ephemeral=True)
            return
            
        role = guild.get_role(role_id)
        if not role:
            await interaction.followup.send("❌ Role not found on this server.", ephemeral=True)
            return
            
        member = guild.get_member(interaction.user.id)
        if not member:
            await interaction.followup.send("❌ Member not found.", ephemeral=True)
            return
            
        # Verify hierarchy compared to the bot's highest role
        bot_member = guild.get_member(self.user.id)
        if role >= bot_member.top_role:
            await interaction.followup.send(
                f"❌ I cannot manage the role **{role.name}** because it is positioned higher than my role (**{bot_member.top_role.name}**) in Discord's server settings. Please ask an Administrator to drag my bot's role above it.",
                ephemeral=True
            )
            return
            
        # Toggle role
        if role in member.roles:
            try:
                await member.remove_roles(role, reason="Self-assigned via Role Panel")
                await interaction.followup.send(f"✅ Removed the **{role.name}** role from you.", ephemeral=True)
                logger.info(f"Removed role '{role.name}' from {member.name}")
            except Exception as e:
                logger.error(f"Failed to remove role: {e}")
                await interaction.followup.send("❌ Failed to remove role. Check bot permissions.", ephemeral=True)
        else:
            try:
                await member.add_roles(role, reason="Self-assigned via Role Panel")
                await interaction.followup.send(f"✅ Added the **{role.name}** role to you.", ephemeral=True)
                logger.info(f"Assigned role '{role.name}' to {member.name}")
            except Exception as e:
                logger.error(f"Failed to add role: {e}")
                await interaction.followup.send("❌ Failed to add role. Check bot permissions.", ephemeral=True)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return

        # Process commands (Tier 3.4)
        await self.process_commands(message)

        self.check_stats_reset()
        self.stats["messages_today"] = self.stats.get("messages_today", 0) + 1

        # Use cached in-memory config instead of reading file (Tier 3.3)
        config = self.config
        
        # Check auto-responders first (supports advanced conditions and regex)
        auto_resp = config.get("auto_responders", [])
        g_id = str(message.guild.id)
        for resp in auto_resp:
            if not resp.get("enabled", True):
                continue
            if str(resp.get("guild_id")) != g_id:
                continue
                
            trigger_type = resp.get("trigger_type", "exact").lower()
            trigger = resp.get("trigger", "").strip()
            msg_content = message.content.strip()
            
            matched = False
            if trigger_type == "exact":
                matched = msg_content.lower() == trigger.lower()
            elif trigger_type == "contains":
                matched = trigger.lower() in msg_content.lower()
            elif trigger_type == "regex":
                if not utils.is_regex_safe(trigger):
                    logger.warning(f"Skipping potentially dangerous or invalid regex trigger: {trigger}")
                    continue
                try:
                    # Run regex search with a threadpool executor timeout to prevent ReDoS (Tier 2.5)
                    loop = asyncio.get_running_loop()
                    matched = await asyncio.wait_for(
                        loop.run_in_executor(
                            None,
                            lambda: bool(re.search(trigger, msg_content, re.IGNORECASE))
                        ),
                        timeout=1.0
                    )
                except Exception:
                    matched = False
                    
            if matched:
                # Check channel constraints
                allowed_channels = resp.get("channels", [])
                if allowed_channels and str(message.channel.id) not in allowed_channels:
                    continue
                    
                response_text = resp.get("response", "")
                if response_text:
                    response_text = response_text.replace("{user}", message.author.mention)
                    response_text = response_text.replace("{username}", message.author.name)
                    response_text = response_text.replace("{server}", message.guild.name)
                    response_text = response_text.replace("{channel}", message.channel.name)
                    response_text = response_text.replace("{membercount}", str(message.guild.member_count))
                    
                embed_data = resp.get("embed")
                try:
                    self.check_stats_reset()
                    self.stats["commands_today"] = self.stats.get("commands_today", 0) + 1
                    if embed_data:
                        embed_json_str = json.dumps(embed_data)
                        embed_json_str = embed_json_str.replace("{user}", message.author.mention).replace("{username}", message.author.name).replace("{server}", message.guild.name).replace("{channel}", message.channel.name).replace("{membercount}", str(message.guild.member_count))
                        embed_dict = json.loads(embed_json_str)
                        embed = discord.Embed.from_dict(embed_dict)
                        await message.channel.send(content=response_text or None, embed=embed)
                    else:
                        await message.channel.send(content=response_text)
                    logger.info(f"Auto-responder triggered by '{trigger}' in #{message.channel.name}")
                    return
                except Exception as e:
                    logger.error(f"Error executing auto-responder: {e}")

        # Check custom commands
        custom_cmds = utils.get_guild_custom_commands(config, message.guild.id)
        msg_clean = message.content.strip()
        custom_cmds_lower = {k.lower(): v for k, v in custom_cmds.items()}
        if msg_clean.lower() in custom_cmds_lower:
            try:
                self.stats["commands_today"] = self.stats.get("commands_today", 0) + 1
                await message.channel.send(custom_cmds_lower[msg_clean.lower()])
                logger.info(f"Executed custom command '{msg_clean}' in #{message.channel.name}")
                return
            except Exception as e:
                logger.error(f"Error sending custom command response: {e}")

        # Process Leveling XP reward
        leveling_cfg = utils.get_guild_leveling_settings(config, message.guild.id)
        if leveling_cfg.get("enabled", False):
            ignored_ch = leveling_cfg.get("ignored_channels", [])
            ignored_rl = leveling_cfg.get("ignored_roles", [])
            
            user_ignored = False
            if str(message.channel.id) in ignored_ch:
                user_ignored = True
            else:
                author_roles = getattr(message.author, "roles", [])
                for role in author_roles:
                    if str(role.id) in ignored_rl:
                        user_ignored = True
                        break
                        
            if not user_ignored:
                from aegis.bot.leveling import leveling_system
                xp_per_msg = int(leveling_cfg.get("xp_per_message", 15))
                cooldown = int(leveling_cfg.get("xp_cooldown_seconds", 60))
                
                new_lvl, leveled_up, cur_xp, tot_msg = leveling_system.add_xp(
                    message.guild.id, message.author.id, xp_per_msg, cooldown
                )
                
                if leveled_up:
                    announce_ch = message.channel
                    lvl_up_ch_id = leveling_cfg.get("level_up_channel")
                    if lvl_up_ch_id:
                        temp_ch = message.guild.get_channel(int(lvl_up_ch_id))
                        if temp_ch:
                            announce_ch = temp_ch
                            
                    try:
                        embed = discord.Embed(
                            title="🎉 LEVEL UP!",
                            description=f"{message.author.mention} has leveled up to **Level {new_lvl}**!",
                            color=discord.Color.gold()
                        )
                        embed.set_thumbnail(url=message.author.display_avatar.url)
                        await announce_ch.send(embed=embed)
                    except Exception as e:
                        logger.error(f"Failed to send level up announcement: {e}")
                        
                    lvl_roles = leveling_cfg.get("level_roles", {})
                    role_id_to_assign = lvl_roles.get(str(new_lvl))
                    if role_id_to_assign:
                        role = message.guild.get_role(int(role_id_to_assign))
                        if role:
                            try:
                                await message.author.add_roles(role, reason=f"Reached level {new_lvl}")
                                logger.info(f"Assigned level role '{role.name}' to {message.author.name}")
                            except Exception as e:
                                logger.error(f"Failed to assign level role '{role.name}': {e}")

        automod = utils.get_guild_automod_settings(config, message.guild.id)

        if not automod.get("enabled", False):
            return

        # Check if user is moderator/administrator or owner to bypass filters
        is_staff = False
        member = message.guild.get_member(message.author.id)
        if member:
            is_owner = member.id == message.guild.owner_id
            is_staff = is_owner or member.guild_permissions.manage_messages or member.guild_permissions.administrator

        if is_staff:
            return

        infractions = []

        # 1. Profanity check
        if automod.get("block_profanity", False):
            words = automod.get("profanity_words", [])
            content_lower = message.content.lower()
            for word in words:
                if word.lower() and re.search(r'\b' + re.escape(word.lower()) + r'\b', content_lower):
                    infractions.append(f"Contains blocked word: '{word}'")
                    break

        # 2. Invite check
        invites_found = DISCORD_INVITE_PATTERN.findall(message.content)
        if invites_found and automod.get("block_invites", False):
            whitelisted_invites = []
            for entry in automod.get("whitelisted_invites", []):
                match = DISCORD_INVITE_PATTERN.search(entry)
                whitelisted_invites.append(match.group(1).lower().strip() if match else entry.lower().strip())
            for invite_code in invites_found:
                if invite_code.lower().strip() not in whitelisted_invites:
                    infractions.append("Contains Discord invite link (unauthorized)")
                    break

        # 3. Link check
        if automod.get("block_links", False):
            url_matches = list(URL_DOMAIN_PATTERN.finditer(message.content))
            if url_matches:
                invite_matches = list(DISCORD_INVITE_PATTERN.finditer(message.content))
                whitelisted_domains = []
                for entry in automod.get("whitelisted_domains", []):
                    match = URL_DOMAIN_PATTERN.search(entry)
                    whitelisted_domains.append(match.group(1).lower().strip() if match else entry.lower().strip())
                for url_match in url_matches:
                    domain = url_match.group(1)
                    domain_lower = domain.lower().strip()
                    # Skip if this domain match is part of a discord invite link AND invite filtering is active
                    is_invite_part = False
                    for inv_match in invite_matches:
                        if inv_match.start() <= url_match.start() and url_match.end() <= inv_match.end():
                            if automod.get("block_invites", False):
                                is_invite_part = True
                            break
                    if is_invite_part:
                        continue
                    
                    is_whitelisted = False
                    for w_dom in whitelisted_domains:
                        if domain_lower == w_dom or domain_lower.endswith("." + w_dom):
                            is_whitelisted = True
                            break
                    if not is_whitelisted:
                        infractions.append("Contains links (unauthorized)")
                        break

        # 4. Mention spam check
        user_mentions_count = len(re.findall(r'<@!?\d+>', message.content))
        role_mentions_count = len(re.findall(r'<@&\d+>', message.content))
        everyone_here_count = message.content.count("@everyone") + message.content.count("@here")
        total_mentions = user_mentions_count + role_mentions_count + everyone_here_count
        
        max_mentions = automod.get("max_mentions", 5)
        if total_mentions > max_mentions:
            infractions.append(f"Mention spam ({total_mentions} mentions, max allowed {max_mentions})")

        if infractions:
            infraction_reason = "; ".join(infractions)
            try:
                # Delete message
                await message.delete()
                logger.info(f"Deleted message from {message.author.name} in #{message.channel.name}. Reason: {infraction_reason}")
                
                # Warn user in chat
                warn_msg = await message.channel.send(
                    f"⚠️ {message.author.mention}, your message was removed. Reason: {infraction_reason}"
                )
                
                # Delete warning after 5 seconds
                async def delete_warning(msg):
                    await asyncio.sleep(5)
                    try:
                        await msg.delete()
                    except discord.NotFound:
                        pass
                asyncio.create_task(delete_warning(warn_msg))

                # Log to Mod-Log
                await self.log_infraction(message.guild, message.author, infraction_reason, message.content, message.channel.name)
            except Exception as e:
                logger.error(f"Error handling auto-mod infraction: {e}")

    async def log_infraction(self, guild: discord.Guild, user: discord.Member, reason: str, original_content: str, channel_name: str = None):
        config = utils.load_config()
        automod = utils.get_guild_automod_settings(config, guild.id)
        log_channel = None

        # Find log channel by ID or name
        if automod.get("log_channel_id"):
            log_channel = guild.get_channel(int(automod["log_channel_id"]))
        
        if not log_channel:
            log_name = automod.get("log_channel_name") or "mod-logs"
            log_name_clean = log_name.lstrip("#").lower()
            if not log_name_clean:
                log_name_clean = "mod-logs"
            for ch in guild.text_channels:
                if ch.name.lower() == log_name_clean:
                    log_channel = ch
                    break

        if not log_channel:
            log_name = automod.get("log_channel_name") or "mod-logs"
            log_name_clean = log_name.lstrip("#").lower()
            if not log_name_clean:
                log_name_clean = "mod-logs"
            try:
                if guild.me.guild_permissions.manage_channels:
                    overwrites = {
                        guild.default_role: discord.PermissionOverwrite(view_channel=False)
                    }
                    admin_role = discord.utils.find(lambda r: r.name.lower() in ("admin", "server admin"), guild.roles)
                    mod_role = discord.utils.find(lambda r: r.name.lower() in ("moderator", "staff"), guild.roles)
                    if admin_role:
                        overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
                    if mod_role:
                        overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)
                        
                    log_channel = await guild.create_text_channel(
                        name=log_name_clean,
                        overwrites=overwrites,
                        reason="Auto-created default AutoMod infraction log channel"
                    )
                    logger.info(f"Auto-created default mod log channel #{log_name_clean}")
                    
                    guild_conf = utils.get_guild_config(str(guild.id))
                    guild_conf["automod_settings"]["log_channel_id"] = str(log_channel.id)
                    guild_conf["automod_settings"]["log_channel_name"] = log_channel.name
                    utils.save_guild_config(str(guild.id), guild_conf)
            except Exception as e:
                logger.error(f"Failed to auto-create default mod log channel: {e}")

        if log_channel:
            try:
                embed = discord.Embed(
                    title="🛡️ AutoMod Infraction Logged",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow()
                )
                embed.add_field(name="User", value=f"{user.mention} ({user.name} / ID: {user.id})", inline=False)
                embed.add_field(name="Reason", value=reason, inline=True)
                if channel_name:
                    embed.add_field(name="Channel", value=f"#{channel_name}", inline=True)
                embed.add_field(name="Message Content", value=original_content if len(original_content) <= 1024 else original_content[:1020] + "...", inline=False)
                
                await log_channel.send(embed=embed)
            except Exception as e:
                logger.error(f"Failed to send infraction log: {e}")


# Helper functions to call from API endpoints
from aegis.bot.restructuring import audit_guild_data, optimize_guild_structure, backup_guild_layout, restore_guild_layout


async def run_bot_safe(token):
    global bot_instance, bot_task
    try:
        await bot_instance.start(token)
    except Exception as e:
        logger.error(f"Discord Bot crashed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    finally:
        bot_instance = None
        bot_task = None
        logger.info("Bot background service ended.")

def parse_duration(duration_str: str) -> Optional[int]:
    match = re.match(r"^(\d+)([smhd])$", duration_str.lower().strip())
    if not match:
        return None
    val, unit = match.groups()
    val = int(val)
    if unit == "s":
        return val
    elif unit == "m":
        return val * 60
    elif unit == "h":
        return val * 3600
    elif unit == "d":
        return val * 86400
    return None


async def start_bot_service(token):
    """Starts the bot asynchronously in the background."""
    global bot_instance, bot_task
    if bot_instance is not None:
        logger.warning("Bot is already running.")
        return False
        
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    intents.voice_states = True
    
    bot_instance = DiscordOptimizerBot(command_prefix="!", intents=intents)
    
    from aegis.bot.commands import register_commands
    register_commands(bot_instance)
    
    bot_task = asyncio.create_task(run_bot_safe(token))
    logger.info("Bot starting background task...")
    return True

async def stop_bot_service():
    """Stops the bot service gracefully."""
    global bot_instance, bot_task
    if bot_instance is None:
        logger.warning("Bot is already stopped.")
        return False
        
    logger.info("Closing bot instance gracefully...")
    await bot_instance.close()
    
    # Wait for the task to finish
    if bot_task:
        try:
            await bot_task
        except asyncio.CancelledError:
            pass
            
    bot_instance = None
    bot_task = None
    logger.info("Bot stopped successfully.")
    return True

from aegis.bot.tickets import deploy_ticket_panel_message


async def deploy_role_panel_message(
    guild_id: int,
    channel_id: int,
    title: str,
    description: str,
    color_hex: str,
    buttons_data: list
):
    bot = get_bot()
    if not bot:
        return False
    guild = bot.get_guild(guild_id)
    if not guild:
        return False
    channel = guild.get_channel(channel_id)
    if not channel:
        return False
        
    try:
        color_val = int(color_hex.replace("#", ""), 16)
    except ValueError:
        color_val = 0x6366F1 # Indigo default
        
    embed = discord.Embed(
        title=title,
        description=description,
        color=discord.Color(color_val)
    )
    
    # Rebuild view
    view = discord.ui.View(timeout=None)
    
    styles_map = {
        "primary": discord.ButtonStyle.primary,
        "secondary": discord.ButtonStyle.secondary,
        "success": discord.ButtonStyle.success,
        "danger": discord.ButtonStyle.danger
    }
    
    for btn in buttons_data:
        try:
            role_id = int(btn["role_id"])
        except ValueError:
            continue
        # Validate role exists
        role = guild.get_role(role_id)
        if not role:
            continue
            
        style = styles_map.get(btn["style"].lower(), discord.ButtonStyle.primary)
        
        # Add button with custom_id starting with 'role_toggle:'
        view.add_item(discord.ui.Button(
            label=btn["label"],
            emoji=btn["emoji"] if btn.get("emoji") else None,
            style=style,
            custom_id=f"role_toggle:{role_id}"
        ))
        
    try:
        await channel.send(embed=embed, view=view)
        logger.info(f"Deployed role selection panel '{title}' in #{channel.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to deploy role panel: {e}")
        return False

def get_bot_stats():
    bot = get_bot()
    if not bot or not bot.is_ready():
        return {
            "status": "stopped",
            "messages_today": 0,
            "commands_today": 0,
            "tickets_today": 0,
            "joins_today": 0,
            "uptime": "N/A",
            "guilds_count": 0,
            "members_count": 0
        }
    
    # Calculate uptime
    import datetime
    uptime_str = "0m"
    if hasattr(bot, "stats") and bot.stats.get("uptime_start"):
        try:
            start_time = datetime.datetime.fromisoformat(bot.stats["uptime_start"])
            delta = datetime.datetime.now(datetime.timezone.utc) - start_time
            hours, remainder = divmod(int(delta.total_seconds()), 3600)
            minutes, _ = divmod(remainder, 60)
            if hours > 0:
                uptime_str = f"{hours}h {minutes}m"
            else:
                uptime_str = f"{minutes}m"
        except Exception:
            uptime_str = "N/A"
            
    return {
        "status": "running",
        "messages_today": bot.stats.get("messages_today", 0),
        "commands_today": bot.stats.get("commands_today", 0),
        "tickets_today": bot.stats.get("tickets_today", 0),
        "joins_today": bot.stats.get("joins_today", 0),
        "uptime": uptime_str,
        "guilds_count": len(bot.guilds),
        "members_count": sum(g.member_count or 0 for g in bot.guilds)
    }
