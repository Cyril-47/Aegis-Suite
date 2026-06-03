import asyncio
import logging
import discord
from discord.ext import commands
from discord import app_commands
import utils
import re
import math
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
    r'(?:https?://)?(?:www\.)?(?:discord\.(?:gg|io|me|li|club)|discord(?:app)?\.com/invite)/([a-zA-Z0-9-]{2,32})',
    re.IGNORECASE
)

URL_DOMAIN_PATTERN = re.compile(
    r'(?:https?://)?(?:www\.)?([a-zA-Z0-9][-a-zA-Z0-9]*[a-zA-Z0-9]\.[a-zA-Z]{2,24}(?:\.[a-zA-Z]{2,24})*)',
    re.IGNORECASE
)

def get_bot():
    return bot_instance

class TicketCloseView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Close Ticket", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="persistent_close_ticket_button")
    async def close_ticket(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        channel = interaction.channel
        await channel.send("🔒 *This ticket is being closed and deleted in 5 seconds...*")
        
        async def delete_channel():
            await asyncio.sleep(5)
            try:
                await channel.delete(reason="Ticket closed")
                logger.info(f"Ticket channel #{channel.name} deleted.")
            except Exception as e:
                logger.error(f"Failed to delete ticket channel: {e}")
        asyncio.create_task(delete_channel())

class TicketPanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Create Support Ticket", style=discord.ButtonStyle.primary, emoji="🎟️", custom_id="persistent_ticket_button")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        bot = get_bot()
        if bot:
            bot.check_stats_reset()
            bot.stats["tickets_today"] = bot.stats.get("tickets_today", 0) + 1
        guild = interaction.guild
        member = interaction.user
        
        config = utils.load_config()
        ticket_cfg = utils.get_guild_ticket_settings(config, guild.id)
        
        category_name = ticket_cfg.get("category_name", "🎟️ SUPPORT TICKETS")
        category = discord.utils.get(guild.categories, name=category_name)
        
        staff_role_name = ticket_cfg.get("staff_role_name", "Moderator")
        staff_role = discord.utils.get(guild.roles, name=staff_role_name)
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
        }
        if staff_role:
            overwrites[staff_role] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
        
        if not category:
            try:
                category = await guild.create_category(name=category_name, overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)})
                logger.info(f"Created ticket category '{category_name}'")
            except Exception as e:
                logger.error(f"Failed to create ticket category: {e}")
        
        try:
            channel_name = f"ticket-{member.name.lower()}"
            channel_name = re.sub(r'[^a-zA-Z0-9-]', '', channel_name)
            
            # Check for existing ticket channel to prevent duplicates (Tier 3.7)
            existing = discord.utils.get(guild.text_channels, name=channel_name, category=category)
            if existing:
                await interaction.followup.send(f"❌ You already have an open ticket: {existing.mention}", ephemeral=True)
                return
                
            ticket_channel = await guild.create_text_channel(
                name=channel_name[:100],
                category=category,
                overwrites=overwrites,
                reason=f"Support ticket opened by {member.name}"
            )
            
            embed = discord.Embed(
                title="🎟️ Support Ticket Created",
                description=f"Welcome {member.mention} to your private support channel.\n\n"
                            f"Please describe your issue in detail. A staff member ({staff_role.mention if staff_role else 'Moderator'}) will be with you shortly.\n\n"
                            f"Click the button below to **Close** this ticket.",
                color=discord.Color.blue()
            )
            await ticket_channel.send(content=f"{member.mention} | Support Staff", embed=embed, view=TicketCloseView())
            await interaction.followup.send(f"✅ Ticket created! Head over to {ticket_channel.mention} to speak with staff.", ephemeral=True)
            logger.info(f"Ticket channel #{channel_name} created for {member.name}")
        except Exception as e:
            logger.error(f"Failed to create support ticket channel: {e}")
            await interaction.followup.send("❌ Failed to create support ticket. Please check bot permissions.", ephemeral=True)

class GiveawayJoinView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎉 Join Giveaway (0)", style=discord.ButtonStyle.blurple, custom_id="giveaway_join_btn")
    async def join_giveaway(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = str(interaction.message.id)
        
        # Acquire lock to prevent entrant race condition (Tier 1.5)
        async with utils.giveaways_lock:
            giveaways = await utils.load_giveaways()
            
            if msg_id not in giveaways:
                button.disabled = True
                button.label = "🎉 Join Giveaway"
                await interaction.message.edit(view=self)
                await interaction.response.send_message("This giveaway is no longer active.", ephemeral=True)
                return
                
            giveaway = giveaways[msg_id]
            if giveaway.get("ended", False):
                button.disabled = True
                await interaction.message.edit(view=self)
                await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)
                return
                
            user_id = interaction.user.id
            entrants = giveaway.get("entrants", [])
            
            if user_id in entrants:
                entrants.remove(user_id)
                joined = False
                msg = "❌ You have left the giveaway."
            else:
                entrants.append(user_id)
                joined = True
                msg = "✅ You have successfully entered the giveaway!"
                
            giveaway["entrants"] = entrants
            giveaways[msg_id] = giveaway
            await utils.save_giveaways(giveaways)
        
        # Update button label count
        button.label = f"🎉 Join Giveaway ({len(entrants)})"
        
        # Update the original embed
        embeds = interaction.message.embeds
        if embeds:
            embed = embeds[0]
            entrants_field_idx = -1
            for idx, field in enumerate(embed.fields):
                if "Participants" in field.name or "Entrants" in field.name:
                    entrants_field_idx = idx
                    break
            
            new_embed = discord.Embed.from_dict(embed.to_dict())
            if entrants_field_idx != -1:
                new_embed.set_field_at(
                    entrants_field_idx,
                    name=f"👥 Participants ({len(entrants)})",
                    value=f"Click the button below to join!\nTotal: **{len(entrants)}** entrant(s)",
                    inline=True
                )
            else:
                new_embed.set_footer(text=f"Total Entrants: {len(entrants)}")
                
            await interaction.message.edit(embed=new_embed, view=self)
        else:
            await interaction.message.edit(view=self)
            
        await interaction.response.send_message(msg, ephemeral=True)


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
        
        # Start scheduled messages background scheduler
        self.scheduler_task = self.loop.create_task(self.scheduler_loop())
        self.giveaway_task = self.loop.create_task(self.giveaway_scheduler_loop())
        
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
                    
                    next_run_str = msg.get("next_run")
                    if not next_run_str:
                        continue
                        
                    next_run = datetime.datetime.fromisoformat(next_run_str)
                    if next_run.tzinfo is None:
                        next_run = next_run.replace(tzinfo=datetime.timezone.utc)
                    if now >= next_run:
                        # Message is due! Send it.
                        guild_id = int(msg["guild_id"])
                        channel_id = int(msg["channel_id"])
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
                        
                if config_changed:
                    utils.save_config(config)
                    self.config = config
                    
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
            
            view = discord.ui.View()
            btn = discord.ui.Button(label=f"Giveaway Ended ({len(entrants)})", style=discord.ButtonStyle.secondary, disabled=True, custom_id="giveaway_ended_btn")
            view.add_item(btn)
            
            await message.edit(embed=new_embed, view=view)
            
            if winners:
                await message.channel.send(
                    f"🎉 Congratulations to {winners_mentions}! You won **{prize}**! 🎁\n"
                    f"Original message: {message.jump_url}"
                )
            else:
                await message.channel.send(
                    f"😭 The giveaway for **{prize}** ended, but there were no participants.\n"
                    f"Original message: {message.jump_url}"
                )

    async def on_command_error(self, ctx: commands.Context, error: Exception):
        # Unwrap CommandInvokeError to get the original exception
        if isinstance(error, commands.CommandInvokeError):
            error = error.original

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
        if member.id == self.user.id and after.channel is None:
            player = self.music_players.pop(member.guild.id, None)
            if player and player.disconnect_task and not player.disconnect_task.done():
                player.disconnect_task.cancel()
            return

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
                    # Start auto-disconnect timer if not already active (Tier 1.6)
                    if not player.disconnect_task or player.disconnect_task.done():
                        async def auto_disconnect(pl, ch):
                            await asyncio.sleep(300)
                            if pl.voice_client and pl.voice_client.channel == ch:
                                humans = [m for m in ch.members if not m.bot]
                                if len(humans) == 0:
                                    await pl.leave_channel()
                                    logger.info(f"Auto-disconnected from voice channel '{ch.name}' due to inactivity.")
                        
                        player.disconnect_task = asyncio.create_task(auto_disconnect(player, bot_channel))
                        logger.info(f"Bot is alone in voice channel '{bot_channel.name}'. Will auto-disconnect in 5 minutes.")
                else:
                    # Cancel disconnect timer if humans returned/are present
                    if player.disconnect_task and not player.disconnect_task.done():
                        player.disconnect_task.cancel()
                        player.disconnect_task = None
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
        if msg_clean in custom_cmds:
            try:
                self.stats["commands_today"] = self.stats.get("commands_today", 0) + 1
                await message.channel.send(custom_cmds[msg_clean])
                logger.info(f"Executed custom command '{msg_clean}' in #{message.channel.name}")
                return
            except Exception as e:
                logger.error(f"Error sending custom command response: {e}")

        # Process Leveling XP reward
        leveling_cfg = config.get("leveling_settings", {})
        if leveling_cfg.get("enabled", False):
            ignored_ch = leveling_cfg.get("ignored_channels", [])
            ignored_rl = leveling_cfg.get("ignored_roles", [])
            
            user_ignored = False
            if str(message.channel.id) in ignored_ch:
                user_ignored = True
            else:
                for role in message.author.roles:
                    if str(role.id) in ignored_rl:
                        user_ignored = True
                        break
                        
            if not user_ignored:
                from leveling import leveling_system
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
            whitelisted_invites = [i.lower().strip() for i in automod.get("whitelisted_invites", [])]
            for invite_code in invites_found:
                if invite_code.lower().strip() not in whitelisted_invites:
                    infractions.append("Contains Discord invite link (unauthorized)")
                    break

        # 3. Link check
        if automod.get("block_links", False):
            url_matches = list(URL_DOMAIN_PATTERN.finditer(message.content))
            if url_matches:
                invite_matches = list(DISCORD_INVITE_PATTERN.finditer(message.content))
                whitelisted_domains = [d.lower().strip() for d in automod.get("whitelisted_domains", [])]
                for url_match in url_matches:
                    domain = url_match.group(1)
                    domain_lower = domain.lower().strip()
                    # Skip if this domain match is part of a discord invite link
                    is_invite_part = False
                    for inv_match in invite_matches:
                        if inv_match.start() <= url_match.start() and url_match.end() <= inv_match.end():
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
            log_name = automod.get("log_channel_name", "mod-logs").lstrip("#").lower()
            for ch in guild.text_channels:
                if ch.name.lower() == log_name:
                    log_channel = ch
                    break

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
def audit_guild_data(guild: discord.Guild):
    """Scans guild settings, roles, channels and computes a health/optimization score."""
    config = utils.load_config()
    
    score = 100
    checklist = []
    
    # 1. Verification level
    v_level = str(guild.verification_level)
    if guild.verification_level == discord.VerificationLevel.none:
        score -= 15
        checklist.append({
            "name": "Verification Level",
            "status": "FAIL",
            "message": "No verification level set. Anyone can join and type immediately, leaving the server vulnerable to raid bots.",
            "value": v_level
        })
    elif guild.verification_level in (discord.VerificationLevel.low, discord.VerificationLevel.medium):
        score -= 5
        checklist.append({
            "name": "Verification Level",
            "status": "WARNING",
            "message": "Low/Medium verification. Recommended to set to High (must have verified phone/email or be member for 10m).",
            "value": v_level
        })
    else:
        checklist.append({
            "name": "Verification Level",
            "status": "SUCCESS",
            "message": "Verification level is secure.",
            "value": v_level
        })

    # 2. Explicit Content Filter
    f_level = str(guild.explicit_content_filter)
    if guild.explicit_content_filter == discord.ContentFilter.disabled:
        score -= 15
        checklist.append({
            "name": "Explicit Content Filter",
            "status": "FAIL",
            "message": "Content filter is disabled. Highly recommended to scan messages from all members to block explicit content.",
            "value": f_level
        })
    elif guild.explicit_content_filter == discord.ContentFilter.all_members:
        checklist.append({
            "name": "Explicit Content Filter",
            "status": "SUCCESS",
            "message": "Explicit content filter scans all messages.",
            "value": f_level
        })
    else:
        score -= 5
        checklist.append({
            "name": "Explicit Content Filter",
            "status": "WARNING",
            "message": "Content filter only scans users without roles. Recommended to scan all members.",
            "value": f_level
        })

    # 3. Log channel check
    log_cfg = utils.get_guild_automod_settings(config, guild.id)
    has_log_channel = False
    log_ch_name = ""
    if log_cfg.get("log_channel_id"):
        ch = guild.get_channel(int(log_cfg["log_channel_id"]))
        if ch:
            has_log_channel = True
            log_ch_name = ch.name
    
    if not has_log_channel:
        # Search by name
        log_name = log_cfg.get("log_channel_name", "mod-logs").lstrip("#").lower()
        for ch in guild.text_channels:
            if ch.name.lower() == log_name:
                has_log_channel = True
                log_ch_name = ch.name
                break

    if not has_log_channel:
        score -= 15
        checklist.append({
            "name": "Moderation Logs Channel",
            "status": "FAIL",
            "message": "No dedicated moderation logs channel found. Staff actions & infractions will not be recorded.",
            "value": "Missing"
        })
    else:
        checklist.append({
            "name": "Moderation Logs Channel",
            "status": "SUCCESS",
            "message": f"Mod logs will be sent to #{log_ch_name}.",
            "value": f"#{log_ch_name}"
        })

    # 4. Welcome channel check
    welcome_cfg = utils.get_guild_welcome_settings(config, guild.id)
    has_welcome_channel = False
    welcome_ch_name = ""
    if welcome_cfg.get("channel_id"):
        ch = guild.get_channel(int(welcome_cfg["channel_id"]))
        if ch:
            has_welcome_channel = True
            welcome_ch_name = ch.name
            
    if not has_welcome_channel:
        welcome_name = welcome_cfg.get("channel_name", "welcome").lower()
        for ch in guild.text_channels:
            if ch.name.lower() == welcome_name:
                has_welcome_channel = True
                welcome_ch_name = ch.name
                break

    if not has_welcome_channel:
        score -= 10
        checklist.append({
            "name": "Welcome Channel",
            "status": "FAIL",
            "message": "No welcome channel detected. New members will not receive greeting guides.",
            "value": "Missing"
        })
    else:
        checklist.append({
            "name": "Welcome Channel",
            "status": "SUCCESS",
            "message": f"Welcome messages will be posted in #{welcome_ch_name}.",
            "value": f"#{welcome_ch_name}"
        })

    # 5. Check @everyone permissions
    everyone_role = guild.default_role
    danger_perms = []
    if everyone_role.permissions.administrator:
        danger_perms.append("Administrator")
    if everyone_role.permissions.manage_guild:
        danger_perms.append("Manage Server")
    if everyone_role.permissions.manage_channels:
        danger_perms.append("Manage Channels")
    if everyone_role.permissions.manage_roles:
        danger_perms.append("Manage Roles")
    if everyone_role.permissions.mention_everyone:
        danger_perms.append("Mention @everyone")

    if danger_perms:
        score -= 25
        checklist.append({
            "name": "@everyone Insecure Permissions",
            "status": "FAIL",
            "message": f"Standard users (@everyone) have powerful permissions: {', '.join(danger_perms)}. This is a severe safety risk!",
            "value": "Vulnerable"
        })
    else:
        checklist.append({
            "name": "@everyone Permissions",
            "status": "SUCCESS",
            "message": "@everyone permissions are safe and restricted.",
            "value": "Secure"
        })

    # 6. Insecure Roles / Admin Bloat
    admin_bloat = False
    insecure_roles = []
    for role in guild.roles:
        if role.is_default():
            continue
        # Check if role has admin/moderation permissions and is assigned to a large portion of users
        if role.permissions.administrator:
            member_percentage = (len(role.members) / max(1, guild.member_count)) * 100
            if member_percentage > 20 and guild.member_count > 5:
                admin_bloat = True
                insecure_roles.append(f"{role.name} ({member_percentage:.1f}% of users have Admin)")

    if admin_bloat:
        score -= 10
        checklist.append({
            "name": "Administrator Overload",
            "status": "WARNING",
            "message": f"Too many users have Administrator access via these roles: {', '.join(insecure_roles)}.",
            "value": "Over-privileged"
        })
    else:
        checklist.append({
            "name": "Administrator Overload",
            "status": "SUCCESS",
            "message": "Admin privileges are limited to a small, secure subset of users.",
            "value": "Healthy"
        })

    # 7. Bot Commands Channel Check
    has_bot_cmd = False
    for ch in guild.text_channels:
        if "bot" in ch.name.lower() and ("command" in ch.name.lower() or "cmd" in ch.name.lower() or "play" in ch.name.lower()):
            has_bot_cmd = True
            break
            
    if not has_bot_cmd:
        score -= 5
        checklist.append({
            "name": "Bot Commands Channel",
            "status": "WARNING",
            "message": "No channel dedicated to bot commands found. Members might clutter general chat with bot commands.",
            "value": "Missing"
        })
    else:
        checklist.append({
            "name": "Bot Commands Channel",
            "status": "SUCCESS",
            "message": "A bot commands channel is available to contain bot spam.",
            "value": "Available"
        })

    # 8. AutoMod Bot Activation
    if not utils.get_guild_automod_settings(config, guild.id).get("enabled", False):
        score -= 10
        checklist.append({
            "name": "AutoMod Configuration",
            "status": "WARNING",
            "message": "Auto-moderation is disabled in the bot dashboard settings.",
            "value": "Disabled"
        })
    else:
        checklist.append({
            "name": "AutoMod Configuration",
            "status": "SUCCESS",
            "message": "Auto-moderation filters are active.",
            "value": "Enabled"
        })

    score = max(0, score)

    # Compile server statistics
    text_count = len(guild.text_channels)
    voice_count = len(guild.voice_channels)
    category_count = len(guild.categories)
    role_count = len(guild.roles)
    
    # Calculate online members (requires chunking/intents, if not fully cached it represents users in cache)
    online_count = sum(1 for m in guild.members if m.status != discord.Status.offline)
    
    return {
        "score": score,
        "checklist": checklist,
        "guild_info": {
            "name": guild.name,
            "id": str(guild.id),
            "member_count": guild.member_count,
            "online_count": online_count if online_count > 0 else 1, # Fallback
            "owner": str(guild.owner),
            "owner_id": str(guild.owner_id) if guild.owner_id else "Unknown",
            "icon_url": str(guild.icon.url) if guild.icon else None,
            "boost_tier": guild.premium_tier,
            "boost_count": guild.premium_subscription_count,
            "verification_level": str(guild.verification_level),
            "explicit_filter": str(guild.explicit_content_filter),
            "text_channels": text_count,
            "voice_channels": voice_count,
            "categories": category_count,
            "roles": role_count
        }
    }

async def optimize_guild_structure(guild: discord.Guild, preset: str, handling: str):
    """Executes preset layouts, configures roles, sets permissions."""
    logger.info(f"Starting server optimization for '{guild.name}' using preset '{preset}' (handling: {handling})...")
    
    # 1. Create Roles
    # Default roles to create
    roles_to_create = {
        "Server Admin": {"permissions": discord.Permissions(administrator=True), "color": discord.Color.teal()},
        "Moderator": {"permissions": discord.Permissions(
            kick_members=True,
            ban_members=True,
            manage_messages=True,
            manage_nicknames=True,
            mute_members=True,
            deafen_members=True,
            move_members=True,
            read_message_history=True,
            view_audit_log=True,
            view_channel=True,
            send_messages=True
        ), "color": discord.Color.blue()},
        "Verified Member": {"permissions": discord.Permissions(
            send_messages=True,
            read_message_history=True,
            view_channel=True,
            connect=True,
            speak=True
        ), "color": discord.Color.green()}
    }

    created_roles = {}
    for role_name, data in roles_to_create.items():
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try:
                role = await guild.create_role(
                    name=role_name,
                    permissions=data["permissions"],
                    color=data["color"],
                    hoist=True,
                    reason="Server Optimizer Setup"
                )
                logger.info(f"Created role '{role_name}'")
            except Exception as e:
                logger.error(f"Failed to create role '{role_name}': {e}")
        created_roles[role_name] = role

    # Set up restriction for @everyone
    try:
        everyone_role = guild.default_role
        everyone_perms = everyone_role.permissions
        everyone_perms.update(
            administrator=False,
            manage_guild=False,
            manage_channels=False,
            manage_roles=False,
            mention_everyone=False
        )
        await everyone_role.edit(permissions=everyone_perms, reason="Secure default permissions")
        logger.info("Restricted dangerous @everyone default permissions.")
    except Exception as e:
        logger.error(f"Failed to edit @everyone role: {e}")

    # 2. Handle existing channels
    if handling == "archive":
        logger.info("Archiving existing channels...")
        archive_category = discord.utils.get(guild.categories, name="📦 ARCHIVED CHANNELS")
        if not archive_category:
            try:
                # Private category only for staff/admin
                admin_role = created_roles.get("Server Admin")
                mod_role = created_roles.get("Moderator")
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                }
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
                if mod_role:
                    overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)
                    
                archive_category = await guild.create_category(
                    name="📦 ARCHIVED CHANNELS",
                    overwrites=overwrites,
                    reason="Archive existing layout"
                )
                logger.info("Created '📦 ARCHIVED CHANNELS' category.")
            except Exception as e:
                logger.error(f"Failed to create archive category: {e}")

        if archive_category:
            for channel in list(guild.channels):
                if channel.category == archive_category or channel == archive_category:
                    continue
                try:
                    await channel.edit(category=archive_category, reason="Archiving old structure")
                    logger.info(f"Archived channel #{channel.name}")
                except Exception as e:
                    logger.warning(f"Could not archive channel #{channel.name}: {e}")

    elif handling == "delete":
        logger.info("Deleting existing categories and channels...")
        for channel in list(guild.channels):
            try:
                await channel.delete(reason="Server Optimizer layout clean")
                logger.info(f"Deleted channel/category: {channel.name}")
            except Exception as e:
                logger.warning(f"Could not delete channel {channel.name}: {e}")

    # 3. Create Preset layout
    # Layout definitions
    presets = {
        "gaming": [
            {
                "category": "🏆 INFORMATION",
                "channels": [
                    {"name": "welcome", "type": "text", "readonly": True},
                    {"name": "rules-and-info", "type": "text", "readonly": True},
                    {"name": "announcements", "type": "text", "readonly": True}
                ]
            },
            {
                "category": "💬 TEXT CHANNELS",
                "channels": [
                    {"name": "general", "type": "text", "readonly": False},
                    {"name": "gaming-lobby", "type": "text", "readonly": False},
                    {"name": "clips-and-highlights", "type": "text", "readonly": False},
                    {"name": "memes", "type": "text", "readonly": False},
                    {"name": "bot-commands", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "General Voice", "type": "voice"},
                    {"name": "Squad Room 1", "type": "voice"},
                    {"name": "Squad Room 2", "type": "voice"},
                    {"name": "Chill Lounge", "type": "voice"}
                ]
            },
            {
                "category": "🛡️ STAFF ONLY",
                "channels": [
                    {"name": "staff-chat", "type": "text", "staff_only": True},
                    {"name": "mod-logs", "type": "text", "staff_only": True}
                ]
            }
        ],
        "community": [
            {
                "category": "📢 WELCOME & INFO",
                "channels": [
                    {"name": "welcome", "type": "text", "readonly": True},
                    {"name": "rules-and-roles", "type": "text", "readonly": True},
                    {"name": "announcements", "type": "text", "readonly": True}
                ]
            },
            {
                "category": "💬 DISCUSSION",
                "channels": [
                    {"name": "general-chat", "type": "text", "readonly": False},
                    {"name": "introductions", "type": "text", "readonly": False},
                    {"name": "bot-commands", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🎭 INTERESTS",
                "channels": [
                    {"name": "hobbies", "type": "text", "readonly": False},
                    {"name": "media-and-art", "type": "text", "readonly": False},
                    {"name": "memes", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🔊 VOICE CHANNELS",
                "channels": [
                    {"name": "General Lounge", "type": "voice"},
                    {"name": "Gaming", "type": "voice"},
                    {"name": "Music Room", "type": "voice"}
                ]
            },
            {
                "category": "🛡️ MODERATION",
                "channels": [
                    {"name": "mod-chat", "type": "text", "staff_only": True},
                    {"name": "mod-logs", "type": "text", "staff_only": True}
                ]
            }
        ],
        "developer": [
            {
                "category": "📚 INFO & RULES",
                "channels": [
                    {"name": "welcome", "type": "text", "readonly": True},
                    {"name": "rules-and-resources", "type": "text", "readonly": True},
                    {"name": "announcements", "type": "text", "readonly": True}
                ]
            },
            {
                "category": "💬 TECH DISCUSSION",
                "channels": [
                    {"name": "general-dev", "type": "text", "readonly": False},
                    {"name": "questions-and-help", "type": "text", "readonly": False},
                    {"name": "resources", "type": "text", "readonly": False},
                    {"name": "bot-commands", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "💻 PROJECT HUB",
                "channels": [
                    {"name": "showcase", "type": "text", "readonly": False},
                    {"name": "ideas-and-feedback", "type": "text", "readonly": False},
                    {"name": "github-feed", "type": "text", "readonly": False}
                ]
            },
            {
                "category": "🔊 COLLABORATION",
                "channels": [
                    {"name": "Dev Desk 1", "type": "voice"},
                    {"name": "Dev Desk 2", "type": "voice"},
                    {"name": "Standup Room", "type": "voice"}
                ]
            },
            {
                "category": "🛡️ STAFF ONLY",
                "channels": [
                    {"name": "staff-chat", "type": "text", "staff_only": True},
                    {"name": "mod-logs", "type": "text", "staff_only": True}
                ]
            }
        ]
    }

    selected_preset = presets.get(preset.lower(), presets["community"])
    welcome_channel_created = None
    log_channel_created = None

    admin_role = created_roles.get("Server Admin")
    mod_role = created_roles.get("Moderator")

    for cat_data in selected_preset:
        cat_name = cat_data["category"]
        
        # Determine category overwrites
        cat_overwrites = {}
        if cat_name.startswith("🛡️"):
            # Private Staff category
            cat_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
            if admin_role:
                cat_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
            if mod_role:
                cat_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)

        try:
            category = await guild.create_category(
                name=cat_name,
                overwrites=cat_overwrites,
                reason="Optimization Preset Category Setup"
            )
            logger.info(f"Created category '{cat_name}'")
        except Exception as e:
            logger.error(f"Failed to create category '{cat_name}': {e}")
            continue

        for chan_data in cat_data["channels"]:
            chan_name = chan_data["name"]
            chan_type = chan_data["type"]
            
            chan_overwrites = {}
            if chan_data.get("readonly", False):
                # Read-only for normal users, writable by admins/mods
                chan_overwrites[guild.default_role] = discord.PermissionOverwrite(send_messages=False, add_reactions=True)
                if admin_role:
                    chan_overwrites[admin_role] = discord.PermissionOverwrite(send_messages=True)
                if mod_role:
                    chan_overwrites[mod_role] = discord.PermissionOverwrite(send_messages=True)
            elif chan_data.get("staff_only", False):
                # Private channel
                chan_overwrites[guild.default_role] = discord.PermissionOverwrite(view_channel=False)
                if admin_role:
                    chan_overwrites[admin_role] = discord.PermissionOverwrite(view_channel=True)
                if mod_role:
                    chan_overwrites[mod_role] = discord.PermissionOverwrite(view_channel=True)

            try:
                if chan_type == "text":
                    channel = await guild.create_text_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overwrites,
                        reason="Optimization Preset Channel Setup"
                    )
                    logger.info(f"Created text channel #{chan_name} inside '{cat_name}'")
                    
                    if chan_name == "welcome":
                        welcome_channel_created = channel
                    elif chan_name == "mod-logs":
                        log_channel_created = channel
                else:
                    channel = await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overwrites,
                        reason="Optimization Preset Channel Setup"
                    )
                    logger.info(f"Created voice channel '{chan_name}' inside '{cat_name}'")
            except Exception as e:
                logger.error(f"Failed to create channel '{chan_name}': {e}")

    # 4. Update configuration settings for welcome & logging to point to the new channels (Tier 5.7)
    guild_conf = utils.get_guild_config(str(guild.id))
    if welcome_channel_created:
        guild_conf["welcome_settings"]["channel_id"] = str(welcome_channel_created.id)
        guild_conf["welcome_settings"]["channel_name"] = welcome_channel_created.name
    if log_channel_created:
        guild_conf["automod_settings"]["log_channel_id"] = str(log_channel_created.id)
        guild_conf["automod_settings"]["log_channel_name"] = log_channel_created.name
    utils.save_guild_config(str(guild.id), guild_conf)

    logger.info(f"Server optimization complete for guild '{guild.name}'. preset={preset}")
    return True


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

async def start_giveaway_bot(channel, prize, winners_count, duration_seconds, host_id):
    import time
    end_time = time.time() + duration_seconds
    
    embed = discord.Embed(
        title="🎁 GIVEAWAY START 🎁",
        description="Click the button below to join the giveaway!",
        color=discord.Color.from_str("#6366F1")
    )
    embed.add_field(name="🎁 Prize", value=prize, inline=True)
    embed.add_field(name="🏆 Winners", value=str(winners_count), inline=True)
    embed.add_field(name="⏳ Ends", value=f"<t:{int(end_time)}:R> (<t:{int(end_time)}:f>)", inline=False)
    embed.add_field(name="👥 Participants (0)", value="Click the button below to join!\nTotal: **0** entrant(s)", inline=True)
    embed.set_footer(text=f"Hosted by Aegis Suite")
    
    view = GiveawayJoinView()
    message = await channel.send(embed=embed, view=view)
    
    async with utils.giveaways_lock:
        giveaways = await utils.load_giveaways()
        giveaways[str(message.id)] = {
            "guild_id": str(channel.guild.id),
            "channel_id": str(channel.id),
            "prize": prize,
            "winners_count": winners_count,
            "end_time": end_time,
            "entrants": [],
            "winners": [],
            "ended": False,
            "host_id": str(host_id)
        }
        await utils.save_giveaways(giveaways)
        
    return str(message.id)

async def reroll_giveaway_bot(channel, message_id):
    msg_id_str = str(message_id)
    
    async with utils.giveaways_lock:
        giveaways = await utils.load_giveaways()
        if msg_id_str not in giveaways:
            return "Giveaway not found in record."
            
        gw = giveaways[msg_id_str]
        if not gw.get("ended", False):
            return "Giveaway is still active. End it first before rerolling."
            
        entrants = gw.get("entrants", [])
        if not entrants:
            return "No entrants to roll from."
            
        winners_count = gw.get("winners_count", 1)
        prize = gw.get("prize", "Unknown Prize")
        
        import random
        actual_winners_count = min(len(entrants), winners_count)
        winners = random.sample(entrants, actual_winners_count)
        
        gw["winners"] = winners
        giveaways[msg_id_str] = gw
        await utils.save_giveaways(giveaways)
        
    try:
        message = await channel.fetch_message(message_id)
        embeds = message.embeds
        if embeds:
            embed = embeds[0]
            new_embed = discord.Embed.from_dict(embed.to_dict())
            new_embed.clear_fields()
            new_embed.add_field(name="🎁 Prize", value=prize, inline=True)
            
            winners_mentions = ", ".join([f"<@{w}>" for w in winners])
            new_embed.add_field(name="🏆 Rerolled Winners", value=winners_mentions, inline=True)
            new_embed.add_field(name="👥 Total Participants", value=f"**{len(entrants)}** entrant(s)", inline=True)
            
            await message.edit(embed=new_embed)
            
        winners_mentions = ", ".join([f"<@{w}>" for w in winners])
        await channel.send(
            f"🔄 **Giveaway Rerolled!**\n"
            f"Congratulations to the new winner(s): {winners_mentions}! You won **{prize}**! 🎁"
        )
        return "success"
    except Exception as e:
        logger.error(f"Failed to edit message during reroll: {e}")
        return f"Failed to edit Discord message: {e}"


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
    
    bot_instance = DiscordOptimizerBot(command_prefix="!", intents=intents)
    
    # Register connection linking command (Tier 5.2)
    @bot_instance.hybrid_command(name="linkdashboard", description="Generates a temporary linking code for the web dashboard.")
    @app_commands.default_permissions(administrator=True)
    async def slash_linkdashboard(ctx: commands.Context):
        if not ctx.guild:
            await ctx.send("This command can only be used inside a Discord server.", ephemeral=True)
            return
            
        # Enforce rate limit of 1 code per guild per 5 minutes (Tier 6.3)
        if not utils.can_generate_code(ctx.guild.id):
            await ctx.send("❌ A connection code was already generated for this server recently. Please use that code or wait 5 minutes before generating a new one.", ephemeral=True)
            return
            
        await ctx.defer(ephemeral=True)
        
        import random
        import string
        import time
        
        # Generate 6 character alphanumeric code
        code = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        with utils.config_lock:
            config = utils.load_config()
            pending = config.setdefault("pending_pairings", {})
            pending[code] = {
                "guild_id": str(ctx.guild.id),
                "guild_name": ctx.guild.name,
                "expires_at": time.time() + 600,
                "attempts": 0  # Initial attempts (Tier 6.4)
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

    @bot_instance.hybrid_command(name="unlink", description="Revokes the web dashboard link for this server.")
    @app_commands.describe(purge="Whether to completely wipe this server's dashboard configurations from the bot.")
    @app_commands.default_permissions(administrator=True)
    async def slash_unlink(ctx: commands.Context, purge: bool = False):
        if not ctx.guild:
            await ctx.send("This command can only be used inside a Discord server.", ephemeral=True)
            return
            
        guild_id = str(ctx.guild.id)
        
        # 1. Revoke the active dashboard sessions for this guild
        auth.revoke_guild_sessions(guild_id)
        
        details = "Sessions revoked."
        # 2. Optionally purge layout and config settings
        if purge:
            with utils.config_lock:
                config = utils.load_config()
                # Idempotent deletion of guild configuration
                guild_configs = config.get("guild_configs", {})
                guild_configs.pop(guild_id, None)
                
                # Clean up scheduled messages
                sched = config.get("scheduled_messages", [])
                config["scheduled_messages"] = [m for m in sched if m.get("guild_id") != guild_id]
                
                # Clean up auto responders
                responders = config.get("auto_responders", [])
                config["auto_responders"] = [r for r in responders if r.get("guild_id") != guild_id]
                
                utils.save_config(config)
            
            # Idempotent deletion of giveaways
            import utils as bot_utils
            giveaways = await bot_utils.load_giveaways()
            to_delete = [msg_id for msg_id, gw in giveaways.items() if gw.get("guild_id") == guild_id]
            for msg_id in to_delete:
                giveaways.pop(msg_id, None)
            await bot_utils.save_giveaways(giveaways)
            
            details += " Guild configuration, custom commands, scheduled messages, auto-responders, and giveaways purged."
            
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

    # Register basic chat help commands
    @bot_instance.hybrid_command(name="audit", description="Scans and audits the server structure and permissions.")
    @app_commands.default_permissions(administrator=True)
    async def slash_audit(ctx: commands.Context):
        await ctx.defer(ephemeral=True)
        try:
            audit_report = audit_guild_data(ctx.guild)
            score = audit_report["score"]
            
            embed = discord.Embed(
                title=f"🛡️ Server Audit Report for {ctx.guild.name}",
                description=f"**Optimization Score: {score}/100**",
                color=discord.Color.green() if score >= 80 else discord.Color.orange() if score >= 50 else discord.Color.red()
            )
            
            for item in audit_report["checklist"][:5]: # Send top 5 checks
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

    @bot_instance.hybrid_command(name="optimize_server", description="Optimizes the server. Warning: will reorganize channels.")
    @app_commands.describe(preset="Select a preset layout (gaming, community, developer)", handling="How to handle existing channels (archive, keep, delete)")
    @app_commands.default_permissions(administrator=True)
    async def slash_optimize(ctx: commands.Context, preset: str, handling: str):
        if preset.lower() not in ["gaming", "community", "developer"]:
            await ctx.send("❌ Invalid preset. Use gaming, community, or developer.", ephemeral=True)
            return
        if handling.lower() not in ["archive", "keep", "delete"]:
            await ctx.send("❌ Invalid handling option. Use archive, keep, or delete.", ephemeral=True)
            return

        await ctx.send(f"⚙️ Starting server optimization under preset **{preset}** and handling **{handling}**... (This will take a moment)", ephemeral=True)
        try:
            success = await optimize_guild_structure(ctx.guild, preset, handling)
            if success:
                await ctx.send("✅ Server optimization complete! Welcome and logs channels have been successfully established.", ephemeral=True)
            else:
                await ctx.send("❌ Server optimization failed. See console logs for details.", ephemeral=True)
        except Exception as e:
            logger.error(f"Error during slash optimization: {e}")
            await ctx.send(f"❌ Error during optimization: {e}", ephemeral=True)

    # Music Bot Slash/Hybrid Commands
    @bot_instance.hybrid_command(name="play", description="Plays a song from YouTube URL or search query.")
    @app_commands.describe(query="Song URL or YouTube search keywords")
    async def music_play(ctx: commands.Context, query: str):
        await ctx.defer()
        if not ctx.author.voice:
            await ctx.send("❌ You must be in a voice channel to use this command.")
            return
            
        player = bot_instance.get_music_player(ctx.guild.id)
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

    @bot_instance.hybrid_command(name="pause", description="Pauses current playback.")
    async def music_pause(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
        if player and player.pause():
            await ctx.send("⏸️ Paused playback.")
        else:
            await ctx.send("❌ Music is not playing or already paused.")

    @bot_instance.hybrid_command(name="resume", description="Resumes current playback.")
    async def music_resume(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
        if player and player.resume():
            await ctx.send("▶️ Resumed playback.")
        else:
            await ctx.send("❌ Playback is not paused.")

    @bot_instance.hybrid_command(name="skip", description="Skips the current song.")
    async def music_skip(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
        if player and player.skip():
            await ctx.send("⏭️ Skipped current song.")
        else:
            await ctx.send("❌ Nothing is playing.")

    @bot_instance.hybrid_command(name="stop", description="Stops music and clears queue.")
    async def music_stop(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
        if player and player.stop():
            await ctx.send("⏹️ Playback stopped and queue cleared.")
        else:
            await ctx.send("❌ Nothing is playing.")

    @bot_instance.hybrid_command(name="queue", description="Shows the current music queue.")
    async def music_queue(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
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

    @bot_instance.hybrid_command(name="volume", description="Adjusts player volume.")
    @app_commands.describe(level="Volume level from 0 to 100")
    async def music_volume(ctx: commands.Context, level: int):
        if level < 0 or level > 100:
            await ctx.send("❌ Volume must be between 0 and 100.")
            return
        player = bot_instance.get_music_player(ctx.guild.id)
        if player:
            vol = player.set_volume(level / 100.0)
            await ctx.send(f"🔊 Volume set to **{int(vol * 100)}%**")
        else:
            await ctx.send("❌ Music player is not active.")

    @bot_instance.hybrid_command(name="nowplaying", description="Shows details of the now playing song.")
    async def music_nowplaying(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
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

    @bot_instance.hybrid_command(name="shuffle", description="Shuffles the queue.")
    async def music_shuffle(ctx: commands.Context):
        player = bot_instance.get_music_player(ctx.guild.id)
        if player and len(player.queue) > 1:
            import random
            random.shuffle(player.queue)
            await ctx.send("🔀 Shuffled the queue.")
        else:
            await ctx.send("❌ Queue has fewer than 2 songs to shuffle.")

    # Leveling System Slash/Hybrid Commands
    @bot_instance.hybrid_command(name="rank", description="Shows rank information.")
    @app_commands.describe(member="Select a member (optional)")
    async def level_rank(ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        from leveling import leveling_system
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

    @bot_instance.hybrid_command(name="leaderboard", description="Shows the server XP leaderboard.")
    async def level_leaderboard(ctx: commands.Context):
        from leveling import leveling_system
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

    @bot_instance.hybrid_command(name="setlevelrole", description="Configures role reward for reaching a level.")
    @app_commands.describe(level="Level required", role="Role to reward")
    @app_commands.default_permissions(administrator=True)
    async def level_setrole(ctx: commands.Context, level: int, role: discord.Role):
        config = utils.load_config()
        if "leveling_settings" not in config:
            config["leveling_settings"] = {}
        if "level_roles" not in config["leveling_settings"]:
            config["leveling_settings"]["level_roles"] = {}
            
        config["leveling_settings"]["level_roles"][str(level)] = str(role.id)
        utils.save_config(config)
        bot_instance.config = config
        
        await ctx.send(f"✅ Users reaching Level **{level}** will now automatically receive the **{role.name}** role!")

    @bot_instance.hybrid_command(name="giveaway", description="Manage giveaways.")
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
        action = action.lower().strip()
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
                guild = bot_instance.get_guild(guild_id)
                if guild:
                    ch = guild.get_channel(channel_id)
                    if ch:
                        try:
                            message = await ch.fetch_message(msg_id)
                            await bot_instance.end_giveaway_action(message, gw, giveaways)
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
                guild = bot_instance.get_guild(guild_id)
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

# Ticket panel deployment
async def deploy_ticket_panel_message(guild_id: int, channel_id: int):
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
        embed = discord.Embed(
            title="🎟️ Support Helpdesk",
            description="Need assistance? Click the button below to open a private support ticket.\n\n"
                        "Our moderation staff will be notified and will assist you inside your private channel.",
            color=discord.Color.blurple()
        )
        view = TicketPanelView()
        msg = await channel.send(embed=embed, view=view)
        
        # Save deployed panel ID in config (Tier 5.7)
        guild_conf = utils.get_guild_config(str(channel.guild.id))
        guild_conf["ticket_settings"]["ticket_channel_id"] = str(channel_id)
        guild_conf["ticket_settings"]["panel_message_id"] = str(msg.id)
        utils.save_guild_config(str(channel.guild.id), guild_conf)
        
        logger.info(f"Ticket support panel deployed in #{channel.name}")
        return True
    except Exception as e:
        logger.error(f"Failed to deploy ticket panel: {e}")
        return False

# Server layout backup
def backup_guild_layout(guild: discord.Guild):
    """Generates a JSON-compatible layout of the guild structure (categories, channels, roles, overwrites)."""
    backup_data = {
        "name": guild.name,
        "verification_level": str(guild.verification_level),
        "explicit_content_filter": str(guild.explicit_content_filter),
        "roles": [],
        "categories": [],
        "uncategorized_channels": []
    }
    
    # 1. Backup roles
    for r in guild.roles:
        if r.is_default() or r.managed:
            continue
        backup_data["roles"].append({
            "name": r.name,
            "color": r.color.value,
            "hoist": r.hoist,
            "permissions": r.permissions.value,
            "position": r.position
        })
        
    # Helper to serialize channel overwrites
    def serialize_overwrites(channel):
        serialized = []
        for target, overwrite in channel.overwrites.items():
            if isinstance(target, discord.Role):
                target_type = "role"
                target_name = target.name
            else:
                target_type = "member"
                target_name = target.name
            
            allow, deny = overwrite.pair()
            serialized.append({
                "target_type": target_type,
                "target_name": target_name,
                "target_id": target.id,  # Serialize by ID (Tier 3.13)
                "allow": allow.value,
                "deny": deny.value
            })
        return serialized
        
    # 2. Backup categories and channels
    for cat in guild.categories:
        cat_data = {
            "name": cat.name,
            "position": cat.position,
            "overwrites": serialize_overwrites(cat),
            "channels": []
        }
        
        for ch in cat.channels:
            chan_data = {
                "name": ch.name,
                "type": str(ch.type),
                "position": ch.position,
                "overwrites": serialize_overwrites(ch)
            }
            cat_data["channels"].append(chan_data)
            
        backup_data["categories"].append(cat_data)
        
    # 3. Backup uncategorized channels
    for ch in guild.channels:
        if ch.category is None and not isinstance(ch, discord.CategoryChannel):
            backup_data["uncategorized_channels"].append({
                "name": ch.name,
                "type": str(ch.type),
                "position": ch.position,
                "overwrites": serialize_overwrites(ch)
            })
            
    return backup_data

# Server layout restore
async def restore_guild_layout(guild: discord.Guild, backup_data: dict):
    """Rebuilds the guild channels, categories, roles and overrides from backup data."""
    logger.info(f"Starting server layout restore on '{guild.name}'...")
    
    # 1. Restore Roles
    created_roles = {}
    created_roles["@everyone"] = guild.default_role
    
    for r_data in backup_data.get("roles", []):
        role_name = r_data["name"]
        role = discord.utils.get(guild.roles, name=role_name)
        if not role:
            try:
                role = await guild.create_role(
                    name=role_name,
                    permissions=discord.Permissions(r_data["permissions"]),
                    color=discord.Color(r_data["color"]),
                    hoist=r_data["hoist"],
                    reason="Server Layout Restore"
                )
                logger.info(f"Restored role: '{role_name}'")
            except Exception as e:
                logger.error(f"Failed to restore role '{role_name}': {e}")
                continue
        created_roles[role_name] = role
        
    # Helper to deserialize overrides
    def deserialize_overwrites(overwrites_data):
        overwrites = {}
        for ow in overwrites_data:
            target_name = ow["target_name"]
            target_type = ow["target_type"]
            target_id = ow.get("target_id")
            
            target = None
            if target_type == "role":
                if target_id:
                    target = guild.get_role(int(target_id))
                if not target:
                    target = created_roles.get(target_name) or discord.utils.get(guild.roles, name=target_name)
            else:
                if target_id:
                    target = guild.get_member(int(target_id))
                if not target:
                    target = discord.utils.get(guild.members, name=target_name)
                
            if target:
                allow_perms = discord.Permissions(ow["allow"])
                deny_perms = discord.Permissions(ow["deny"])
                overwrites[target] = discord.PermissionOverwrite.from_pair(allow_perms, deny_perms)
        return overwrites

    # Clean existing channels by archiving them to prevent data loss
    archive_category = discord.utils.get(guild.categories, name="📦 PRE-RESTORE ARCHIVE")
    if not archive_category:
        try:
            archive_category = await guild.create_category(
                name="📦 PRE-RESTORE ARCHIVE",
                overwrites={guild.default_role: discord.PermissionOverwrite(view_channel=False)},
                reason="Archive before restore"
            )
        except Exception:
            pass
            
    if archive_category:
        for ch in list(guild.channels):
            if ch.category == archive_category or ch == archive_category:
                continue
            try:
                await ch.edit(category=archive_category)
            except Exception:
                pass

    # 2. Restore Categories and Channels
    for cat_data in backup_data.get("categories", []):
        cat_name = cat_data["name"]
        cat_overwrites = deserialize_overwrites(cat_data.get("overwrites", []))
        
        try:
            category = await guild.create_category(
                name=cat_name,
                overwrites=cat_overwrites,
                position=cat_data.get("position"),
                reason="Layout Restore"
            )
            logger.info(f"Restored category: '{cat_name}'")
        except Exception as e:
            logger.error(f"Failed to restore category '{cat_name}': {e}")
            continue
            
        for ch_data in cat_data.get("channels", []):
            chan_name = ch_data["name"]
            chan_type = ch_data["type"]
            chan_overwrites = deserialize_overwrites(ch_data.get("overwrites", []))
            
            try:
                if chan_type == "text":
                    await guild.create_text_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overwrites,
                        position=ch_data.get("position"),
                        reason="Layout Restore"
                    )
                    logger.info(f"Restored text channel #{chan_name}")
                else:
                    await guild.create_voice_channel(
                        name=chan_name,
                        category=category,
                        overwrites=chan_overwrites,
                        position=ch_data.get("position"),
                        reason="Layout Restore"
                    )
                    logger.info(f"Restored voice channel '{chan_name}'")
            except Exception as e:
                logger.error(f"Failed to restore channel '{chan_name}': {e}")
                
    # 3. Restore uncategorized channels
    for ch_data in backup_data.get("uncategorized_channels", []):
        chan_name = ch_data["name"]
        chan_type = ch_data["type"]
        chan_overwrites = deserialize_overwrites(ch_data.get("overwrites", []))
        
        try:
            if chan_type == "text":
                await guild.create_text_channel(
                    name=chan_name,
                    overwrites=chan_overwrites,
                    position=ch_data.get("position"),
                    reason="Layout Restore"
                )
                logger.info(f"Restored uncategorized text channel #{chan_name}")
            else:
                await guild.create_voice_channel(
                    name=chan_name,
                    overwrites=chan_overwrites,
                    position=ch_data.get("position"),
                    reason="Layout Restore"
                )
                logger.info(f"Restored uncategorized voice channel '{chan_name}'")
        except Exception as e:
            logger.error(f"Failed to restore uncategorized channel '{chan_name}': {e}")
            
    logger.info("Server layout restore process complete.")
    return True

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
