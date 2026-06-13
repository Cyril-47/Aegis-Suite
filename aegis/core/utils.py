import json
import os
import logging
import shutil
import threading
import asyncio
import sys
from collections import deque

logger = logging.getLogger("utils")

def get_writeable_path(filename: str) -> str:
    """Get path to a writeable file in the app directory (works for python script and built exe)"""
    try:
        # Avoid circular import by doing inline import
        from aegis.core.paths import Paths
        p = Paths()
        if filename == "config.json":
            return str(p.config_file)
        return str(p.root / filename)
    except Exception:
        if getattr(sys, 'frozen', False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        if filename == "config.json":
            return os.path.join(base_dir, "config", "config.json")
        return os.path.join(base_dir, filename)


def get_resource_path(relative_path: str) -> str:
    """Get absolute path to read-only resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        # In dev mode, utils.py lives in aegis/core, so project root is 2 levels up
        base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base_path, relative_path)

# Load environment variables from .env if present (Tier 2.8) and migrate secrets (Tier 6.1)
def load_env_file():
    env_path = get_writeable_path(".env")
    enc_path = get_writeable_path(".env.enc")
    env_data = {}

    # 0. If .env.enc is present, decrypt it via Windows DPAPI and treat the
    # plaintext as if it had been read from .env. The plaintext is parsed
    # in-memory only — it is never materialized to disk. This is the
    # release-mode path for the local Windows EXE deployment; cloud
    # deployments (Render / self-hosted) skip this branch because no .env.enc
    # ships with the platform-provisioned image and DPAPI is unavailable
    # on Linux.
    encrypted_lines = None
    if os.path.exists(enc_path):
        try:
            from aegis.core.secret_store import decrypt_env_file, CorruptedSecretFile
            try:
                plaintext_bytes = decrypt_env_file(enc_path)
            except CorruptedSecretFile as exc:
                print(f"[!] Encrypted secrets at {enc_path} could not be loaded: {exc}")
                plaintext_bytes = None
            if plaintext_bytes is not None:
                encrypted_lines = plaintext_bytes.decode("utf-8", errors="replace").splitlines()
        except Exception as exc:
            # Never let a failure in the encryption path block startup; on
            # cloud hosts the platform-injected env vars take precedence.
            print(f"[!] Could not load secret_store: {exc}")

    # 1. Read existing .env if it exists (legacy plaintext path), or fall
    # back to the decrypted .env.enc lines from step 0.
    plaintext_lines = None
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                plaintext_lines = f.readlines()
        except Exception as e:
            print(f"Error loading .env file: {e}")

    source_lines = encrypted_lines if encrypted_lines is not None else plaintext_lines
    if source_lines is not None:
        for raw_line in source_lines:
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("=", 1)
            if len(parts) != 2:
                continue
            key = parts[0].strip()
            val = parts[1].strip()
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                val = val[1:-1]
            env_data[key] = val
            # Platform-provided env vars (Render / self-hosted) take precedence
            # over file-loaded values to preserve the cloud secrets path.
            if key not in os.environ or not os.environ.get(key):
                os.environ[key] = val
            
    # 2. Check config.json for migrations
    config_path = get_writeable_path("config.json")
    config_updated = False
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                
            # Migrate bot token if present
            token = config.get("bot_token")
            if token and token != "********":
                env_data["DISCORD_BOT_TOKEN"] = token
                os.environ["DISCORD_BOT_TOKEN"] = token
                config["bot_token"] = ""
                config_updated = True
                
            # Migrate admin password hash if present
            pwd_hash = config.get("admin_password_hash")
            if pwd_hash and pwd_hash != "********":
                env_data["ADMIN_PASSWORD_HASH"] = pwd_hash
                os.environ["ADMIN_PASSWORD_HASH"] = pwd_hash
                config["admin_password_hash"] = ""
                config_updated = True
                
        except Exception as e:
            print(f"Error migrating secrets from config.json: {e}")

    # 3. Ensure JWT_SECRET exists in .env
    if "JWT_SECRET" not in env_data:
        import secrets
        jwt_sec = secrets.token_hex(32)
        env_data["JWT_SECRET"] = jwt_sec
        os.environ["JWT_SECRET"] = jwt_sec
        
        # We need to save the new JWT_SECRET back to .env
        try:
            with open(env_path, "w", encoding="utf-8") as f:
                for k, v in env_data.items():
                    f.write(f"{k}={v}\n")
            print("[+] Successfully initialized JWT_SECRET in .env!")
            
            # Persist to .env.enc using DPAPI if available
            from pathlib import Path
            from aegis.core.secret_store import is_dpapi_available, encrypt_env_file
            if is_dpapi_available():
                try:
                    encrypt_env_file(Path(env_path), Path(enc_path))
                    print("[+] Successfully persisted generated JWT_SECRET to .env.enc via DPAPI!")
                    if sys.platform == "win32":
                        try:
                            os.remove(env_path)
                            print("[+] Plaintext .env removed after successful encryption.")
                        except Exception as e:
                            print(f"[-] Failed to delete plaintext .env: {e}")
                except Exception as e:
                    print(f"[-] Failed to encrypt generated env file via DPAPI: {e}")
        except Exception as e:
            print(f"Error saving JWT_SECRET to .env: {e}")
            
    # 4. Save config.json if updated (secrets removed)
    if config_updated:
        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            # Re-write all env values to .env to make sure everything is saved
            with open(env_path, "w", encoding="utf-8") as f:
                for k, v in env_data.items():
                    f.write(f"{k}={v}\n")
            print("[+] Successfully migrated secrets from config.json to .env!")
            
            # Persist to .env.enc using DPAPI if available
            from pathlib import Path
            from aegis.core.secret_store import is_dpapi_available, encrypt_env_file
            if is_dpapi_available():
                try:
                    encrypt_env_file(Path(env_path), Path(enc_path))
                    print("[+] Successfully persisted migrated secrets to .env.enc via DPAPI!")
                    if sys.platform == "win32":
                        try:
                            os.remove(env_path)
                            print("[+] Plaintext .env removed after successful encryption.")
                        except Exception as e:
                            print(f"[-] Failed to delete plaintext .env: {e}")
                except Exception as e:
                    print(f"[-] Failed to encrypt migrated env file via DPAPI: {e}")
        except Exception as e:
            print(f"Error saving config.json after secret migration: {e}")

load_env_file()

def get_bot_token(config=None):
    token = os.environ.get("DISCORD_BOT_TOKEN")
    if token:
        return token
    if config is None:
        config = load_config()
    return config.get("bot_token", "")

# Config path
CONFIG_PATH = get_writeable_path("config.json")

# Config lock to prevent race conditions (Tier 3.1)
config_lock = threading.RLock()

# Lazy initialized FFmpeg checker (Tier 4.9)
ffmpeg_initialized = False

def ensure_ffmpeg_path():
    global ffmpeg_initialized
    if ffmpeg_initialized:
        return
    if not shutil.which("ffmpeg"):
        import sys
        if sys.platform == "win32":
            local_app_data = os.environ.get("LOCALAPPDATA")
            if local_app_data:
                winget_packages = os.path.join(local_app_data, "Microsoft", "WinGet", "Packages")
                if os.path.exists(winget_packages):
                    for root, dirs, files in os.walk(winget_packages):
                        if "ffmpeg.exe" in files:
                            os.environ["PATH"] = root + os.pathsep + os.environ.get("PATH", "")
                            break
    ffmpeg_initialized = True

# Default config structure
DEFAULT_CONFIG = {
    "bot_token": "",
    "client_id": "",
    "hosting_mode": "",
    "welcome_settings": {
        "enabled": True,
        "channel_id": None,
        "channel_name": "welcome",
        "message_title": "Welcome to the Server, {user}!",
        "message_description": "We are thrilled to have you here! Please make sure to check out the rules and have a wonderful time.",
        "embed_color": "#6366F1",
        "auto_assign_roles": []
    },
    "automod_settings": {
        "enabled": True,
        "block_profanity": True,
        "block_links": False,
        "max_mentions": 5,
        "log_channel_id": None,
        "log_channel_name": "mod-logs",
        "profanity_words": [
            "badword1",
            "badword2"
        ]
    },
    "custom_commands": {
        "!website": "Visit our official website at https://example.com!",
        "!rules": "Please read #rules-and-info. Be respectful and have fun!"
    },
    "ticket_settings": {
        "enabled": True,
        "category_name": "🎟️ SUPPORT TICKETS",
        "staff_role_name": "Moderator",
        "ticket_channel_id": None,
        "panel_message_id": None
    },
    "admin_password_hash": "",
    "scheduled_messages": [],
    "leveling_settings": {
        "enabled": False,
        "xp_per_message": 15,
        "xp_cooldown_seconds": 60,
        "level_up_channel": None,
        "level_roles": {},
        "ignored_channels": [],
        "ignored_roles": []
    },
    "auto_responders": [],
    "giveaways": {}
}

def load_config():
    with config_lock:
        from pathlib import Path
        from aegis.core.paths import Paths
        from aegis.config.loader import ConfigStore
        root_path = None
        if CONFIG_PATH:
            try:
                root_path = Path(CONFIG_PATH).resolve().parent.parent
            except Exception:
                pass
        paths = Paths(root=root_path)
        if not os.path.exists(CONFIG_PATH):
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            store = ConfigStore.load(paths)
            config = store.as_dict()
            # Ensure nested keys exist (merging with defaults)
            for k, v in DEFAULT_CONFIG.items():
                if k not in config or config[k] is None:
                    config[k] = v
                elif isinstance(v, dict):
                    if not isinstance(config[k], dict):
                        config[k] = v
                    else:
                        for sub_k, sub_v in v.items():
                            if sub_k not in config[k] or config[k][sub_k] is None:
                                config[k][sub_k] = sub_v
            return config
        except Exception:
            # Fallback to direct json.load or DEFAULT_CONFIG on validation failure
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    for k, v in DEFAULT_CONFIG.items():
                        if k not in config or config[k] is None:
                            config[k] = v
                        elif isinstance(v, dict):
                            if not isinstance(config[k], dict):
                                config[k] = v
                            else:
                                for sub_k, sub_v in v.items():
                                    if sub_k not in config[k] or config[k][sub_k] is None:
                                        config[k][sub_k] = sub_v
                    return config
            except Exception:
                pass
            logger.exception("Error loading config")
            return DEFAULT_CONFIG

def save_config(config):
    with config_lock:
        try:
            from pathlib import Path
            from aegis.core.paths import Paths
            from aegis.config.loader import ConfigStore
            from aegis.config.schema import validate_config
            root_path = None
            if CONFIG_PATH:
                try:
                    root_path = Path(CONFIG_PATH).resolve().parent.parent
                except Exception:
                    pass
            paths = Paths(root=root_path)
            model = validate_config(config)
            store = ConfigStore(paths, model)
            store.save()
            return True
        except Exception:
            # Fallback to direct file save
            try:
                with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                    json.dump(config, f, indent=2)
                return True
            except Exception:
                pass
            logger.exception("Error saving config")
            return False

# Log management
log_history = deque(maxlen=500)
active_websockets = set()

class WebConsoleHandler(logging.Handler):
    def emit(self, record):
        try:
            log_entry = self.format(record)
            log_history.append(log_entry)
            
            # Broadcast to active sockets asynchronously (Tier 3.12)
            import asyncio
            for ws in list(active_websockets):
                try:
                    # Safely get running loop
                    try:
                        loop = asyncio.get_running_loop()
                    except RuntimeError:
                        loop = asyncio.get_event_loop()
                    
                    if loop.is_running():
                        role = getattr(ws, "role", "guest")
                        ws_guild_id = getattr(ws, "guild_id", None)
                        
                        if role == "admin":
                            # Global admins get the full stream
                            asyncio.run_coroutine_threadsafe(ws.send_text(log_entry), loop)
                        elif role == "tenant" and ws_guild_id:
                            # Tenants only see logs referencing their guild ID (Gap 1)
                            if str(ws_guild_id) in log_entry:
                                asyncio.run_coroutine_threadsafe(ws.send_text(log_entry), loop)
                except Exception:
                    pass
        except Exception:
            pass

def broadcast_stats(data: dict):
    """Broadcast structured stats data to all active WebSocket clients."""
    import asyncio
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            return
    if not loop.is_running():
        return
    msg = json.dumps({"type": "stats_update", "data": data})
    for ws in list(active_websockets):
        try:
            role = getattr(ws, "role", "guest")
            if role in ("admin", "tenant"):
                asyncio.run_coroutine_threadsafe(ws.send_text(msg), loop)
        except Exception:
            pass

def is_regex_safe(pattern: str) -> bool:
    if not pattern:
        return False
    if len(pattern) > 100:
        return False
    import re as pyre
    try:
        pyre.compile(pattern)
    except pyre.error:
        return False
    # Check for nested quantifiers to mitigate ReDoS vulnerability (Tier 2.5)
    if pyre.search(r'\([^)]*[\*\+\{\}][^)]*\)[\*\+\?\{]', pattern):
        return False
    return True

# Active linking codes storage (Tier 5.1 & Tier 8.1)
# Note: pending_pairings is saved directly in config.json to persist across bot restarts.

def can_generate_code(guild_id: str) -> bool:
    """Checks if a linking code was generated for this server in the last 5 minutes (Tier 6.3)"""
    import time
    now = time.time()
    with config_lock:
        config = load_config()
        pending = config.get("pending_pairings", {})
        for code, data in pending.items():
            created_at = data.get("expires_at", 0) - 600
            if data.get("guild_id") == str(guild_id) and now - created_at < 300:
                return False
    return True

def record_failed_code_attempt(entered_code: str):
    """Increments the attempt counter for active codes close to the entered code and wipes them after 3 bad tries (Tier 6.4)"""
    if not entered_code or len(entered_code) != 6:
        return
    entered_upper = entered_code.upper().strip()
    with config_lock:
        config = load_config()
        pending = config.get("pending_pairings", {})
        to_delete = []
        for code, data in pending.items():
            # Calculate Hamming distance (number of mismatched characters)
            mismatches = sum(1 for c1, c2 in zip(code, entered_upper) if c1 != c2)
            if mismatches <= 2:  # Typo/Brute-force guess threshold
                data["attempts"] = data.get("attempts", 0) + 1
                if data["attempts"] >= 3:
                    to_delete.append(code)
        
        config_changed = False
        for code in to_delete:
            pending.pop(code, None)
            config_changed = True
            
        if config_changed or to_delete:
            config["pending_pairings"] = pending
            save_config(config)

def get_guild_id_by_code(code: str):
    """Checks the code, consumes it immediately on success, and returns guild_id (Tier 6.4 / 8.1 / 8.5)"""
    import time
    if not code:
        return None
    code_upper = code.upper().strip()
    with config_lock:
        config = load_config()
        pending = config.get("pending_pairings", {})
        
        # Clean up expired codes
        now = time.time()
        expired = [c for c, data in list(pending.items()) if now > data.get("expires_at", 0)]
        for c in expired:
            pending.pop(c, None)
            
        data = pending.get(code_upper)
        if data:
            # Check if actually expired
            if now > data.get("expires_at", 0):
                pending.pop(code_upper, None)
                config["pending_pairings"] = pending
                save_config(config)
                return None
                
            # Consume the code immediately (one-time use, replay protection)
            pending.pop(code_upper, None)
            config["pending_pairings"] = pending
            
            # Remove from revoked list so they can log in again (Tier 8.5)
            guild_id = data["guild_id"]
            revoked_list = config.setdefault("revoked_guilds", [])
            if guild_id in revoked_list:
                revoked_list.remove(guild_id)
                # Ensure the in-memory set in auth.py is also cleared
                try:
                    import aegis.core.auth as auth
                    auth._revoked_guilds.discard(guild_id)
                except Exception:
                    pass
                    
            save_config(config)
            return guild_id
            
        if expired:
            config["pending_pairings"] = pending
            save_config(config)
            
    return None

# Guild-specific config storage and helper functions (Tier 5.3)
def is_mock_guild_id(guild_id) -> bool:
    gid_str = str(guild_id)
    if gid_str.startswith("<") and gid_str.endswith(">"):
        return True
    if "Mock" in gid_str or "mock" in gid_str:
        return True
    try:
        from unittest.mock import Mock
        if isinstance(guild_id, Mock):
            return True
    except ImportError:
        pass
    return False

def get_guild_config(guild_id: str) -> dict:
    config = load_config()
    guild_configs = config.setdefault("guild_configs", {})
    
    gid_str = str(guild_id)
    if is_mock_guild_id(guild_id):
        guild_conf = {}
    else:
        guild_conf = guild_configs.setdefault(gid_str, {})
    
    # Fill defaults if missing
    for key in ["welcome_settings", "automod_settings", "ticket_settings", "leveling_settings"]:
        if key not in guild_conf:
            guild_conf[key] = DEFAULT_CONFIG[key].copy()
    if "custom_commands" not in guild_conf:
        guild_conf["custom_commands"] = {}
    if "command_permissions" not in guild_conf:
        guild_conf["command_permissions"] = {}
    if "permission_roles" not in guild_conf:
        guild_conf["permission_roles"] = {
            "admin_role_id": None,
            "moderator_role_id": None
        }
    if "music_settings" not in guild_conf:
        guild_conf["music_settings"] = {}
        
    return guild_conf

def save_guild_config(guild_id: str, guild_conf: dict):
    if is_mock_guild_id(guild_id):
        return
    gid_str = str(guild_id)
    config = load_config()
    
    old_guild_conf = config.get("guild_configs", {}).get(gid_str, {}).copy()
    
    guild_configs = config.setdefault("guild_configs", {})
    guild_configs[gid_str] = guild_conf
    save_config(config)

    # Automatically generate config snapshot
    try:
        from aegis.core.config_history import create_snapshot, compute_diff
        changed = compute_diff(old_guild_conf, guild_conf)
        if changed:
            create_snapshot(gid_str, guild_conf, changed_keys=changed, created_by="dashboard")
    except Exception:
        pass

def get_guild_welcome_settings(config, guild_id: str) -> dict:
    guild_configs = config.get("guild_configs", {})
    guild_conf = guild_configs.get(str(guild_id), {})
    # Fallback to the legacy global configuration
    return guild_conf.get("welcome_settings", config.get("welcome_settings", {}))

def get_guild_automod_settings(config, guild_id: str) -> dict:
    guild_configs = config.get("guild_configs", {})
    guild_conf = guild_configs.get(str(guild_id), {})
    return guild_conf.get("automod_settings", config.get("automod_settings", {}))

def get_guild_ticket_settings(config, guild_id: str) -> dict:
    guild_configs = config.get("guild_configs", {})
    guild_conf = guild_configs.get(str(guild_id), {})
    return guild_conf.get("ticket_settings", config.get("ticket_settings", {}))

def get_guild_custom_commands(config, guild_id: str) -> dict:
    guild_configs = config.get("guild_configs", {})
    guild_conf = guild_configs.get(str(guild_id), {})
    cmds = guild_conf.get("custom_commands")
    if not cmds:
        return config.get("custom_commands", {})
    return cmds

def get_guild_leveling_settings(config, guild_id: str) -> dict:
    guild_configs = config.get("guild_configs", {})
    guild_conf = guild_configs.get(str(guild_id), {})
    return guild_conf.get("leveling_settings", config.get("leveling_settings", {}))

# Isolated Giveaway Store (Tier 7.2, DB-backed)
_giveaways_lock = None

def _get_giveaways_lock() -> asyncio.Lock:
    global _giveaways_lock
    if _giveaways_lock is None:
        _giveaways_lock = asyncio.Lock()
    return _giveaways_lock

class LazyAsyncLock:
    async def __aenter__(self):
        return await _get_giveaways_lock().__aenter__()

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return await _get_giveaways_lock().__aexit__(exc_type, exc_val, exc_tb)

giveaways_lock = LazyAsyncLock()


def _giveaway_model_to_dict(gw):
    """Convert a Giveaway model instance to the legacy dict format."""
    from datetime import timezone
    end_time = 0.0
    if gw.end_time:
        end_time = gw.end_time.replace(tzinfo=timezone.utc).timestamp()
    return {
        "guild_id": gw.guild_id,
        "channel_id": gw.channel_id,
        "prize": gw.prize,
        "winners_count": gw.winner_count,
        "end_time": end_time,
        "entrants": json.loads(gw.entrants) if gw.entrants else [],
        "winners": json.loads(gw.winners) if gw.winners else [],
        "ended": gw.status == "ended",
        "host_id": gw.host_user_id,
        "host_name": gw.host_name or "Aegis Suite",
    }


def _dict_to_giveaway_model(msg_id, gw_dict):
    """Convert a legacy dict to fields suitable for Giveaway model creation/update."""
    from datetime import datetime, timezone
    end_time = gw_dict.get("end_time", 0)
    if end_time:
        end_dt = datetime.fromtimestamp(end_time, tz=timezone.utc).replace(tzinfo=None)
    else:
        end_dt = None
    return {
        "guild_id": str(gw_dict.get("guild_id", "")),
        "channel_id": str(gw_dict.get("channel_id", "")),
        "prize": gw_dict.get("prize", ""),
        "winner_count": gw_dict.get("winners_count", 1),
        "end_time": end_dt,
        "host_user_id": str(gw_dict.get("host_id", "")),
        "host_name": gw_dict.get("host_name", "Aegis Suite"),
        "status": "ended" if gw_dict.get("ended", False) else "active",
        "entrants": json.dumps(gw_dict.get("entrants", [])),
        "winners": json.dumps(gw_dict.get("winners", [])),
    }


def _get_db_session():
    """Get a database session if available."""
    try:
        from aegis.core.app_core import _active_cores
        if _active_cores:
            from sqlalchemy.orm import sessionmaker
            core = _active_cores[-1]
            if core.db:
                return sessionmaker(bind=core.db)()
    except Exception:
        pass
    return None


def _load_giveaways_from_db():
    """Load all giveaways from the database, returning legacy dict format."""
    session = _get_db_session()
    if session:
        try:
            from aegis.db.models import Giveaway
            rows = session.query(Giveaway).all()
            result = {}
            for row in rows:
                if row.message_id:
                    result[row.message_id] = _giveaway_model_to_dict(row)
            return result
        except Exception:
            logger.debug("DB giveaway load failed")
        finally:
            session.close()

    return _load_giveaways_from_file()


def _save_giveaways_to_db(giveaways):
    """Save giveaways dict to the database (full-replace semantics)."""
    session = _get_db_session()
    if session:
        try:
            from aegis.db.models import Giveaway
            existing = {r.message_id: r for r in session.query(Giveaway).all()}
            seen_ids = set()
            for msg_id, gw_dict in giveaways.items():
                seen_ids.add(msg_id)
                fields = _dict_to_giveaway_model(msg_id, gw_dict)
                if msg_id in existing:
                    for k, v in fields.items():
                        setattr(existing[msg_id], k, v)
                else:
                    session.add(Giveaway(message_id=msg_id, **fields))
            for msg_id, row in existing.items():
                if msg_id not in seen_ids:
                    session.delete(row)
            session.commit()
            return
        except Exception:
            session.rollback()
            logger.debug("DB giveaway save failed, falling back to file")
        finally:
            session.close()

    _save_giveaways_to_file(giveaways)


GIVEAWAYS_PATH = get_writeable_path("giveaways.json")


def _migrate_giveaways(config):
    gws = config.get("giveaways", {})
    if gws:
        with open(GIVEAWAYS_PATH, "w", encoding="utf-8") as f:
            json.dump(gws, f, indent=2)
        if "giveaways" in config:
            del config["giveaways"]
            save_config(config)
        return gws
    else:
        with open(GIVEAWAYS_PATH, "w", encoding="utf-8") as f:
            json.dump({}, f, indent=2)
        return {}


def _load_giveaways_from_file():
    if os.path.exists(GIVEAWAYS_PATH):
        try:
            with open(GIVEAWAYS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            logger.exception("Error loading giveaways from file")
    config = load_config()
    try:
        return _migrate_giveaways(config)
    except Exception:
        logger.exception("Error migrating giveaways")
        return {}


def _save_giveaways_to_file(data):
    with open(GIVEAWAYS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


async def load_giveaways() -> dict:
    try:
        return await asyncio.to_thread(_load_giveaways_from_db)
    except Exception:
        logger.exception("Error loading giveaways")
        return {}


async def save_giveaways(giveaways: dict) -> None:
    try:
        await asyncio.to_thread(_save_giveaways_to_db, giveaways)
    except Exception:
        logger.exception("Error saving giveaways")

# Per-Guild Rate Limiter (Tier 8.2 & Tier 8.6)
from collections import defaultdict
guild_request_counts = defaultdict(list)
guild_limiter_lock = threading.Lock()

def check_guild_rate_limit(guild_id: str) -> bool:
    """Enforces a sliding window limit of 60 requests per guild per minute (Tier 8.2)"""
    import time
    now = time.time()
    with guild_limiter_lock:
        timestamps = guild_request_counts[str(guild_id)]
        active = [t for t in timestamps if now - t < 60]
        if len(active) >= 60:
            guild_request_counts[str(guild_id)] = active
            return False
        active.append(now)
        guild_request_counts[str(guild_id)] = active
        return True

async def prune_stale_rate_limiters():
    """Background garbage collector task for tenant rate limiting (Tier 8.6)"""
    import time
    while True:
        try:
            await asyncio.sleep(60)
            now = time.time()
            with guild_limiter_lock:
                stale_guilds = []
                for gid, timestamps in list(guild_request_counts.items()):
                    active = [t for t in timestamps if now - t < 60]
                    if not active:
                        stale_guilds.append(gid)
                    else:
                        guild_request_counts[gid] = active
                for gid in stale_guilds:
                    guild_request_counts.pop(gid, None)
        except Exception as e:
            print(f"Error in rate limiter GC: {e}")
