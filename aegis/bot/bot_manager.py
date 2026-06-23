import asyncio
import logging
import discord
from discord.ext import commands
import aegis.core.utils as utils
import re
import json
import datetime
from typing import Optional
import aegis.core.auth as auth
import aegis.core.audit_log as audit_log

logger = logging.getLogger("DiscordBot")

# Global reference to the bot instance and background task
bot_instance = None
bot_task = None


async def resolve_embed_variables(text: str, member: discord.Member = None, guild: discord.Guild = None) -> str:
    """Replace smart variable placeholders in embed text with live data."""
    if not text:
        return text
    
    now = datetime.datetime.now()
    
    text = text.replace("{date}", now.strftime("%B %d, %Y"))
    text = text.replace("{time}", now.strftime("%I:%M %p"))
    text = text.replace("{datetime}", now.strftime("%B %d, %Y %I:%M %p"))
    
    if guild:
        text = text.replace("{server}", str(getattr(guild, "name", "") or ""))
        text = text.replace("{membercount}", str(getattr(guild, "member_count", 0) or 0))
        text = text.replace("{boost_count}", str(getattr(guild, "premium_subscription_count", 0) or 0))
        text = text.replace("{boost_tier}", str(getattr(guild, "premium_tier", 0) or 0))
        text = text.replace("{role_count}", str(len(getattr(guild, "roles", []))))
        created_at = getattr(guild, "created_at", None)
        text = text.replace("{server_created}", created_at.strftime("%B %d, %Y") if created_at else "Unknown")
        owner = getattr(guild, "owner", None)
        if owner:
            text = text.replace("{server_owner}", owner.mention)
        
        members = getattr(guild, "members", [])
        online = sum(1 for m in members if getattr(m, "status", None) != discord.Status.offline)
        text = text.replace("{online_count}", str(online))
        
        try:
            invite = None
            text_channels = getattr(guild, "text_channels", [])
            guild_me = getattr(guild, "me", None)
            for ch in text_channels:
                if guild_me and hasattr(ch, "permissions_for") and ch.permissions_for(guild_me).create_instant_invite:
                    invites = await ch.invites() if hasattr(ch, 'invites') else []
                    if invites:
                        invite = invites[0]
                        break
            if invite:
                text = text.replace("{invite_link}", f"https://discord.gg/{invite.code}")
            else:
                text = text.replace("{invite_link}", "No invite available")
        except Exception:
            text = text.replace("{invite_link}", "No invite available")
    
    if member:
        # Use display_name (nickname or username) instead of raw mention
        display_name = getattr(member, "display_name", "") or getattr(member, "name", "")
        if hasattr(display_name, "_mock_return_value"):
            display_name = ""
        text = text.replace("{user}", str(display_name))
        
        # Keep mention available as {mention} for admin who want clickable mentions
        mention = getattr(member, "mention", "")
        if hasattr(mention, "_mock_return_value"):
            mention = ""
        text = text.replace("{mention}", str(mention))
        
        name = getattr(member, "name", "")
        if hasattr(name, "_mock_return_value"):
            name = ""
        text = text.replace("{username}", str(name))
        
        top_role = getattr(member, "top_role", None)
        top_role_name = "None"
        if top_role and not hasattr(top_role, "_mock_return_value"):
            raw_name = getattr(top_role, "name", "None")
            if isinstance(raw_name, str):
                top_role_name = raw_name
        text = text.replace("{top_role}", top_role_name)
        
        created_at = getattr(member, "created_at", None)
        if created_at and not hasattr(created_at, "_mock_return_value"):
            try:
                text = text.replace("{account_age}", str((now.replace(tzinfo=None) - created_at.replace(tzinfo=None)).days))
            except Exception:
                text = text.replace("{account_age}", "Unknown")
        else:
            text = text.replace("{account_age}", "Unknown")
            
        joined_at = getattr(member, "joined_at", None)
        if joined_at and not hasattr(joined_at, "_mock_return_value"):
            try:
                text = text.replace("{member_join_date}", joined_at.strftime("%B %d, %Y"))
            except Exception:
                text = text.replace("{member_join_date}", "Unknown")
        else:
            text = text.replace("{member_join_date}", "Unknown")
    
    return text


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
    global bot_instance
    if bot_instance is not None:
        return bot_instance
    try:
        from aegis.core.app_core import _active_cores
        if _active_cores:
            core = _active_cores[0]
            if hasattr(core, "bot") and core.bot:
                return core.bot
    except Exception:
        pass
    return None

def process_embed_data_urls(embed_dicts: list[dict]) -> tuple[list[dict], list[discord.File]]:
    """
    Scans embed dictionaries for data:image/ base64 URLs.
    Replaces them with attachment:// references and returns the list of discord.File objects to attach.
    """
    import base64
    import io
    import copy
    
    files = []
    file_counter = 0
    
    # Regex to match data URL: data:image/png;base64,xxxxx
    data_url_pattern = re.compile(r'^data:image/(?P<ext>[a-zA-Z+.-]+);base64,(?P<b64>.+)$')
    
    copied_dicts = copy.deepcopy(embed_dicts)
    
    for embed in copied_dicts:
        # Check thumbnail
        if "thumbnail" in embed and isinstance(embed["thumbnail"], dict) and "url" in embed["thumbnail"]:
            url = embed["thumbnail"]["url"]
            if url and isinstance(url, str) and url.startswith("data:image/"):
                match = data_url_pattern.match(url)
                if match:
                    ext = match.group("ext")
                    if "+" in ext:
                        ext = ext.split("+")[0]
                    filename = f"thumbnail_{file_counter}.{ext}"
                    try:
                        b64_data = match.group("b64")
                        b64_data = re.sub(r'\s+', '', b64_data)
                        img_bytes = base64.b64decode(b64_data)
                        files.append(discord.File(io.BytesIO(img_bytes), filename=filename))
                        embed["thumbnail"]["url"] = f"attachment://{filename}"
                        file_counter += 1
                    except Exception as e:
                        logger.error(f"Failed to decode base64 thumbnail: {e}")
                        
        # Check image
        if "image" in embed and isinstance(embed["image"], dict) and "url" in embed["image"]:
            url = embed["image"]["url"]
            if url and isinstance(url, str) and url.startswith("data:image/"):
                match = data_url_pattern.match(url)
                if match:
                    ext = match.group("ext")
                    if "+" in ext:
                        ext = ext.split("+")[0]
                    filename = f"image_{file_counter}.{ext}"
                    try:
                        b64_data = match.group("b64")
                        b64_data = re.sub(r'\s+', '', b64_data)
                        img_bytes = base64.b64decode(b64_data)
                        files.append(discord.File(io.BytesIO(img_bytes), filename=filename))
                        embed["image"]["url"] = f"attachment://{filename}"
                        file_counter += 1
                    except Exception as e:
                        logger.error(f"Failed to decode base64 image: {e}")
                        
    return copied_dicts, files

async def add_reactions_from_embeds(msg: discord.Message, embeds: list):
    """Extract emojis from embed fields and add them as reactions to the message."""
    if not msg:
        return
    custom_emoji_pattern = r'<a?:\w+:\d+>'
    unicode_emoji_pattern = r'(?:[0-9*#]\ufe0f?\u20e3|[\U0001F1E6-\U0001F1FF]{1,2}|[\u2600-\u27BF\U0001F000-\U0001FBFF]+(?:\u200D[\u2600-\u27BF\U0001F000-\U0001FBFF]+)*)'
    emoji_regex = re.compile(rf'({custom_emoji_pattern}|{unicode_emoji_pattern})')

    emojis_to_add = []
    for embed in embeds:
        fields = []
        if isinstance(embed, discord.Embed):
            fields = embed.fields
        elif isinstance(embed, dict):
            fields = embed.get("fields", [])
        
        for field in fields:
            name = None
            if hasattr(field, "name"):
                name = field.name
            elif isinstance(field, dict):
                name = field.get("name")
            
            if name:
                match = emoji_regex.search(name)
                if match:
                    emoji = match.group(1)
                    if emoji not in emojis_to_add:
                        emojis_to_add.append(emoji)
    
    for emoji in emojis_to_add:
        try:
            await msg.add_reaction(emoji)
        except Exception as e:
            logger.warning(f"Failed to add reaction {emoji} to message {msg.id}: {e}")

from aegis.bot.tickets import TicketCloseView, TicketPanelView

from aegis.bot.giveaways import GiveawayJoinView, start_giveaway_bot, reroll_giveaway_bot  # noqa: F401

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
        self.anti_raid = None  # Initialized in setup_hook
        self._new_members = set()  # Track recently joined members for first-msg analysis

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
                from aegis.bot.music import MusicPlayer
                self.music_players[guild_id] = MusicPlayer(guild)
        return self.music_players.get(guild_id)

    async def setup_hook(self):
        # Register events & commands
        logger.info("Setting up bot hooks and syncing slash commands...")
        self.add_view(TicketPanelView())
        self.add_view(TicketCloseView())
        self.add_view(GiveawayJoinView())
        
        # Load cogs for modular architecture
        from aegis.bot.cog_loader import load_all_cogs
        loaded_cogs, failed_cogs = await load_all_cogs(self)
        logger.info(f"Loaded {len(loaded_cogs)} cogs successfully")
        if failed_cogs:
            for cog, error in failed_cogs:
                logger.warning(f"Failed to load cog {cog}: {error}")
        
        # Start scheduled messages background scheduler and watchdog
        self.scheduler_task = self.loop.create_task(self.scheduler_loop())
        self.giveaway_task = self.loop.create_task(self.giveaway_scheduler_loop())
        self.embed_scheduler_task = self.loop.create_task(self.embed_scheduler_loop())
        self.watchdog_task = self.loop.create_task(self.watchdog_loop())
        self.backup_task = self.loop.create_task(self.backup_loop())
        from aegis.bot.anti_raid import AntiRaidEngine
        self.anti_raid = AntiRaidEngine()

        def _raid_alert(guild_id_str, message):
            """Alert callback: sends alert to configured channel."""
            try:
                guild = self.get_guild(int(guild_id_str))
                if not guild:
                    return
                cfg = utils.get_guild_config(guild_id_str)
                raid_cfg = cfg.get("anti_raid_settings", {})
                ch_id = raid_cfg.get("raid_alert_channel")
                if ch_id:
                    ch = guild.get_channel(int(ch_id))
                    if ch:
                        self.loop.create_task(ch.send(f"🚨 {message}"))
            except Exception:
                pass

        def _raid_lockdown(guild_id_str, duration):
            """Lockdown callback: temp-mute new joins by locking text channels."""
            try:
                guild = self.get_guild(int(guild_id_str))
                if not guild:
                    return
                self.loop.create_task(self._apply_lockdown(guild, duration))
            except Exception:
                pass

        def _raid_verify(guild_id_str):
            """Auto-verify callback: raise verification level."""
            try:
                guild = self.get_guild(int(guild_id_str))
                if not guild:
                    return
                if guild.me.guild_permissions.manage_guild:
                    self.loop.create_task(guild.edit(verification_level=discord.VerificationLevel.HIGH))
                    logger.info(f"Auto-verify: raised verification level for guild {guild_id_str}")
            except Exception:
                pass

        def _raid_dm_owner(guild_id_str, message):
            """DM the server owner on raid."""
            try:
                guild = self.get_guild(int(guild_id_str))
                if not guild or not guild.owner:
                    return
                self.loop.create_task(guild.owner.send(f"🛡️ **Raid Alert** — {guild.name}\n{message}"))
            except Exception:
                pass

        self.anti_raid.set_alert_callback(_raid_alert)
        self.anti_raid.set_lockdown_callback(_raid_lockdown)
        self.anti_raid.set_verify_callback(_raid_verify)
        self.anti_raid.set_dm_owner_callback(_raid_dm_owner)

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

    async def _apply_lockdown(self, guild, duration_seconds):
        """Lock text channels during raid, then restore after duration."""
        locked_channels = []
        for ch in guild.text_channels:
            if not ch.permissions_for(guild.me).manage_channels:
                continue
            # Only lock channels that aren't already locked
            overwrites = ch.overwrites_for(guild.default_role)
            if overwrites.send_messages is not True:
                continue
            try:
                await ch.set_permissions(guild.default_role, send_messages=False, reason="Anti-raid lockdown")
                locked_channels.append(ch)
            except Exception:
                pass
        if locked_channels:
            logger.info(f"Lockdown: locked {len(locked_channels)} channels in {guild.name} for {duration_seconds}s")
        # Wait for duration then unlock
        await asyncio.sleep(duration_seconds)
        for ch in locked_channels:
            try:
                await ch.set_permissions(guild.default_role, send_messages=None, reason="Anti-raid lockdown ended")
            except Exception:
                pass
        if locked_channels:
            logger.info(f"Lockdown ended: unlocked {len(locked_channels)} channels in {guild.name}")

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

                # Monitor embed_scheduler_loop
                if self.embed_scheduler_task is None or self.embed_scheduler_task.done():
                    if self.embed_scheduler_task and self.embed_scheduler_task.done() and self.embed_scheduler_task.exception():
                        exc = self.embed_scheduler_task.exception()
                        logger.error(f"Embed scheduler loop crashed with exception: {exc}. Restarting...")
                    else:
                        logger.warning("Embed scheduler loop is not running. Restarting...")
                    self.embed_scheduler_task = self.loop.create_task(self.embed_scheduler_loop())
            except Exception as e:
                logger.error(f"Error in watchdog loop: {e}")
            await asyncio.sleep(30)

    async def backup_loop(self):
        logger.info("Automated backup loop started.")
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                config = utils.load_config()
                backup_cfg = config.get("backup_settings", {})
                if not backup_cfg.get("enabled", True):
                    await asyncio.sleep(3600)
                    continue
                hour = backup_cfg.get("schedule_hour", 3)
                minute = backup_cfg.get("schedule_minute", 0)
                now = datetime.datetime.now(datetime.timezone.utc)
                target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if now >= target:
                    target += datetime.timedelta(days=1)
                wait_seconds = (target - now).total_seconds()
                if wait_seconds < 60:
                    wait_seconds += 86400
                await asyncio.sleep(wait_seconds)
                await asyncio.get_event_loop().run_in_executor(None, self._run_nightly_backup)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Backup loop error")
                await asyncio.sleep(3600)

    def _run_nightly_backup(self):
        import shutil
        from aegis.core.paths import Paths
        config = utils.load_config()
        backup_cfg = config.get("backup_settings", {})
        retention = backup_cfg.get("retention_days", 7)
        use_safe = backup_cfg.get("use_safe_backup", True)
        paths = Paths()
        backup_dir = paths.backups_db
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        src = paths.db_file
        if not src.exists():
            return
        dst = backup_dir / f"aegis_backup_{timestamp}.db"
        try:
            if use_safe:
                try:
                    from aegis.db.maintenance import backup_db
                    from sqlalchemy import create_engine
                    engine = create_engine(f"sqlite:///{src}")
                    with engine.connect() as conn:
                        dbapi = conn.connection.driver_connection
                        import sqlite3
                        dest_conn = sqlite3.connect(str(dst))
                        dbapi.backup(dest_conn)
                        dest_conn.close()
                    engine.dispose()
                    logger.info(f"Nightly safe backup created: {dst.name}")
                except Exception:
                    logger.warning("Safe backup failed, falling back to shutil")
                    shutil.copy2(str(src), str(dst))
                    logger.info(f"Nightly backup (shutil) created: {dst.name}")
            else:
                shutil.copy2(str(src), str(dst))
                logger.info(f"Nightly backup created: {dst.name}")
            backups = sorted(backup_dir.glob("aegis_backup_*.db"), key=lambda p: p.stat().st_mtime)
            while len(backups) > retention:
                old = backups.pop(0)
                old.unlink(missing_ok=True)
                logger.info(f"Pruned old backup: {old.name}")
        except Exception:
            logger.exception("Nightly backup failed")

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

    async def embed_scheduler_loop(self):
        logger.info("Scheduled embeds background scheduler loop started.")
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                now = datetime.datetime.now(datetime.timezone.utc)
                config = utils.load_config()
                schedules = config.get("scheduled_embeds", [])
                
                config_changed = False
                for sched in list(schedules):
                    try:
                        scheduled_at_str = sched.get("scheduled_at")
                        if not scheduled_at_str:
                            continue
                        
                        scheduled_at = datetime.datetime.fromisoformat(scheduled_at_str.replace("Z", "+00:00"))
                        if now >= scheduled_at:
                            guild_id = int(sched["guild_id"])
                            channel_id = int(sched["channel_id"])
                            guild = self.get_guild(guild_id)
                            if guild:
                                channel = guild.get_channel(channel_id)
                                if channel:
                                    try:
                                        embeds_data = sched.get("embeds", [])
                                        embeds_data, files = process_embed_data_urls(embeds_data)
                                        content = sched.get("content")
                                        discord_embeds = [discord.Embed.from_dict(e) for e in embeds_data[:10]]
                                        if files:
                                            msg = await channel.send(content=content or None, embeds=discord_embeds, files=files)
                                        else:
                                            msg = await channel.send(content=content or None, embeds=discord_embeds)
                                        logger.info(f"Fired scheduled embed(s) in #{channel.name}")
                                        if sched.get("add_reactions"):
                                            await add_reactions_from_embeds(msg, discord_embeds)
                                    except Exception as e:
                                        logger.error(f"Failed to send scheduled embed: {e}")
                            
                            schedules.remove(sched)
                            config_changed = True
                    except Exception as e:
                        logger.error(f"Error processing scheduled embed: {e}")
                
                if config_changed:
                    with utils.config_lock:
                        new_config = utils.load_config()
                        new_config["scheduled_embeds"] = schedules
                        utils.save_config(new_config)
                        self.config = new_config
                        
            except Exception as e:
                logger.error(f"Error in embed scheduler loop: {e}")
            
            await asyncio.sleep(30)

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

        if isinstance(error, commands.BotMissingPermissions):
            try:
                perms = ", ".join(error.missing_permissions)
                await ctx.send(f"❌ I'm missing required permissions: **{perms}**. Please ask a server admin to grant these permissions to my role.")
            except Exception:
                pass
            return

        if isinstance(error, commands.CommandOnCooldown):
            try:
                await ctx.send(f"⏳ This command is on cooldown. Try again in {error.retry_after:.1f}s.", delete_after=5.0)
            except Exception:
                pass
            return

        if isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.send("❌ This command can only be used inside a Discord server.")
            except Exception:
                pass
            return

        # Log other errors
        logger.error(f"Error executing command: {error}", exc_info=error)
        try:
            await ctx.send("❌ Something went wrong while running this command. Please try again.", delete_after=10.0)
        except Exception:
            pass

    async def on_ready(self):
        logger.info(f"Bot logged in successfully as {self.user} (ID: {self.user.id})")
        logger.info(f"Currently connected to {len(self.guilds)} guilds.")

    async def on_member_join(self, member: discord.Member):
        logger.info(f"New member joined: {member.name} in guild '{member.guild.name}'")
        self.stats["joins_today"] = self.stats.get("joins_today", 0) + 1

        # Record analytics (best-effort)
        try:
            from aegis.analytics.engine import get_analytics_engine
            _ae = get_analytics_engine()
            if _ae:
                _ae.record_member_event(member.guild.id, member.id, "join")
        except Exception:
            pass

        # Wire intelligence features (Critical 1)
        try:
            from aegis.intelligence.registry import get_raid_detector, get_automation_engine
            guild_id_str = str(member.guild.id)
            member_id_str = str(member.id)
            
            get_raid_detector().record_join(guild_id_str)
            
            context = {
                "member": {
                    "id": member_id_str,
                    "username": member.name,
                },
                "guild": {
                    "id": guild_id_str,
                    "name": member.guild.name,
                }
            }
            actions = get_automation_engine().evaluate_trigger(guild_id_str, "member_join", context)
            if actions:
                from aegis.intelligence.automation import execute_automation_rule_actions
                asyncio.create_task(
                    execute_automation_rule_actions(self, member.guild, actions, context)
                )
        except Exception as e:
            logger.error(f"Error executing intelligence events in on_member_join: {e}")

        # Anti-raid detection (best-effort)
        try:
            if self.anti_raid:
                guild_config = utils.get_guild_config(str(member.guild.id))
                raid_cfg = guild_config.get("anti_raid_settings", {})
                if raid_cfg.get("enabled", False):
                    # Read config at runtime (not cached at init)
                    response_mode = raid_cfg.get("response_mode", "alert")
                    min_age = raid_cfg.get("min_account_age_days", 7)
                    score_threshold = raid_cfg.get("suspicious_score_threshold", 70)
                    dm_owner = raid_cfg.get("dm_owner_on_raid", True)
                    lockdown_duration = raid_cfg.get("lockdown_duration_seconds", 300)

                    # Calculate suspicious score
                    is_in_raid_window = len(self.anti_raid._joins.get(str(member.guild.id), [])) > 2
                    score = self.anti_raid.calculate_suspicious_score(
                        member.created_at,
                        is_default_avatar=(str(member.avatar.url) if member.avatar else "") == "",
                        username=member.name,
                        is_raid_window=is_in_raid_window,
                    )

                    # Join rate check
                    raid_event = self.anti_raid.record_join(
                        str(member.guild.id), str(member.id)
                    )
                    if raid_event:
                        # Execute the configured response mode
                        context = {
                            "join_count": raid_event["join_count"],
                            "duration_seconds": lockdown_duration,
                        }
                        self.anti_raid.execute_response(response_mode, str(member.guild.id), context)

                        # DM owner if enabled
                        if dm_owner:
                            self.anti_raid._dm_owner_callback(
                                str(member.guild.id),
                                f"{raid_event['join_count']} members joined in {raid_event['window_seconds']}s in **{member.guild.name}**."
                            )

                    # Account age check — take action based on response mode
                    if self.anti_raid.check_account_age(member.created_at, min_age):
                        account_days = (datetime.now(timezone.utc) - member.created_at).days
                        logger.warning(
                            f"Suspicious account joined: {member.name} "
                            f"(age: {account_days} days, score: {score})"
                        )

                        # Take action if score exceeds threshold
                        if score >= score_threshold and response_mode in ("lockdown", "auto_verify"):
                            if response_mode == "lockdown":
                                try:
                                    timeout_duration = min(lockdown_duration, 3600)
                                    await member.timeout(
                                        datetime.now(timezone.utc) + __import__('datetime').timedelta(seconds=timeout_duration),
                                        reason=f"Anti-raid: suspicious account (score {score})"
                                    )
                                    logger.info(f"Timed out {member.name} for {timeout_duration}s (score {score})")
                                except Exception:
                                    pass
                            elif response_mode == "auto_verify":
                                # For auto-verify, DM the user asking to verify
                                try:
                                    await member.send(
                                        f"Welcome to **{member.guild.name}**! Your account is new, so please verify yourself. "
                                        f"A moderator will review your account shortly."
                                    )
                                except Exception:
                                    pass

                        # DM owner about suspicious account
                        if dm_owner and score >= score_threshold:
                            self.anti_raid._dm_owner_callback(
                                str(member.guild.id),
                                f"Suspicious account joined **{member.guild.name}**: `{member.name}` "
                                f"(account age: {account_days}d, score: {score}/{score_threshold})"
                            )
        except Exception:
            pass

        self._new_members.add(member.id)
        # Prune after 5 minutes
        async def prune_new_member(mid=member.id):
            await asyncio.sleep(300)
            self._new_members.discard(mid)
        asyncio.get_event_loop().create_task(prune_new_member())

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
                title = await resolve_embed_variables(
                    welcome.get("message_title", "Welcome to the Server, {user}!"),
                    member=member, guild=member.guild
                )
                desc = await resolve_embed_variables(
                    welcome.get("message_description", ""),
                    member=member, guild=member.guild
                )
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
                embed.set_footer(text=await resolve_embed_variables(
                    welcome.get("footer_text", "Member #{membercount}"),
                    member=member, guild=member.guild
                ))
                
                if welcome.get("author_name"):
                    embed.set_author(
                        name=await resolve_embed_variables(welcome["author_name"], member=member, guild=member.guild),
                        icon_url=welcome.get("author_icon") or discord.Embed.Empty
                    )
                
                if welcome.get("image"):
                    embed.set_image(url=welcome["image"])
                
                for field in welcome.get("fields", []):
                    if field.get("name") and field.get("value"):
                        embed.add_field(
                            name=await resolve_embed_variables(field["name"], member=member, guild=member.guild),
                            value=await resolve_embed_variables(field["value"], member=member, guild=member.guild),
                            inline=field.get("inline", True)
                        )
                
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

        # 3. Check Member Milestones
        try:
            guild_conf = utils.get_guild_config(str(member.guild.id))
            milestone_cfg = guild_conf.get("milestone_settings", {})
            if milestone_cfg.get("enabled", False):
                milestones = milestone_cfg.get("milestones", [])
                member_count = member.guild.member_count
                fired = guild_conf.get("fired_milestones", [])
                
                for ms in milestones:
                    if member_count >= ms and str(ms) not in fired:
                        ch_id = milestone_cfg.get("channel_id")
                        if ch_id:
                            ch = member.guild.get_channel(int(ch_id))
                        else:
                            ch = member.guild.system_channel
                        
                        if ch:
                            embed_cfg = milestone_cfg.get("embed", {})
                            title = resolve_embed_variables(
                                embed_cfg.get("title", f"🎉 {member_count} MEMBERS!"),
                                member=member, guild=member.guild
                            ).replace("{membercount}", str(member_count))
                            desc = resolve_embed_variables(
                                embed_cfg.get("description", f"We just hit {member_count} members!"),
                                member=member, guild=member.guild
                            ).replace("{membercount}", str(member_count))
                            
                            color_hex = embed_cfg.get("color", "#FFD700").replace("#", "")
                            try:
                                color = discord.Color(int(color_hex, 16))
                            except ValueError:
                                color = discord.Color.gold()
                            
                            milestone_embed = discord.Embed(title=title, description=desc, color=color)
                            if member.guild.icon:
                                milestone_embed.set_thumbnail(url=member.guild.icon.url)
                            
                            try:
                                await ch.send(embed=milestone_embed)
                                fired.append(str(ms))
                                guild_conf["fired_milestones"] = fired
                                with utils.config_lock:
                                    config = utils.load_config()
                                    gc = config.get("guild_configs", {}).get(str(member.guild.id), {})
                                    gc["fired_milestones"] = fired
                                    utils.save_config(config)
                                logger.info(f"Milestone {ms} reached in {member.guild.name}")
                            except Exception as e:
                                logger.error(f"Failed to send milestone embed: {e}")
        except Exception as e:
            logger.error(f"Error checking milestones: {e}")

    async def on_member_remove(self, member: discord.Member):
        logger.info(f"Member left: {member.name} from guild '{member.guild.name}'")
        # Record analytics (best-effort)
        try:
            from aegis.analytics.engine import get_analytics_engine
            _ae = get_analytics_engine()
            if _ae:
                _ae.record_member_event(member.guild.id, member.id, "leave")
        except Exception:
            pass

        # Wire intelligence features (Critical 1)
        try:
            from aegis.intelligence.registry import get_automation_engine
            guild_id_str = str(member.guild.id)
            member_id_str = str(member.id)
            
            context = {
                "member": {
                    "id": member_id_str,
                    "username": member.name,
                },
                "guild": {
                    "id": guild_id_str,
                    "name": member.guild.name,
                }
            }
            actions = get_automation_engine().evaluate_trigger(guild_id_str, "member_leave", context)
            if actions:
                from aegis.intelligence.automation import execute_automation_rule_actions
                asyncio.create_task(
                    execute_automation_rule_actions(self, member.guild, actions, context)
                )
        except Exception as e:
            logger.error(f"Error executing intelligence events in on_member_remove: {e}")

    async def on_member_ban(self, guild: discord.Guild, user: discord.User):
        logger.info(f"Member banned: {user.name} in guild '{guild.name}'")
        try:
            from aegis.intelligence.registry import get_raid_detector, get_automation_engine
            get_raid_detector().record_mod_action(str(guild.id))
            
            context = {
                "target": {
                    "id": str(user.id),
                    "username": user.name,
                },
                "guild": {
                    "id": str(guild.id),
                    "name": guild.name,
                },
                "action": "ban"
            }
            actions = get_automation_engine().evaluate_trigger(str(guild.id), "moderation_action", context)
            if actions:
                from aegis.intelligence.automation import execute_automation_rule_actions
                asyncio.create_task(
                    execute_automation_rule_actions(self, guild, actions, context)
                )
        except Exception as e:
            logger.error(f"Error in on_member_ban: {e}")

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
        # Record analytics (best-effort)
        try:
            from aegis.analytics.engine import get_analytics_engine
            _ae = get_analytics_engine()
            if _ae and not member.bot:
                if before.channel is None and after.channel is not None:
                    _ae.record_voice_join(member.guild.id, member.id, after.channel.id)
                elif before.channel is not None and after.channel is None:
                    _ae.record_voice_leave(member.guild.id, member.id, before.channel.id)
                elif (before.channel is not None and after.channel is not None
                      and before.channel.id != after.channel.id):
                    _ae.record_voice_leave(member.guild.id, member.id, before.channel.id)
                    _ae.record_voice_join(member.guild.id, member.id, after.channel.id)
        except Exception:
            pass

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

            try:
                from aegis.analytics.engine import get_analytics_engine
                _ae = get_analytics_engine()
                if _ae and interaction.guild:
                    cmd_name = interaction.data.get("name", "") if interaction.data else ""
                    _ae.record_command(interaction.guild.id, interaction.user.id, cmd_name)
            except Exception:
                pass
            
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

        # Wire intelligence features (Critical 1)
        try:
            from aegis.intelligence.registry import (
                get_raid_detector,
                get_sentiment_analyzer,
                get_spam_detector,
                get_activity_intelligence,
                get_automation_engine
            )
            guild_id_str = str(message.guild.id)
            user_id_str = str(message.author.id)
            channel_id_str = str(message.channel.id)
            
            # Record join/message rates in raid detector
            get_raid_detector().record_message(guild_id_str)
            
            # Analyze sentiment
            get_sentiment_analyzer().analyze_message(user_id_str, channel_id_str, message.content, guild_id_str)
            
            # Record & analyze spam
            get_spam_detector().record_message(user_id_str, channel_id_str, message.content)
            
            # Record activity
            now_dt = datetime.datetime.now(datetime.timezone.utc)
            get_activity_intelligence().record_activity(guild_id_str, now_dt.hour, now_dt.weekday(), "message")
            
            # Evaluate and run automation trigger "message_sent"
            context = {
                "message": {
                    "content": message.content,
                    "length": len(message.content),
                    "author_id": user_id_str,
                    "id": str(getattr(message, "id", 0)),
                },
                "author": {
                    "id": user_id_str,
                    "username": message.author.name,
                },
                "channel": {
                    "id": channel_id_str,
                    "name": message.channel.name,
                },
                "guild": {
                    "id": guild_id_str,
                    "name": message.guild.name,
                }
            }
            actions = get_automation_engine().evaluate_trigger(guild_id_str, "message_sent", context)
            if actions:
                from aegis.intelligence.automation import execute_automation_rule_actions
                asyncio.create_task(
                    execute_automation_rule_actions(self, message.guild, actions, context)
                )
        except Exception as e:
            logger.error(f"Error executing intelligence events in on_message: {e}")

        # Record analytics (best-effort)
        try:
            from aegis.analytics.engine import get_analytics_engine
            _ae = get_analytics_engine()
            if _ae:
                _ae.record_message(
                    message.guild.id,
                    message.channel.id,
                    message.author.id,
                    len(message.content.split()) if message.content else 0,
                )
        except Exception:
            pass

        # Use cached in-memory config instead of reading file (Tier 3.3)
        config = self.config

        # Dynamic Slowmode Policy
        try:
            from aegis.bot.slowmode_tracker import slowmode_tracker
            # Reload config to pick up dashboard changes
            try:
                self.config = utils.load_config()
            except Exception:
                pass

            # Raid detector hook — check threat level and set on tracker
            try:
                from aegis.intelligence.registry import get_raid_detector
                raid_detector = get_raid_detector()
                if raid_detector:
                    result = raid_detector.analyze(str(message.guild.id))
                    threat = result.get("threat_level", "normal")
                    if threat in ["high", "critical"]:
                        slowmode_tracker.set_raid_threat(threat, str(message.guild.id))
            except Exception:
                pass

            slowmode_settings = utils.get_guild_slowmode_settings(self.config, message.guild.id)
            if slowmode_settings.get("enabled", False):
                slowmode_tracker.record_message(str(message.channel.id), str(message.author.id))
                asyncio.create_task(
                    slowmode_tracker.check_and_apply(message.guild, message.channel, slowmode_settings)
                )
            else:
                logger.debug(f"Slowmode disabled for guild {message.guild.id}")
        except Exception as e:
            logger.error(f"Slowmode error: {e}")

        # Process commands (Tier 3.4)
        await self.process_commands(message)

        self.check_stats_reset()
        self.stats["messages_today"] = self.stats.get("messages_today", 0) + 1

        # First-message analysis for new members (anti-raid)
        if message.author.id in self._new_members:
            try:
                if self.anti_raid:
                    guild_config = utils.get_guild_config(str(message.guild.id))
                    raid_cfg = guild_config.get("anti_raid_settings", {})
                    if raid_cfg.get("enabled", False):
                        mention_count = (
                            len(message.mentions) +
                            len(message.role_mentions) +
                            message.content.count("@everyone") +
                            message.content.count("@here")
                        )
                        if mention_count >= 5:
                            logger.warning(
                                f"Suspicious first message from {message.author.name}: "
                                f"{mention_count} mentions"
                            )
            except Exception:
                pass

        try:
            from aegis.core.utils import broadcast_stats
            broadcast_stats({
                "messages_today": self.stats["messages_today"],
                "commands_today": self.stats.get("commands_today", 0),
                "joins_today": self.stats.get("joins_today", 0),
            })
        except Exception:
            pass

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
                
                allowed_roles = resp.get("roles", [])
                author_roles_str = [str(r.id) for r in getattr(message.author, "roles", [])]
                if allowed_roles and not any(r in allowed_roles for r in author_roles_str):
                    continue
                    
                response_text = resp.get("response", "")
                if response_text:
                    response_text = await resolve_embed_variables(
                        response_text, member=message.author, guild=message.guild
                    )
                    response_text = response_text.replace("{channel}", message.channel.name)
                    
                embed_data = resp.get("embed")
                try:
                    self.check_stats_reset()
                    self.stats["commands_today"] = self.stats.get("commands_today", 0) + 1
                    if embed_data:
                        embed_json_str = json.dumps(embed_data)
                        embed_json_str = await resolve_embed_variables(
                            embed_json_str, member=message.author, guild=message.guild
                        )
                        embed_json_str = embed_json_str.replace("{channel}", message.channel.name)
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
        if leveling_cfg and leveling_cfg.get("enabled", False):
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
                    
                    rank_data = leveling_system.get_user_rank(str(message.guild.id), str(message.author.id))
                            
                    try:
                        lvl_embed_cfg = leveling_cfg.get("level_up_embed", {})
                        if not lvl_embed_cfg.get("enabled", True):
                            lvl_embed_cfg = {}
                        
                        title = (await resolve_embed_variables(
                            lvl_embed_cfg.get("title", "🎉 LEVEL UP!"),
                            member=message.author, guild=message.guild
                        )).replace("{level}", str(new_lvl)).replace("{xp}", str(cur_xp)).replace("{rank}", str(rank_data.get("rank", "?"))).replace("{messages}", str(tot_msg))
                        
                        desc = (await resolve_embed_variables(
                            lvl_embed_cfg.get("description", f"{message.author.mention} has leveled up to **Level {new_lvl}**!"),
                            member=message.author, guild=message.guild
                        )).replace("{level}", str(new_lvl)).replace("{xp}", str(cur_xp)).replace("{rank}", str(rank_data.get("rank", "?"))).replace("{messages}", str(tot_msg))
                        
                        color_hex = lvl_embed_cfg.get("color", "#FFD700").replace("#", "")
                        try:
                            color = discord.Color(int(color_hex, 16))
                        except ValueError:
                            color = discord.Color.gold()
                        
                        embed = discord.Embed(title=title, description=desc, color=color)
                        
                        if lvl_embed_cfg.get("show_thumbnail", True):
                            embed.set_thumbnail(url=message.author.display_avatar.url)
                        
                        if lvl_embed_cfg.get("image"):
                            embed.set_image(url=lvl_embed_cfg["image"])
                        
                        footer_text = (await resolve_embed_variables(
                            lvl_embed_cfg.get("footer_text", ""),
                            member=message.author, guild=message.guild
                        )).replace("{level}", str(new_lvl)).replace("{xp}", str(cur_xp)).replace("{rank}", str(rank_data.get("rank", "?"))).replace("{messages}", str(tot_msg))
                        if footer_text:
                            embed.set_footer(text=footer_text)
                        
                        for field in lvl_embed_cfg.get("fields", []):
                            if field.get("name") and field.get("value"):
                                field_name = (await resolve_embed_variables(
                                    field["name"], member=message.author, guild=message.guild
                                )).replace("{level}", str(new_lvl)).replace("{xp}", str(cur_xp)).replace("{rank}", str(rank_data.get("rank", "?"))).replace("{messages}", str(tot_msg))
                                field_value = (await resolve_embed_variables(
                                    field["value"], member=message.author, guild=message.guild
                                )).replace("{level}", str(new_lvl)).replace("{xp}", str(cur_xp)).replace("{rank}", str(rank_data.get("rank", "?"))).replace("{messages}", str(tot_msg))
                                embed.add_field(name=field_name, value=field_value, inline=field.get("inline", True))
                        
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

            # Record automod analytics (best-effort)
            try:
                from aegis.analytics.engine import get_analytics_engine
                _ae = get_analytics_engine()
                if _ae:
                    categories = []
                    if any("profanity" in i.lower() or "blocked word" in i.lower() for i in infractions):
                        categories.append("profanity")
                    if any("invite" in i.lower() for i in infractions):
                        categories.append("invite_link")
                    if any("link" in i.lower() for i in infractions):
                        categories.append("link")
                    if any("mention" in i.lower() for i in infractions):
                        categories.append("mention_spam")
                    for cat in categories:
                        _ae.record_mod_action(
                            message.guild.id, message.author.id,
                            event_type="automod_block",
                            reason=infraction_reason,
                            automod_category=cat,
                        )
            except Exception:
                pass

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
from aegis.bot.restructuring import audit_guild_data, optimize_guild_structure, backup_guild_layout, restore_guild_layout  # noqa: F401


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
    try:
        from aegis.bot.leveling import leveling_system
        leveling_system.stop()
    except Exception as e:
        logger.error(f"Error stopping leveling system: {e}")
        
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

from aegis.bot.tickets import deploy_ticket_panel_message  # noqa: F401


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
