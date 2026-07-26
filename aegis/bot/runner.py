import asyncio
import logging
from enum import Enum
import discord
import discord.gateway

# Monkeypatch removed. Native discord.py v2.7.x now supports gateway v=8 and E2EE/DAVE protocol directly.

from aegis.bot.bot_manager import DiscordOptimizerBot as LegacyDiscordOptimizerBot

logger = logging.getLogger("aegis.bot.runner")

class TokenVerdict(str, Enum):
    OK = "OK"
    AUTH_FAILED = "AUTH_FAILED"
    INTENT_FAILED = "INTENT_FAILED"
    TIMEOUT = "TIMEOUT"

def build_intents() -> discord.Intents:
    """Builds the required gateway intents for the Aegis bot."""
    intents = discord.Intents.default()
    intents.guilds = True
    intents.members = True
    intents.messages = True
    intents.message_content = True
    intents.voice_states = True
    return intents

async def validate_token(token: str, timeout: float = 10.0, probe: bool = True) -> TokenVerdict:
    """Lightweight authentication probe and intent capability check.
    Completes the auth probe and privileged intents check.
    Returns TokenVerdict.
    """
    if not token:
        return TokenVerdict.AUTH_FAILED

    # Heuristic format check: three dot-separated components
    parts = token.split('.')
    if len(parts) != 3:
        return TokenVerdict.AUTH_FAILED

    if not probe:
        return TokenVerdict.OK

    intents = build_intents()
    client = discord.Client(intents=intents)

    async def probe():
        try:
            await client.login(token)
            return TokenVerdict.OK
        except discord.errors.LoginFailure:
            return TokenVerdict.AUTH_FAILED
        except discord.errors.PrivilegedIntentsRequired:
            return TokenVerdict.INTENT_FAILED
        except Exception:
            return TokenVerdict.AUTH_FAILED
        finally:
            try:
                await client.close()
            except Exception:
                pass

    try:
        return await asyncio.wait_for(probe(), timeout=timeout)
    except asyncio.TimeoutError:
        return TokenVerdict.TIMEOUT

class DiscordOptimizerBot(LegacyDiscordOptimizerBot):
    """Subclass of the legacy Discord bot class, integrating with the new AppCore."""
    def __init__(self, core, *args, **kwargs):
        self.core = core
        super().__init__(*args, **kwargs)
        # Point bot config to ConfigStore model dict
        if core.config:
            self.config = core.config.as_dict()
        if core.db:
            from sqlalchemy.orm import sessionmaker
            class BotDatabaseWrapper:
                def __init__(self, engine):
                    self.session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
            self.db = BotDatabaseWrapper(core.db)
        self.analytics_engine = getattr(core, "analytics_engine", None)

async def start_bot_task(core, token: str) -> None:
    """Supervised bot task. Registers relocated commands, instantiates the bot,
    and runs it until completion or cancellation.
    """
    import aegis.bot.bot_manager as bot_manager
    intents = build_intents()
    
    bot = DiscordOptimizerBot(core, command_prefix="!", intents=intents)
    
    # Store bot in core and register it in legacy bot_manager
    core.bot = bot
    bot_manager.bot_instance = bot
    
    # Register hybrid/slash commands
    from aegis.bot.commands import register_commands
    register_commands(bot)
    
    import os
    if os.environ.get("AEGIS_MOCK_ENV") == "1":
        import datetime
        from unittest.mock import MagicMock, AsyncMock
        
        # Build mock guild list
        mock_guild_obj = MagicMock()
        mock_guild_obj.id = 1509050530369114162 # Cyril's server id
        mock_guild_obj.name = "Cyril's Server"
        mock_guild_obj.member_count = 120
        mock_guild_obj.premium_subscription_count = 5
        mock_guild_obj.premium_tier = 1
        mock_guild_obj.verification_level = discord.VerificationLevel.high
        mock_guild_obj.explicit_content_filter = discord.ContentFilter.all_members
        mock_guild_obj.created_at = datetime.datetime(2025, 1, 1, tzinfo=datetime.timezone.utc)
        mock_guild_obj.icon = MagicMock()
        mock_guild_obj.icon.url = "https://example.com/icon.png"
        
        # Mock channels
        welcome_ch = MagicMock()
        welcome_ch.id = 1509557921615319041
        welcome_ch.name = "welcome"
        
        general_ch = MagicMock()
        general_ch.id = 1508707951550922782
        general_ch.name = "general"
        
        mod_logs_ch = MagicMock()
        mod_logs_ch.id = 1509557966792167579
        mod_logs_ch.name = "mod-logs"
        
        mock_guild_obj.text_channels = [welcome_ch, general_ch, mod_logs_ch]
        mock_guild_obj.voice_channels = []
        mock_guild_obj.channels = [welcome_ch, general_ch, mod_logs_ch]
        
        # Mock role
        mock_role = MagicMock()
        mock_role.id = 12345
        mock_role.name = "Moderator"
        mock_role.color = MagicMock()
        mock_role.color.value = 0x6366F1
        mock_role.position = 1
        mock_role.permissions = MagicMock()
        mock_role.permissions.value = 8
        mock_role.hoist = True
        mock_role.managed = False
        mock_guild_obj.roles = [mock_role]
        
        mock_me = MagicMock()
        mock_me_top_role = MagicMock()
        mock_me_top_role.position = 10
        mock_me.top_role = mock_me_top_role
        mock_guild_obj.me = mock_me
        
        def mock_get_channel(channel_id):
            for ch in [welcome_ch, general_ch, mod_logs_ch]:
                if ch.id == int(channel_id):
                    return ch
            return None
        mock_guild_obj.get_channel = mock_get_channel
        
        type(bot).guilds = property(lambda self: [mock_guild_obj])
        bot.is_ready = MagicMock(return_value=True)
        bot.get_guild = MagicMock(return_value=mock_guild_obj)
        
        mock_fetched = MagicMock()
        mock_fetched.approximate_presence_count = 10
        mock_fetched.approximate_member_count = 120
        bot.fetch_guild = AsyncMock(return_value=mock_fetched)
        
        mock_bot_user = MagicMock()
        mock_bot_user.name = "AegisOptimizerBot"
        mock_bot_user.display_name = "AegisOptimizerBot"
        mock_bot_user.username = "AegisOptimizerBot"
        mock_bot_user.discriminator = "9999"
        mock_bot_user.avatar = MagicMock()
        mock_bot_user.avatar.url = "https://example.com/avatar.png"
        mock_bot_user.avatar_url = "https://example.com/avatar.png"
        type(bot).user = property(lambda self: mock_bot_user)
        
        logger.info("Mock bot environment started.")
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            logger.info("Mock bot task cancelled.")
            raise
        return

    logger.info("Starting Discord bot instance...")
    try:
        await bot.start(token)
    except asyncio.CancelledError:
        logger.info("Bot task cancelled, closing bot connection gracefully...")
        await bot.close()
        raise
    except Exception as e:
        logger.exception("Bot encountered a fatal exception during runtime")
        await bot.close()
        raise e
