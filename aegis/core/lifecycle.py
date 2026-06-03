import logging
import os
from typing import Tuple, Optional

from aegis.core.state import ReasonCode
from aegis.core.paths import UnwritableDataDirError

logger = logging.getLogger("aegis.core.lifecycle")

RETRY_START = {
    ReasonCode.NEEDS_SETUP: 2,       # config check
    ReasonCode.DB_RECOVERY: 3,       # database check
    ReasonCode.TOKEN_RECOVERY: 5,    # token check
    ReasonCode.INTENT_RECOVERY: 6,   # intents check
}

def _bootstrap_hosting_mode_from_env() -> None:
    """One-time AEGIS_HOSTING_MODE bootstrap for headless cloud deploys.

    Honored only when ``config.json`` does not already carry a valid
    ``hosting_mode``. A pre-existing persisted value is never overwritten so
    a stale Render / self-hosted env var cannot silently stomp an explicit
    Maintainer choice.
    """
    valid = ("local_pc", "cloud")
    import utils
    config = utils.load_config()
    if config.get("hosting_mode") in valid:
        return
    env_val = os.environ.get("AEGIS_HOSTING_MODE", "").strip().lower()
    if not env_val:
        return
    if env_val not in valid:
        logger.warning(
            f"AEGIS_HOSTING_MODE={env_val!r} is not a valid hosting mode "
            f"(expected 'local_pc' or 'cloud'); ignoring."
        )
        return
    with utils.config_lock:
        cfg = utils.load_config()
        if cfg.get("hosting_mode") in valid:
            return
        cfg["hosting_mode"] = env_val
        utils.save_config(cfg)
    logger.info(f"Hosting mode bootstrapped from AEGIS_HOSTING_MODE: {env_val}")


async def run_startup_checks(core, start_at: int = 0, end_at: Optional[int] = None) -> Tuple[str, Optional[ReasonCode]]:
    """Runs the 7 startup checks in order starting from start_at index, up to end_at index (inclusive).
    Returns (verdict, reason_code). Verdict is one of 'OK', 'FATAL-to-bot', 'FATAL-to-app'.
    """
    # 0. Data Directory Check
    if start_at <= 0 and (end_at is None or end_at >= 0):
        try:
            core.paths.ensure()
            core.health.record_check("data_directory", "OK")
        except (UnwritableDataDirError, OSError) as exc:
            logger.error(f"FATAL-to-app: resolved data directory is unwritable: {exc}")
            core.health.record_fatal(exc)
            core.health.record_check("data_directory", "FATAL-to-app")
            return "FATAL-to-app", None

    # 1. Logging Check
    if start_at <= 1 and (end_at is None or end_at >= 1):
        try:
            from aegis.core.logging_setup import setup_logging
            setup_logging(core.paths)
            core.health.record_check("logging", "OK")
        except Exception as exc:
            # Degrade to console and continue
            logger.warning(f"Logging initialization degraded to console: {exc}")
            core.health.record_check("logging", "OK")

    # 2. Config Check
    if start_at <= 2 and (end_at is None or end_at >= 2):
        try:
            try:
                _bootstrap_hosting_mode_from_env()
            except Exception as e:
                logger.error(f"Hosting mode bootstrap failed: {e}")
            from aegis.config.loader import ConfigStore
            core.config = ConfigStore.load(core.paths)
            if not core.config.is_setup_complete():
                raise ValueError("Setup not complete")
            core.health.record_check("config", "OK")
        except Exception:
            logger.info("Config Check: needs-setup")
            core.health.record_check("config", "FATAL-to-bot")
            return "FATAL-to-bot", ReasonCode.NEEDS_SETUP

    # 3. Database Check
    if start_at <= 3 and (end_at is None or end_at >= 3):
        try:
            from aegis.db.engine import make_engine
            from aegis.db.maintenance import integrity_check
            if core.db is None:
                core.db = make_engine(core.paths)
            if not integrity_check(core.db):
                raise RuntimeError("Database integrity check failed")
            core.health.record_check("database", "OK")
            core.health.database = {"reachable": True, "integrity_ok": True, "at_head": False}
        except Exception as exc:
            logger.error(f"Database Check failed: {exc}")
            core.health.record_fatal(exc)
            core.health.record_check("database", "FATAL-to-bot")
            core.health.database = {"reachable": False, "integrity_ok": False, "at_head": False}
            return "FATAL-to-bot", ReasonCode.DB_RECOVERY

    # 4. Migrations Check
    if start_at <= 4 and (end_at is None or end_at >= 4):
        try:
            from aegis.db.maintenance import run_migrations
            success, reason = run_migrations(core.paths, core.db)
            if not success:
                logger.error("Migrations Check failed")
                core.health.record_check("migrations", "FATAL-to-bot")
                core.health.database["at_head"] = False
                return "FATAL-to-bot", reason or ReasonCode.DB_RECOVERY
            
            # Execute one-time idempotent legacy import and wire leveling system engine (Req 18.3, 18.4)
            try:
                from sqlalchemy.orm import sessionmaker
                from aegis.db.legacy_import import run_legacy_import
                from aegis.bot.leveling import leveling_system
                
                Session = sessionmaker(bind=core.db)
                with Session() as session:
                    run_legacy_import(session, core.paths)
                
                leveling_system.set_engine(core.db)
            except Exception:
                logger.exception("Failed to run legacy importer or bind leveling system")
                
            core.health.record_check("migrations", "OK")
            core.health.database["at_head"] = True
        except Exception as exc:
            logger.error(f"Migrations Check exception: {exc}")
            core.health.record_fatal(exc)
            core.health.record_check("migrations", "FATAL-to-bot")
            core.health.database["at_head"] = False
            return "FATAL-to-bot", ReasonCode.DB_RECOVERY

    # 5. Token Check
    if start_at <= 5 and (end_at is None or end_at >= 5):
        try:
            from utils import get_bot_token
            from aegis.bot.runner import validate_token
            config_dict = core.config.as_dict() if core.config else None
            token = get_bot_token(config_dict)

            verdict = await validate_token(token)
            if verdict in ("OK", "INTENT_FAILED"):
                core.health.record_check("token", "OK")
            else:
                logger.info("Token Check: token-recovery")
                core.health.record_check("token", "FATAL-to-bot")
                return "FATAL-to-bot", ReasonCode.TOKEN_RECOVERY
        except Exception as exc:
            logger.exception("Token check failed unexpectedly")
            core.health.record_fatal(exc)
            core.health.record_check("token", "FATAL-to-bot")
            return "FATAL-to-bot", ReasonCode.TOKEN_RECOVERY

    # 6. Intents Check
    if start_at <= 6 and (end_at is None or end_at >= 6):
        try:
            from utils import get_bot_token
            from aegis.bot.runner import validate_token
            config_dict = core.config.as_dict() if core.config else None
            token = get_bot_token(config_dict)

            verdict = await validate_token(token)
            if verdict == "OK":
                core.health.record_check("intents", "OK")
                core.health.intents = "declared_enabled"
            elif verdict == "INTENT_FAILED":
                logger.info("Intents Check: intent-recovery")
                core.health.record_check("intents", "FATAL-to-bot")
                core.health.intents = "missing"
                return "FATAL-to-bot", ReasonCode.INTENT_RECOVERY
            else:
                core.health.record_check("intents", "FATAL-to-bot")
                core.health.intents = "unknown"
                return "FATAL-to-bot", ReasonCode.INTENT_RECOVERY
        except Exception as exc:
            logger.exception("Intents check failed unexpectedly")
            core.health.record_fatal(exc)
            core.health.record_check("intents", "FATAL-to-bot")
            core.health.intents = "unknown"
            return "FATAL-to-bot", ReasonCode.INTENT_RECOVERY

    return "OK", None
