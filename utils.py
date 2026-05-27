import json
import os
import logging
import shutil
import threading
import asyncio
import sys
from collections import deque

def get_writeable_path(filename: str) -> str:
    """Get path to a writeable file in the app directory (works for python script and built exe)"""
    if getattr(sys, 'frozen', False):
        base_dir = os.path.dirname(sys.executable)
    else:
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, filename)

def get_resource_path(relative_path: str) -> str:
    """Get absolute path to read-only resource, works for dev and for PyInstaller"""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# Load environment variables from .env if present (Tier 2.8) and migrate secrets (Tier 6.1)
def load_env_file():
    env_path = get_writeable_path(".env")
    env_data = {}
    
    # 1. Read existing .env if it exists
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    parts = line.split("=", 1)
                    if len(parts) == 2:
                        key = parts[0].strip()
                        val = parts[1].strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        env_data[key] = val
                        os.environ[key] = val
        except Exception as e:
            print(f"Error loading .env file: {e}")
            
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
        if not os.path.exists(CONFIG_PATH):
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Ensure nested keys exist (merging with defaults)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in config:
                        config[k] = v
                    elif isinstance(v, dict):
                        for sub_k, sub_v in v.items():
                            if sub_k not in config[k]:
                                config[k][sub_k] = sub_v
                return config
        except Exception as e:
            print(f"Error loading config: {e}")
            return DEFAULT_CONFIG

def save_config(config):
    with config_lock:
        try:
            with open(CONFIG_PATH, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
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

def setup_logging():
    ensure_ffmpeg_path()
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Console formatter
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s', '%Y-%m-%d %H:%M:%S')
    
    # Avoid duplicate handlers on re-entry (Tier 4.3)
    has_stream = any(isinstance(h, logging.StreamHandler) and not isinstance(h, WebConsoleHandler) for h in logger.handlers)
    has_web = any(isinstance(h, WebConsoleHandler) for h in logger.handlers)
    
    if not has_stream:
        # Stream Handler
        sh = logging.StreamHandler()
        sh.setFormatter(formatter)
        logger.addHandler(sh)
        
    if not has_web:
        # Web Console Handler
        wh = WebConsoleHandler()
        wh.setFormatter(formatter)
        logger.addHandler(wh)
    
    # Reduce noisy libraries
    logging.getLogger("discord").setLevel(logging.WARNING)
    logging.getLogger("websockets").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.INFO)

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
                    import auth
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
def get_guild_config(guild_id: str) -> dict:
    config = load_config()
    guild_configs = config.setdefault("guild_configs", {})
    guild_conf = guild_configs.setdefault(str(guild_id), {})
    
    # Fill defaults if missing
    for key in ["welcome_settings", "automod_settings", "ticket_settings"]:
        if key not in guild_conf:
            guild_conf[key] = DEFAULT_CONFIG[key].copy()
    if "custom_commands" not in guild_conf:
        guild_conf["custom_commands"] = {}
        
    return guild_conf

def save_guild_config(guild_id: str, guild_conf: dict):
    config = load_config()
    guild_configs = config.setdefault("guild_configs", {})
    guild_configs[str(guild_id)] = guild_conf
    save_config(config)

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
    return guild_conf.get("custom_commands", config.get("custom_commands", {}))

# Isolated Giveaway Store (Tier 7.2)
GIVEAWAYS_PATH = get_writeable_path("giveaways.json")
giveaways_lock = asyncio.Lock()

async def load_giveaways() -> dict:
    async with giveaways_lock:
        if not os.path.exists(GIVEAWAYS_PATH):
            # Try to migrate from config.json first to avoid data loss
            config = load_config()
            gws = config.get("giveaways", {})
            if gws:
                try:
                    with open(GIVEAWAYS_PATH, "w", encoding="utf-8") as f:
                        json.dump(gws, f, indent=2)
                    if "giveaways" in config:
                        del config["giveaways"]
                        save_config(config)
                except Exception as e:
                    print(f"Error migrating giveaways: {e}")
                return gws
            else:
                try:
                    with open(GIVEAWAYS_PATH, "w", encoding="utf-8") as f:
                        json.dump({}, f, indent=2)
                except Exception as e:
                    print(f"Error creating giveaways.json: {e}")
                return {}
        try:
            with open(GIVEAWAYS_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"Error loading giveaways: {e}")
            return {}

async def save_giveaways(giveaways: dict) -> None:
    async with giveaways_lock:
        try:
            with open(GIVEAWAYS_PATH, "w", encoding="utf-8") as f:
                json.dump(giveaways, f, indent=2)
        except Exception as e:
            print(f"Error saving giveaways: {e}")

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
