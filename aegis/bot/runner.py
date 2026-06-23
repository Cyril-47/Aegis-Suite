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
