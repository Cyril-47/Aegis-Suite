import logging
import os
import discord
import sys
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Body, Request
from pydantic import BaseModel, Field
from typing import List, Optional
import utils
import bot_manager
import auth
import audit_log

# Configure logging
logger = logging.getLogger("WebServer")

BUILTIN_METADATA = {
    "gaming": {
        "display_name": "Gaming Lobbies",
        "category": "Gaming",
        "description": "Designed for gaming servers, featuring dedicated lounges, clips highlights, and squad voice rooms.",
        "icon": "fa-gamepad"
    },
    "clan": {
        "display_name": "Clan Squads",
        "category": "Gaming",
        "description": "Tactical setups with clan rosters, war logs, announcements, and competitive lounges.",
        "icon": "fa-shield-halved"
    },
    "esports": {
        "display_name": "Esports Arena",
        "category": "Gaming",
        "description": "Ideal for leagues, featuring brackets, match results, scrim schedules, and team voice desks.",
        "icon": "fa-trophy"
    },
    "community": {
        "display_name": "Social Community",
        "category": "Community",
        "description": "Perfect for social circles. Features interest-based channels (hobbies, media) and text lounges.",
        "icon": "fa-users"
    },
    "creator": {
        "display_name": "Content Creator",
        "category": "Creator",
        "description": "Optimized for YouTube/Twitch creators. Features content showcase, feedback, and collaboration.",
        "icon": "fa-laptop-code"
    },
    "streamer": {
        "display_name": "Live Streamer",
        "category": "Creator",
        "description": "Setup for active streamers, featuring live notifications, stream logs, and subscriber voice decks.",
        "icon": "fa-video"
    },
    "anime": {
        "display_name": "Anime Hub",
        "category": "Anime",
        "description": "Anime layout featuring discussion channels, manga chat, and movie watch party voice rooms.",
        "icon": "fa-mask"
    },
    "minimal": {
        "display_name": "Minimalist",
        "category": "Utility",
        "description": "Barebones structure with announcements, rules, general chat, and a single voice channel.",
        "icon": "fa-circle-dot"
    },
    "study": {
        "display_name": "Study Group",
        "category": "Utility",
        "description": "Designed for classes or study circles, with resources lists, Q&A helpdesk, and study desks.",
        "icon": "fa-book"
    },
    "business": {
        "display_name": "Business Office",
        "category": "Utility",
        "description": "Professional setup for workspace collaborations, project teams, and standup voice desks.",
        "icon": "fa-briefcase"
    },
    "support": {
        "display_name": "Support Desk",
        "category": "Support",
        "description": "Customer helpdesk setup with ticket panels, staff lobby, and mod log channels.",
        "icon": "fa-ticket"
    }
}
BUILTIN_NAMES = set(BUILTIN_METADATA.keys())

from collections import defaultdict
import time
import threading

# Simple rate limiter (Tier 2.7)
login_attempts = defaultdict(list)
limiter_lock = threading.Lock()

def check_login_rate_limit(ip: str) -> bool:
    """Returns True if the IP is allowed to attempt login, False if rate limited."""
    now = time.time()
    with limiter_lock:
        attempts = login_attempts[ip]
        # Filter attempts to last 15 minutes (900 seconds) (Tier 6.5)
        attempts = [t for t in attempts if now - t < 900]
        login_attempts[ip] = attempts
        if len(attempts) >= 5: # Max 5 attempts per 15 minutes
            return False
        attempts.append(now)
        return True

# Helper to safely parse IDs (Tier 3.11)
def parse_id(val: str, name: str = "ID") -> int:
    try:
        return int(val)
    except (ValueError, TypeError):
        raise HTTPException(status_code=400, detail=f"Invalid {name} format: must be numeric.")

# Helper to get active bot (Tier 4.4)
def get_active_bot():
    # Use central AppCore reference (Req 18.2)
    from aegis.core.app_core import _active_cores
    if _active_cores:
        core = _active_cores[0]
        if hasattr(core, "bot"):
            return core.bot
    import bot_manager
    return bot_manager.get_bot()

# Lifespan logic is handled by AppCore lifecycle state transitions

router = APIRouter()

# auth_middleware is defined in aegis/web/app.py
# Ensure static folder exists in development
if not getattr(sys, 'frozen', False):
    os.makedirs(utils.get_writeable_path("static"), exist_ok=True)

# Pydantic models for configuration
from typing import Dict, Literal

class WelcomeSettingsModel(BaseModel):
    enabled: bool
    channel_id: Optional[str] = None
    channel_name: str
    message_title: str
    message_description: str
    embed_color: str
    auto_assign_roles: List[str] = Field(default_factory=list)

class AutomodSettingsModel(BaseModel):
    enabled: bool
    block_profanity: bool
    block_links: bool
    max_mentions: int
    log_channel_id: Optional[str] = None
    log_channel_name: str
    profanity_words: List[str] = Field(default_factory=list)
    block_invites: bool = False
    whitelisted_domains: List[str] = Field(default_factory=list)
    whitelisted_invites: List[str] = Field(default_factory=list)

class TicketSettingsModel(BaseModel):
    enabled: bool
    category_name: str
    staff_role_name: str
    ticket_channel_id: Optional[str] = None
    panel_message_id: Optional[str] = None

class CommandPermissionRule(BaseModel):
    mode: Literal["everyone", "moderator", "admin", "owner", "role", "roles"]
    role_id: Optional[str] = None
    role_ids: List[str] = Field(default_factory=list)

class PermissionRoles(BaseModel):
    admin_role_id: Optional[str] = None
    moderator_role_id: Optional[str] = None

class LevelingConfigModel(BaseModel):
    enabled: bool = False
    xp_per_message: int = 15
    xp_cooldown_seconds: int = 60
    level_up_channel: Optional[str] = None
    level_roles: dict = Field(default_factory=dict)
    ignored_channels: List[str] = Field(default_factory=list)
    ignored_roles: List[str] = Field(default_factory=list)

class ConfigModel(BaseModel):
    client_id: str
    welcome_settings: WelcomeSettingsModel
    automod_settings: AutomodSettingsModel
    ticket_settings: Optional[TicketSettingsModel] = None
    custom_commands: Optional[dict] = Field(default_factory=dict)
    admin_password_hash: Optional[str] = ""
    command_permissions: Dict[str, CommandPermissionRule] = Field(default_factory=dict)
    permission_roles: PermissionRoles = Field(default_factory=PermissionRoles)
    leveling_settings: Optional[LevelingConfigModel] = None

class HostingModePutRequest(BaseModel):
    # Dedicated request body for PUT /api/hosting-mode. The handler enforces
    # that the value (after .strip()) equals exactly "local_pc" or "cloud" — a
    # plain ``str`` is used here so missing / non-string / unknown values are
    # caught by the handler with HTTP 400 (rather than Pydantic's 422 default)
    # to satisfy Requirement 8.3.
    hosting_mode: str

class LoginRequest(BaseModel):
    password: str

class SetupRequest(BaseModel):
    password: str

class OptimizeRequest(BaseModel):
    preset: str
    handling: str

class CreateRoleRequest(BaseModel):
    name: str
    color: str
    hoist: bool = False

class RolePanelButton(BaseModel):
    role_id: str
    label: str
    emoji: Optional[str] = None
    style: str

class RolePanelDeployRequest(BaseModel):
    guild_id: str
    channel_id: str
    title: str
    description: str
    color: str
    buttons: List[RolePanelButton]

class TemplateSaveRequest(BaseModel):
    guild_id: str
    name: str

class TemplateApplyRequest(BaseModel):
    guild_id: str
    name: str
    customizations: Optional[dict] = None
    handling: Optional[str] = "archive"

class TemplateUploadRequest(BaseModel):
    name: str
    data: dict

class MusicPlayRequest(BaseModel):
    query: str

class MusicVolumeRequest(BaseModel):
    volume: float

class ScheduledMessageModel(BaseModel):
    id: Optional[str] = None
    guild_id: str
    channel_id: str
    content: str
    schedule_type: str
    datetime: Optional[str] = None
    interval_type: Optional[str] = None
    interval_value: Optional[int] = 1
    embed: Optional[dict] = None
    enabled: bool = True
    next_run: Optional[str] = None

# LevelingConfigModel moved above ConfigModel

class AutoResponderModel(BaseModel):
    id: Optional[str] = None
    guild_id: str
    trigger_type: str
    trigger: str
    response: str

class GiveawayStartRequest(BaseModel):
    channel_id: str
    prize: str
    winners_count: int
    duration: str
    embed: Optional[dict] = None
    enabled: bool = True
    channels: List[str] = Field(default_factory=list)
    roles: List[str] = Field(default_factory=list)
    host: Optional[str] = None

# API Endpoints

@router.get("/api/auth/setup-status")
async def get_auth_setup_status():
    has_hash = bool(os.environ.get("ADMIN_PASSWORD_HASH"))
    return {"setup": has_hash}

@router.post("/api/auth/setup")
async def setup_auth(request: SetupRequest):
    if os.environ.get("ADMIN_PASSWORD_HASH"):
        raise HTTPException(status_code=400, detail="Password is already set up.")
    
    if len(request.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
        
    hashed = auth.hash_password(request.password)
    
    # Save to env and .env file (Tier 6.1)
    env_path = utils.get_writeable_path(".env")
    env_data = {}
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "=" in line:
                        k, v = line.split("=", 1)
                        env_data[k.strip()] = v.strip()
        except Exception:
            pass
    env_data["ADMIN_PASSWORD_HASH"] = hashed
    os.environ["ADMIN_PASSWORD_HASH"] = hashed
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            for k, v in env_data.items():
                f.write(f"{k}={v}\n")
    except Exception as e:
        logger.error(f"Failed to write admin password hash to .env: {e}")
        raise HTTPException(status_code=500, detail="Failed to save credentials to environment.")
        
    token = auth.create_session("global", "admin")
    audit_log.log_action("system", "BOT_CONTROL", "Admin password configured")
    return {"status": "success", "token": token}

@router.post("/api/auth/login")
async def login_auth(request: Request, login_data: LoginRequest):
    hashed = os.environ.get("ADMIN_PASSWORD_HASH")
    
    ip = request.client.host if request.client else "unknown"
    if not check_login_rate_limit(ip):
        raise HTTPException(status_code=429, detail="Too many login attempts. Please try again in 15 minutes.")
        
    input_code = login_data.password.upper().strip()
    
    # 1. Try treating password input as a 6-digit connection code first (Tier 6.6)
    if len(input_code) == 6 and input_code.isalnum():
        guild_id = utils.get_guild_id_by_code(input_code)
        if guild_id:
            token = auth.create_session(guild_id, "tenant") # Signed JWT tenant session (Gap 1)
            audit_log.log_action("system", "BOT_CONTROL", f"User logged in to manage server: {guild_id}", guild_id)
            with limiter_lock:
                login_attempts.pop(ip, None)
            return {"status": "success", "token": token, "role": "user", "guild_id": guild_id}
        else:
            # Check/increment failed attempts on matching close codes to wipe them after 3 bad tries
            utils.record_failed_code_attempt(input_code)
            
    # 2. Fallback to verification against the admin password
    if not hashed:
        raise HTTPException(status_code=400, detail="Authentication is not configured. Setup password first.")
        
    if auth.verify_password(login_data.password, hashed):
        token = auth.create_session("global", "admin") # Signed JWT admin session (Gap 1)
        audit_log.log_action("system", "BOT_CONTROL", "Admin logged in successfully")
        with limiter_lock:
            login_attempts.pop(ip, None)
        return {"status": "success", "token": token, "role": "admin", "guild_id": "global"}
    else:
        raise HTTPException(status_code=401, detail="Invalid password or server linking code.")

@router.post("/api/auth/logout")
async def logout_auth(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        auth.destroy_session(token)
        audit_log.log_action("system", "BOT_CONTROL", "Admin logged out")
    return {"status": "success"}

@router.get("/api/stats")
async def get_stats():
    return bot_manager.get_bot_stats()

@router.get("/api/status")
async def get_status(request: Request):
    import shutil
    bot = bot_manager.get_bot()
    config = utils.load_config()
    has_token = bool(utils.get_bot_token(config))
    ffmpeg_installed = bool(shutil.which("ffmpeg"))
    
    # Check session role and guild_id using JWT explicit fields (Gap 1)
    role = "guest"
    guild_id = None
    
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        
    if token and auth.validate_session(token):
        guild_id = auth.get_session_guild_id(token)
        role = auth.get_session_role(token) or "guest"
        # Map tenant role to frontend expected "user" string
        if role == "tenant":
            role = "user"
        
    # Normalize the persisted hosting_mode for the response payload — empty
    # string, missing key, or any value other than the two valid enum values
    # is reported as ``null`` (Requirement 8.6, 5.4).
    hosting_mode_raw = config.get("hosting_mode")
    hosting_mode_value = hosting_mode_raw if hosting_mode_raw in ("local_pc", "cloud") else None

    status_data = {
        "status": "running" if bot and bot.is_ready() else ("connecting" if bot else "stopped"),
        "has_token": has_token,
        "ffmpeg_installed": ffmpeg_installed,
        "role": role,
        "guild_id": guild_id,
        "bot_user": None,
        "client_id": config.get("client_id", ""),
        "hosting_mode": hosting_mode_value
    }
    
    if bot and bot.is_ready():
        status_data["bot_user"] = {
            "username": bot.user.name,
            "discriminator": bot.user.discriminator,
            "id": str(bot.user.id),
            "avatar_url": str(bot.user.display_avatar.url) if bot.user.avatar else None,
            "guilds_count": len(bot.guilds)
        }
        
    return status_data

@router.get("/api/hosting-mode")
async def get_hosting_mode():
    """Return the persisted hosting mode (or ``null`` when unset / invalid).

    Allowed for any authenticated session (admin or tenant) — ``auth_middleware``
    handles the 401 path for missing / invalid tokens, and the response value
    is non-sensitive (Requirement 8.1, 8.5).
    """
    config = utils.load_config()
    raw = config.get("hosting_mode")
    value = raw if raw in ("local_pc", "cloud") else None
    return {"hosting_mode": value}

@router.put("/api/hosting-mode")
async def put_hosting_mode(request: Request, body: dict = Body(...)):
    """Persist a new hosting mode. Admin-only (Requirement 7.7, 8.4)."""
    # 1. Admin-only handler-level role check. ``auth_middleware`` has already
    # rejected unauthenticated requests upstream with HTTP 401 (Req 8.5).
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    if auth.get_session_role(token) != "admin":
        raise HTTPException(status_code=403, detail="Forbidden: Admin role required")

    # 2. Body validation (Requirement 8.3). config.json is NOT touched on a 400.
    if not isinstance(body, dict):
        raise HTTPException(
            status_code=400,
            detail="Invalid hosting_mode value. Must be 'local_pc' or 'cloud'."
        )
    new_raw = body.get("hosting_mode")
    if not isinstance(new_raw, str):
        raise HTTPException(
            status_code=400,
            detail="Invalid hosting_mode value. Must be 'local_pc' or 'cloud'."
        )
    new_value = new_raw.strip()
    if new_value not in ("local_pc", "cloud"):
        raise HTTPException(
            status_code=400,
            detail="Invalid hosting_mode value. Must be 'local_pc' or 'cloud'."
        )

    # 3. Persist under the same config_lock used by every other config writer
    # (Requirement 5.1, 9.5). The old value (default "") is captured before
    # the write so the audit log can name both values.
    with utils.config_lock:
        config = utils.load_config()
        old_value = config.get("hosting_mode", "") or ""
        config["hosting_mode"] = new_value
        success = utils.save_config(config)

    if not success:
        # Disk write failed — surface as HTTP 500 and skip the audit log so
        # the audit trail does not falsely claim a change took effect (mirrors
        # the existing pattern in POST /api/config).
        raise HTTPException(status_code=500, detail="Failed to save hosting mode.")

    # 4. Best-effort audit log entry (Requirement 7.6). audit_log.log_action
    # already swallows write errors internally, so a logging failure does not
    # roll back the config write.
    try:
        audit_log.log_action(
            actor="admin",
            category="CONFIG_CHANGE",
            action=f"Hosting mode changed from '{old_value}' to '{new_value}'",
        )
    except Exception as e:
        logger.error(f"Failed to append audit log entry for hosting mode change: {e}")

    return {"status": "success", "hosting_mode": new_value}

@router.get("/api/config")
async def get_config(request: Request, guild_id: Optional[str] = None):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if not session_guild_id or not session_role:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    config = utils.load_config().copy()
    
    # Strip the residual bot_token key from the legacy on-disk config so the
    # response body never exposes that field (R2.5 — managed-hosting migration).
    # Tokens live exclusively in the server-side .env via DISCORD_BOT_TOKEN.
    config.pop("bot_token", None)
    
    # Hide password hash
    config["admin_password_hash"] = "********" if os.environ.get("ADMIN_PASSWORD_HASH") else ""
        
    if session_role == "admin":
        target_guild_id = guild_id if guild_id else "global"
    else:
        target_guild_id = session_guild_id

    if target_guild_id and target_guild_id != "global":
        # Resolve guild-specific configs (Tier 5.6)
        guild_conf = utils.get_guild_config(target_guild_id)
        config["welcome_settings"] = guild_conf.get("welcome_settings", config.get("welcome_settings", {}))
        config["automod_settings"] = guild_conf.get("automod_settings", config.get("automod_settings", {}))
        config["ticket_settings"] = guild_conf.get("ticket_settings", config.get("ticket_settings", {}))
        guild_cmds = guild_conf.get("custom_commands")
        config["custom_commands"] = guild_cmds if guild_cmds else config.get("custom_commands", {})
        config["leveling_settings"] = guild_conf.get("leveling_settings", config.get("leveling_settings", {}))
        
    return config

@router.post("/api/config")
async def save_config(config_data: ConfigModel, request: Request, guild_id: Optional[str] = None):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if not session_guild_id or not session_role:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Merge with existing file to ensure we don't break extra fields
    current_config = utils.load_config()
    new_data = config_data.model_dump()
    
    if session_role == "admin":
        target_guild_id = guild_id if guild_id else "global"
    else:
        target_guild_id = session_guild_id

    if target_guild_id and target_guild_id != "global":
        # Save to guild-specific configs (Tier 5.6)
        guild_conf = utils.get_guild_config(target_guild_id)
        guild_conf["welcome_settings"] = new_data["welcome_settings"]
        guild_conf["automod_settings"] = new_data["automod_settings"]
        if new_data.get("ticket_settings"):
            guild_conf["ticket_settings"] = new_data["ticket_settings"]
        if new_data.get("custom_commands"):
            guild_conf["custom_commands"] = new_data["custom_commands"]
        if new_data.get("leveling_settings"):
            guild_conf["leveling_settings"] = new_data["leveling_settings"]
            
        utils.save_guild_config(target_guild_id, guild_conf)
        
        # Update AppCore ConfigStore reference
        core = getattr(request.app.state, "core", None)
        if not core:
            from aegis.core.app_core import _active_cores
            if _active_cores:
                core = _active_cores[-1]
        if core:
            from aegis.config.loader import ConfigStore
            try:
                core.config = ConfigStore.load(core.paths)
            except Exception as e:
                logger.error(f"Failed to reload AppCore config: {e}")

        # Update running bot references
        bot = bot_manager.get_bot()
        if bot:
            bot.config = utils.load_config()
            logger.info(f"Bot configuration updated in-memory for guild {target_guild_id}.")
            
        audit_log.log_action("admin", "CONFIG_CHANGE", f"Dashboard configuration saved for server {target_guild_id}", target_guild_id)
        return {"status": "success", "token_changed": False}
        
    else:
        # Global administrator configuration saving
        # Defensive: drop any stray bot_token field; tokens live only in server .env
        new_data.pop("bot_token", None)

        # Always keep bot_token and admin_password_hash empty in config.json
        new_data["bot_token"] = ""
        new_data["admin_password_hash"] = ""
        
        for k, v in new_data.items():
            if k == "admin_password_hash":
                continue
            current_config[k] = v
            
        success = utils.save_config(current_config)
        if not success:
            raise HTTPException(status_code=500, detail="Failed to save configuration file.")
            
        # Update AppCore ConfigStore reference
        core = getattr(request.app.state, "core", None)
        if not core:
            from aegis.core.app_core import _active_cores
            if _active_cores:
                core = _active_cores[-1]
        if core:
            from aegis.config.loader import ConfigStore
            try:
                core.config = ConfigStore.load(core.paths)
            except Exception as e:
                logger.error(f"Failed to reload AppCore config: {e}")

        # Dynamically update the running bot settings if running
        bot = bot_manager.get_bot()
        if bot:
            bot.config = current_config
            logger.info("Bot configuration updated in-memory.")
            
        audit_log.log_action("admin", "CONFIG_CHANGE", "Dashboard configuration saved")
        return {"status": "success", "token_changed": False}

@router.get("/api/guilds")
async def get_guilds(request: Request):
    bot = get_active_bot()
    if not bot or not bot.is_ready():
        return []
    
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    guilds_list = []
    for g in bot.guilds:
        if session_role == "admin" or str(g.id) == session_guild_id:
            guilds_list.append({
                "id": str(g.id),
                "name": g.name,
                "icon_url": str(g.icon.url) if g.icon else None,
                "member_count": g.member_count
            })
    return guilds_list

@router.get("/api/guilds/{guild_id}/audit")
async def audit_guild(guild_id: str):
    bot = get_active_bot()
    
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found. Ensure the bot is added to the server.")
        
    try:
        report = bot_manager.audit_guild_data(guild)
        return report
    except Exception as e:
        logger.error(f"Error auditing guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/guilds/{guild_id}/optimize")
async def optimize_guild(guild_id: str, request: OptimizeRequest):
    """DEPRECATED: Kept for backwards compatibility with legacy integration checks.
    Dashboard UI has migrated to the Server Layouts & Templates deployment workflow.
    """
    logger.warning(f"Deprecated endpoint /api/guilds/{guild_id}/optimize called.")
    bot = get_active_bot()
        
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    preset = request.preset.lower()
    handling = request.handling.lower()
    
    if preset not in ["gaming", "community", "developer"]:
        raise HTTPException(status_code=400, detail="Invalid preset selected.")
    if handling not in ["archive", "keep", "delete"]:
        raise HTTPException(status_code=400, detail="Invalid channel handling method.")
        
    try:
        # Optimization is blocking / takes a little time, but since it's async, we run it in the event loop
        # We can run it in a background task so we respond instantly or wait for it to complete.
        # Let's await it so the frontend knows when it's done! It takes ~5-15 seconds.
        success = await bot_manager.optimize_guild_structure(guild, preset, handling)
        if success:
            audit_log.log_action("admin", "BACKUP_ACTION", f"Applied server optimization preset '{preset}' (handling: {handling})", guild_id)
            return {"status": "success", "message": f"Server optimized successfully using {preset} preset."}
        else:
            raise HTTPException(status_code=500, detail="Server optimization failed. Check logs.")
    except Exception as e:
        logger.error(f"Error optimizing guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/guilds/{guild_id}/channels")
async def get_guild_channels(guild_id: str):
    bot = get_active_bot()
    
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    channels_list = []
    for ch in guild.text_channels:
        channels_list.append({
            "id": str(ch.id),
            "name": ch.name,
            "type": "text"
        })
    return channels_list

class TicketSetupRequest(BaseModel):
    guild_id: str
    channel_id: str

@router.get("/api/commands")
async def get_commands(request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    if session_role == "tenant" and session_guild_id:
        return utils.get_guild_custom_commands(config, session_guild_id)
    return config.get("custom_commands", {})

@router.post("/api/commands")
async def save_commands(request: Request, commands: dict = Body(...), guild_id: Optional[str] = None):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        target_guild_id = session_guild_id
    elif session_role == "admin" and guild_id:
        target_guild_id = guild_id
    else:
        target_guild_id = None

    if target_guild_id and target_guild_id != "global":
        guild_conf = utils.get_guild_config(target_guild_id)
        guild_conf["custom_commands"] = commands
        utils.save_guild_config(target_guild_id, guild_conf)
        
        # Update AppCore ConfigStore reference
        core = getattr(request.app.state, "core", None)
        if not core:
            from aegis.core.app_core import _active_cores
            if _active_cores:
                core = _active_cores[-1]
        if core:
            from aegis.config.loader import ConfigStore
            try:
                core.config = ConfigStore.load(core.paths)
            except Exception as e:
                logger.error(f"Failed to reload AppCore config: {e}")
                
        bot = bot_manager.get_bot()
        if bot and bot.is_ready():
            bot.config = utils.load_config()
            
        audit_log.log_action("admin", "CONFIG_CHANGE", f"Configured {len(commands)} custom commands for server {target_guild_id}", target_guild_id)
        return {"status": "success"}
        
    config = utils.load_config()
    config["custom_commands"] = commands
    success = utils.save_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save custom commands.")
        
    # Update AppCore ConfigStore reference
    core = getattr(request.app.state, "core", None)
    if not core:
        from aegis.core.app_core import _active_cores
        if _active_cores:
            core = _active_cores[-1]
    if core:
        from aegis.config.loader import ConfigStore
        try:
            core.config = ConfigStore.load(core.paths)
        except Exception as e:
            logger.error(f"Failed to reload AppCore config: {e}")
            
    bot = bot_manager.get_bot()
    if bot and bot.is_ready():
        bot.config = config
        
    audit_log.log_action("admin", "CONFIG_CHANGE", f"Configured {len(commands)} custom commands")
    return {"status": "success"}

@router.post("/api/tickets/setup")
async def setup_tickets(request: TicketSetupRequest, req_data: Request):
    auth_header = req_data.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(request.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot deploy support tickets to another server")
            
    bot = get_active_bot()
        
    success = await bot_manager.deploy_ticket_panel_message(
        parse_id(request.guild_id, "guild_id"), 
        parse_id(request.channel_id, "channel_id")
    )
    if success:
        audit_log.log_action("admin", "TICKET_ACTION", f"Deployed ticket panel to channel ID '{request.channel_id}'", request.guild_id)
        return {"status": "success"}
    else:
        raise HTTPException(status_code=500, detail="Failed to deploy ticket panel in channel.")

@router.get("/api/guilds/{guild_id}/roles")
async def get_roles(guild_id: str):
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    roles_list = []
    for r in guild.roles:
        # Exclude @everyone
        if r.is_default():
            continue
        roles_list.append({
            "id": str(r.id),
            "name": r.name,
            "color": f"#{r.color.value:06X}" if r.color.value else "#99AAB5",
            "position": r.position,
            "member_count": len(r.members),
            "managed": r.managed,
            "hoist": r.hoist
        })
    # Sort roles by position descending
    roles_list.sort(key=lambda x: x["position"], reverse=True)
    return roles_list

@router.post("/api/guilds/{guild_id}/roles")
async def create_role(guild_id: str, request: CreateRoleRequest):
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    color_hex = request.color.replace("#", "")
    try:
        color_val = int(color_hex, 16)
    except ValueError:
        color_val = 0
        
    try:
        role = await guild.create_role(
            name=request.name,
            color=discord.Color(color_val),
            hoist=request.hoist,
            reason="Created via Web Dashboard"
        )
        audit_log.log_action("admin", "ROLE_ACTION", f"Created role '{request.name}'", guild_id)
        return {
            "status": "success",
            "role": {
                "id": str(role.id),
                "name": role.name,
                "color": f"#{role.color.value:06X}" if role.color.value else "#99AAB5"
            }
        }
    except Exception as e:
        logger.error(f"Failed to create role in guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/guilds/{guild_id}/roles/{role_id}")
async def delete_role(guild_id: str, role_id: str):
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    role = guild.get_role(parse_id(role_id, "role_id"))
    if not role:
        raise HTTPException(status_code=404, detail="Role not found.")
        
    # Check hierarchy and managed status to give user a helpful message
    if not guild.me.guild_permissions.manage_roles:
        raise HTTPException(
            status_code=403,
            detail="The bot does not have 'Manage Roles' permission in this server. Please grant this permission to the bot's role in Discord."
        )
        
    if role.is_default():
        raise HTTPException(status_code=400, detail="Cannot delete the @everyone role.")
        
    if role.managed:
        raise HTTPException(
            status_code=400,
            detail="This role is managed by an external integration (such as a bot, integration, or server booster) and cannot be deleted directly."
        )
        
    if role.position >= guild.me.top_role.position:
        raise HTTPException(
            status_code=403,
            detail=f"Role hierarchy constraint: The role '{role.name}' is positioned higher than or equal to the bot's highest role. "
                   f"Please open Discord Server Settings > Roles, and drag the bot's integration role above '{role.name}' to allow management."
        )
        
    try:
        import discord
        await role.delete(reason="Deleted via Web Dashboard")
        audit_log.log_action("admin", "ROLE_ACTION", f"Deleted role ID '{role_id}'", guild_id)
        return {"status": "success"}
    except discord.Forbidden:
        raise HTTPException(
            status_code=403,
            detail=f"Discord Forbidden: The bot lacks permission to delete the role '{role.name}'. Check that the bot has 'Manage Roles' and its role is high enough in the hierarchy."
        )
    except Exception as e:
        logger.error(f"Failed to delete role {role_id} in guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/roles/panel/deploy")
async def deploy_role_panel(request: RolePanelDeployRequest, req_data: Request):
    auth_header = req_data.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(request.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in role panel deploy request.")
            
    bot = get_active_bot()
        
    buttons_list = []
    for btn in request.buttons:
        buttons_list.append({
            "role_id": btn.role_id,
            "label": btn.label,
            "emoji": btn.emoji,
            "style": btn.style
        })
        
    success = await bot_manager.deploy_role_panel_message(
        parse_id(request.guild_id, "guild_id"),
        parse_id(request.channel_id, "channel_id"),
        request.title,
        request.description,
        request.color,
        buttons_list
    )
    if success:
        audit_log.log_action("admin", "ROLE_ACTION", f"Deployed role panel '{request.title}'", request.guild_id)
        return {"status": "success"}
    else:
        raise HTTPException(status_code=500, detail="Failed to deploy role panel message.")

@router.get("/api/guilds/{guild_id}/backup")
async def get_backup(guild_id: str):
    bot = get_active_bot()
        
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    try:
        backup = bot_manager.backup_guild_layout(guild)
        return backup
    except Exception as e:
        logger.error(f"Error backing up guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/guilds/{guild_id}/restore")
async def restore_backup(guild_id: str, backup_data: dict = Body(...)):
    bot = get_active_bot()
        
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    try:
        success, errors = await bot_manager.restore_guild_layout(guild, backup_data, None)
        if success:
            audit_log.log_action("admin", "BACKUP_ACTION", "Restored server structure from backup file", guild_id)
            return {"status": "success", "message": "Server structure restored successfully."}
        else:
            raise HTTPException(status_code=400, detail="Encountered errors during layout restoration:\n" + "\n".join(errors))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error restoring guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/templates")
async def get_templates():
    templates_dir = utils.get_writeable_path("templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    templates_list = []
    for filename in os.listdir(templates_dir):
        if filename.endswith(".json"):
            name = filename[:-5]
            if name.lower() not in BUILTIN_NAMES:
                templates_list.append({
                    "name": name
                })
    return templates_list

@router.get("/api/templates/builtin")
async def get_builtin_templates():
    templates_dir = utils.get_writeable_path("templates")
    builtin_dir = os.path.join(templates_dir, "builtin")
    if not os.path.exists(builtin_dir):
        builtin_dir = os.path.join("templates", "builtin")
        
    templates_list = []
    if os.path.exists(builtin_dir):
        for filename in os.listdir(builtin_dir):
            if filename.endswith(".json"):
                name = filename[:-5]
                if name.lower() in BUILTIN_NAMES:
                    file_path = os.path.join(builtin_dir, filename)
                    try:
                        import json
                        with open(file_path, "r", encoding="utf-8") as f:
                            data = json.load(f)
                        
                        roles_count = len(data.get("roles", []))
                        categories_count = len(data.get("categories", []))
                        channels_count = 0
                        for cat in data.get("categories", []):
                            channels_count += len(cat.get("channels", []))
                        channels_count += len(data.get("uncategorized_channels", []))
                        
                        meta = BUILTIN_METADATA.get(name.lower(), {})
                        
                        templates_list.append({
                            "name": name,
                            "display_name": meta.get("display_name", name.capitalize()),
                            "category": meta.get("category", "General"),
                            "description": meta.get("description", f"Pre-built template layout containing {channels_count} channels and {roles_count} roles."),
                            "icon": meta.get("icon", "fa-layer-group"),
                            "channels_count": channels_count,
                            "roles_count": roles_count
                        })
                    except Exception as e:
                        logger.error(f"Error parsing builtin template {filename}: {e}")
    return templates_list

@router.post("/api/templates/save")
async def save_template(request: TemplateSaveRequest, req_data: Request):
    auth_header = req_data.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(request.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in template save request.")
            
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(request.guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', request.name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid template name.")
        
    try:
        backup = bot_manager.backup_guild_layout(guild)
        templates_dir = utils.get_writeable_path("templates")
        os.makedirs(templates_dir, exist_ok=True)
        
        import json
        file_path = os.path.join(templates_dir, f"{safe_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(backup, f, indent=2)
            
        logger.info(f"Saved server layout template: '{safe_name}'")
        audit_log.log_action("admin", "BACKUP_ACTION", f"Saved current server layout as template '{request.name}'", request.guild_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error saving template {request.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/templates/upload")
async def upload_template(request: TemplateUploadRequest):
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', request.name)
    if not safe_name:
        raise HTTPException(status_code=400, detail="Invalid template name.")
        
    try:
        if not isinstance(request.data, dict) or (not request.data.get("categories") and not request.data.get("roles") and not request.data.get("channels")):
            raise HTTPException(status_code=400, detail="Invalid template format. Must contain roles, channels, or categories.")
            
        templates_dir = utils.get_writeable_path("templates")
        os.makedirs(templates_dir, exist_ok=True)
        
        import json
        file_path = os.path.join(templates_dir, f"{safe_name}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(request.data, f, indent=2)
            
        logger.info(f"Uploaded server layout template: '{safe_name}'")
        audit_log.log_action("admin", "BACKUP_ACTION", f"Uploaded third-party template '{request.name}'", "N/A")
        return {"status": "success"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error uploading template {request.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/templates/{name}/preview")
async def get_template_preview(name: str, guild_id: str, request: Request, handling: str = "keep"):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in template preview request.")
            
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    templates_dir = utils.get_writeable_path("templates")
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    if safe_name.lower() in BUILTIN_NAMES:
        file_path = os.path.join(templates_dir, "builtin", f"{safe_name}.json")
    else:
        file_path = os.path.join(templates_dir, f"{safe_name}.json")
        
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found.")
        
    try:
        import json
        with open(file_path, "r", encoding="utf-8") as f:
            template_data = json.load(f)
            
        from aegis.bot.restructuring import generate_template_preview
        preview = generate_template_preview(guild, template_data, handling)
        return preview
    except Exception as e:
        logger.error(f"Error loading template preview for {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/templates/apply")
async def apply_template(request: TemplateApplyRequest, req_data: Request):
    auth_header = req_data.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(request.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in template apply request.")
            
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(request.guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    templates_dir = utils.get_writeable_path("templates")
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', request.name)
    if safe_name.lower() in BUILTIN_NAMES:
        file_path = os.path.join(templates_dir, "builtin", f"{safe_name}.json")
    else:
        file_path = os.path.join(templates_dir, f"{safe_name}.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Template '{request.name}' not found.")
        
    try:
        import json
        with open(file_path, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
            
        success, errors = await bot_manager.restore_guild_layout(guild, backup_data, request.customizations, handling=request.handling)
        if success:
            audit_log.log_action("admin", "BACKUP_ACTION", f"Applied server layout template '{request.name}'", request.guild_id)
            return {"status": "success", "message": f"Template '{request.name}' applied successfully."}
        else:
            raise HTTPException(status_code=400, detail="Encountered errors during template deployment:\n" + "\n".join(errors))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error applying template {request.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/templates/{name}")
async def delete_template(name: str):
    templates_dir = utils.get_writeable_path("templates")
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    if safe_name.lower() in BUILTIN_NAMES:
        raise HTTPException(status_code=403, detail="Cannot delete built-in templates.")
        
    file_path = os.path.join(templates_dir, f"{safe_name}.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found.")
        
    try:
        os.remove(file_path)
        logger.info(f"Deleted custom template: '{safe_name}'")
        audit_log.log_action("dashboard", "BACKUP_ACTION", f"Deleted server layout template '{name}'")
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Error deleting template {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class PermissionsPutRequest(BaseModel):
    command_permissions: Dict[str, CommandPermissionRule]
    permission_roles: PermissionRoles

@router.get("/api/guilds/{guild_id}/permissions")
async def get_guild_permissions(guild_id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID.")
            
    guild_conf = utils.get_guild_config(guild_id)
    return {
        "command_permissions": guild_conf.get("command_permissions", {}),
        "permission_roles": guild_conf.get("permission_roles", {
            "admin_role_id": None,
            "moderator_role_id": None
        })
    }

@router.put("/api/guilds/{guild_id}/permissions")
async def update_guild_permissions(guild_id: str, payload: PermissionsPutRequest, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID.")
            
    guild_conf = utils.get_guild_config(guild_id)
    
    guild_conf["command_permissions"] = {
        k: v.model_dump() for k, v in payload.command_permissions.items()
    }
    guild_conf["permission_roles"] = payload.permission_roles.model_dump()
    
    utils.save_guild_config(guild_id, guild_conf)
    
    bot = bot_manager.get_bot()
    if bot and bot.is_ready():
        bot.config = utils.load_config()
        
    audit_log.log_action("admin", "CONFIG_CHANGE", f"Command permissions updated for server {guild_id}", guild_id)
    return {"status": "success"}

# Music Bot Endpoints

@router.get("/api/guilds/{guild_id}/music/status")
async def get_music_status(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if not player:
        raise HTTPException(status_code=404, detail="Guild/Player not found.")
    status = player.get_status()
    if "queue" in status:
        status["queue"] = status["queue"][:50]
    return status

@router.get("/api/guilds/{guild_id}/music/queue")
async def get_music_queue(guild_id: str, page: int = 1, limit: int = 20):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if not player:
        raise HTTPException(status_code=404, detail="Guild/Player not found.")
    
    if page < 1:
        page = 1
    if limit < 1:
        limit = 20
        
    queue = player.queue
    total_items = len(queue)
    start = (page - 1) * limit
    end = start + limit
    
    paginated_items = queue[start:end]
    total_pages = (total_items + limit - 1) // limit if total_items > 0 else 1
    
    return {
        "page": page,
        "limit": limit,
        "total_items": total_items,
        "total_pages": total_pages,
        "items": paginated_items
    }

@router.get("/api/guilds/{guild_id}/voice-channels")
async def get_voice_channels(guild_id: str):
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
    return [{"id": str(ch.id), "name": ch.name, "type": "voice"} for ch in guild.voice_channels]

@router.post("/api/guilds/{guild_id}/music/play")
async def music_play_endpoint(guild_id: str, request: MusicPlayRequest):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if not player:
        raise HTTPException(status_code=404, detail="Guild/Player not found.")
    
    if not player.voice_client or not player.voice_client.is_connected():
        guild = bot.get_guild(parse_id(guild_id, "guild_id"))
        if guild and guild.voice_channels:
            await player.join_channel(guild.voice_channels[0].id)
        else:
            raise HTTPException(status_code=400, detail="No voice channel available to join.")
            
    try:
        song = await player.add_to_queue(request.query)
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Played/queued song '{song['title']}'", guild_id)
        return {"status": "success", "song": song}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/guilds/{guild_id}/music/pause")
async def music_pause_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.pause():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Paused playback", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot pause playback.")

@router.post("/api/guilds/{guild_id}/music/resume")
async def music_resume_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.resume():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Resumed playback", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot resume playback.")

@router.post("/api/guilds/{guild_id}/music/skip")
async def music_skip_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.skip():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Skipped song", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot skip playback.")

@router.post("/api/guilds/{guild_id}/music/stop")
async def music_stop_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.stop():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Stopped playback", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot stop playback.")

@router.post("/api/guilds/{guild_id}/music/volume")
async def music_volume_endpoint(guild_id: str, request: MusicVolumeRequest):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player:
        vol = player.set_volume(request.volume)
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Adjusted volume to {int(vol*100)}%", guild_id)
        return {"status": "success", "volume": vol}
    raise HTTPException(status_code=400, detail="Player not active.")

@router.post("/api/guilds/{guild_id}/music/queue/shuffle")
async def music_shuffle_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and len(player.queue) > 1:
        import random
        random.shuffle(player.queue)
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Shuffled queue", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Queue is too small to shuffle.")

@router.delete("/api/guilds/{guild_id}/music/queue/{index}")
async def music_remove_queue_endpoint(guild_id: str, index: int):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and 0 <= index < len(player.queue):
        removed = player.queue.pop(index)
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Removed song '{removed['title']}' from queue", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Invalid queue index.")

@router.post("/api/guilds/{guild_id}/voice/join/{channel_id}")
async def voice_join_endpoint(guild_id: str, channel_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player:
        await player.join_channel(parse_id(channel_id, "channel_id"))
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Joined voice channel {channel_id}", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Player not found.")

@router.post("/api/guilds/{guild_id}/voice/leave")
async def voice_leave_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player:
        await player.leave_channel()
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Left voice channel", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Player not found.")

# Scheduled Messages Endpoints

@router.get("/api/scheduled-messages")
async def get_scheduled_messages(request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    scheduled = config.get("scheduled_messages", [])
    if session_role == "tenant" and session_guild_id:
        return [m for m in scheduled if m.get("guild_id") == session_guild_id]
    return scheduled

@router.post("/api/scheduled-messages")
async def create_scheduled_message(msg: ScheduledMessageModel, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(msg.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in scheduled message payload.")
            
    msg_data = msg.model_dump()
    if session_role == "tenant" and session_guild_id:
        msg_data["guild_id"] = session_guild_id
        
    config = utils.load_config()
    scheduled = config.setdefault("scheduled_messages", [])
    
    import uuid
    if not msg_data.get("id"):
        msg_data["id"] = "sched_" + uuid.uuid4().hex[:8]
        
    if not msg_data.get("next_run") and msg_data.get("datetime"):
        msg_data["next_run"] = msg_data["datetime"]
        
    scheduled.append(msg_data)
    config["scheduled_messages"] = scheduled
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "SCHEDULE_ACTION", f"Created scheduled message '{msg_data['id']}'", msg_data["guild_id"])
    return {"status": "success", "message": msg_data}

@router.delete("/api/scheduled-messages/{id}")
async def delete_scheduled_message(id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    scheduled = config.get("scheduled_messages", [])
    
    existing = None
    for m in scheduled:
        if m["id"] == id:
            existing = m
            break
            
    if not existing:
        raise HTTPException(status_code=404, detail="Scheduled message not found.")
        
    if session_role == "tenant" and session_guild_id:
        if existing.get("guild_id") != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot delete this scheduled message")
            
    new_scheduled = [m for m in scheduled if m["id"] != id]
    config["scheduled_messages"] = new_scheduled
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "SCHEDULE_ACTION", f"Deleted scheduled message '{id}'", existing.get("guild_id"))
    return {"status": "success"}

@router.patch("/api/scheduled-messages/{id}")
async def toggle_scheduled_message(id: str, request: Request, enabled: bool = Body(...)):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    scheduled = config.get("scheduled_messages", [])
    
    existing = None
    for m in scheduled:
        if m["id"] == id:
            existing = m
            break
            
    if not existing:
        raise HTTPException(status_code=404, detail="Scheduled message not found.")
        
    if session_role == "tenant" and session_guild_id:
        if existing.get("guild_id") != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot toggle this scheduled message")
            
    existing["enabled"] = enabled
    if enabled and existing.get("schedule_type") == "once" and not existing.get("next_run") and existing.get("datetime"):
        existing["next_run"] = existing["datetime"]
        
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "SCHEDULE_ACTION", f"Toggled scheduled message '{id}' (enabled={enabled})", existing.get("guild_id"))
    return {"status": "success"}

# Leveling Endpoints

@router.get("/api/guilds/{guild_id}/leaderboard")
async def get_leveling_leaderboard(guild_id: str):
    from aegis.bot.leveling import leveling_system
    bot = get_active_bot()
    
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    leaderboard = leveling_system.get_leaderboard(guild_id)
    full_leaderboard = []
    for item in leaderboard:
        member = guild.get_member(parse_id(item["user_id"], "user_id"))
        if not member:
            try:
                member = await bot.fetch_user(parse_id(item["user_id"], "user_id"))
            except Exception:
                member = None
                
        full_leaderboard.append({
            "user_id": item["user_id"],
            "xp": item["xp"],
            "level": item["level"],
            "messages": item["messages"],
            "rank": item["rank"],
            "username": member.name if member else f"User {item['user_id']}",
            "avatar_url": str(member.display_avatar.url) if member and hasattr(member, 'display_avatar') else "/static/bot_logo.png"
        })
    return full_leaderboard

@router.get("/api/guilds/{guild_id}/members/{member_id}/rank")
async def get_member_rank(guild_id: str, member_id: str):
    from aegis.bot.leveling import leveling_system
    rank = leveling_system.get_user_rank(guild_id, member_id)
    return rank

@router.get("/api/guilds/{guild_id}/leveling/config")
async def get_leveling_config(guild_id: str):
    config = utils.load_config()
    return utils.get_guild_leveling_settings(config, guild_id)

@router.post("/api/guilds/{guild_id}/leveling/config")
async def save_leveling_config(guild_id: str, request: LevelingConfigModel):
    config = utils.load_config()
    guild_configs = config.setdefault("guild_configs", {})
    guild_conf = guild_configs.setdefault(str(guild_id), {})
    guild_conf["leveling_settings"] = request.model_dump()
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "LEVELING_ACTION", "Updated leveling settings", guild_id)
    return {"status": "success"}

@router.post("/api/guilds/{guild_id}/leveling/reset")
async def reset_leveling_endpoint(guild_id: str):
    from aegis.bot.leveling import leveling_system
    leveling_system.reset_guild(guild_id)
    audit_log.log_action("dashboard", "LEVELING_ACTION", "Reset leveling data for server", guild_id)
    return {"status": "success"}

# Audit Log Endpoint

@router.get("/api/audit-log")
async def get_audit_log_endpoint(request: Request, category: Optional[str] = None, limit: int = 100, offset: int = 0):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        return audit_log.get_logs(category, limit, offset, guild_id=session_guild_id)
    return audit_log.get_logs(category, limit, offset)

# Auto-Responder Endpoints

@router.get("/api/auto-responders")
async def get_auto_responders(request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    auto_resp = config.get("auto_responders", [])
    
    if session_role == "tenant" and session_guild_id:
        return [item for item in auto_resp if item.get("guild_id") == session_guild_id]
    return auto_resp

@router.post("/api/auto-responders")
async def create_auto_responder(resp: AutoResponderModel, request: Request):
    if resp.trigger_type == "regex" and not utils.is_regex_safe(resp.trigger):
        raise HTTPException(status_code=400, detail="Invalid or potentially dangerous regular expression pattern.")
        
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(resp.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in auto-responder payload.")
            
    resp_data = resp.model_dump()
    if session_role == "tenant" and session_guild_id:
        resp_data["guild_id"] = session_guild_id
        
    config = utils.load_config()
    auto_resp = config.setdefault("auto_responders", [])
    
    import uuid
    if not resp_data.get("id"):
        resp_data["id"] = "trigger_" + uuid.uuid4().hex[:8]
        
    auto_resp.append(resp_data)
    config["auto_responders"] = auto_resp
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "AUTORESPONDER_ACTION", f"Created auto-responder for '{resp_data['trigger']}'", resp_data["guild_id"])
    return {"status": "success", "auto_responder": resp_data}

@router.put("/api/auto-responders/{id}")
async def update_auto_responder(id: str, resp: AutoResponderModel, request: Request):
    if resp.trigger_type == "regex" and not utils.is_regex_safe(resp.trigger):
        raise HTTPException(status_code=400, detail="Invalid or potentially dangerous regular expression pattern.")
        
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(resp.guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID in auto-responder payload.")
    
    config = utils.load_config()
    auto_resp = config.get("auto_responders", [])
    
    existing = None
    for item in auto_resp:
        if item["id"] == id:
            existing = item
            break
            
    if not existing:
        raise HTTPException(status_code=404, detail="Auto-responder not found.")
        
    if session_role == "tenant" and session_guild_id:
        if existing.get("guild_id") != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot modify this auto-responder")
            
    resp_data = resp.model_dump()
    resp_data["id"] = id
    if session_role == "tenant" and session_guild_id:
        resp_data["guild_id"] = session_guild_id
        
    for i, item in enumerate(auto_resp):
        if item["id"] == id:
            auto_resp[i] = resp_data
            break
            
    config["auto_responders"] = auto_resp
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "AUTORESPONDER_ACTION", f"Updated auto-responder '{id}' for '{resp_data['trigger']}'", resp_data["guild_id"])
    return {"status": "success", "auto_responder": resp_data}

@router.delete("/api/auto-responders/{id}")
async def delete_auto_responder(id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    auto_resp = config.get("auto_responders", [])
    
    existing = None
    for item in auto_resp:
        if item["id"] == id:
            existing = item
            break
            
    if not existing:
        raise HTTPException(status_code=404, detail="Auto-responder not found.")
        
    if session_role == "tenant" and session_guild_id:
        if existing.get("guild_id") != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: You cannot delete this auto-responder")
            
    new_auto_resp = [r for r in auto_resp if r["id"] != id]
    config["auto_responders"] = new_auto_resp
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "AUTORESPONDER_ACTION", f"Deleted auto-responder '{id}'", existing.get("guild_id"))
    return {"status": "success"}

class EmbedSendRequest(BaseModel):
    channel_id: str
    content: Optional[str] = None
    embed: dict

@router.post("/api/guilds/{guild_id}/embeds/send")
async def send_embed_message(guild_id: str, request: EmbedSendRequest):
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
    channel = guild.get_channel(parse_id(request.channel_id, "channel_id"))
    if not channel:
        raise HTTPException(status_code=404, detail="Channel not found.")
        
    try:
        embed = discord.Embed.from_dict(request.embed)
        await channel.send(content=request.content or None, embed=embed)
        audit_log.log_action("admin", "CONFIG_CHANGE", f"Sent custom embed message in #{channel.name}", guild_id)
        return {"status": "success"}
    except Exception as e:
        logger.error(f"Failed to send custom embed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/api/guilds/{guild_id}/embeds/presets")
async def get_custom_presets(guild_id: str, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID.")
            
    guild_conf = utils.get_guild_config(guild_id)
    return guild_conf.get("custom_embed_presets", {})

@router.post("/api/guilds/{guild_id}/embeds/presets/{preset_name}")
async def save_custom_preset(guild_id: str, preset_name: str, payload: dict, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID.")
            
    config = utils.load_config()
    guild_configs = config.setdefault("guild_configs", {})
    guild_conf = guild_configs.setdefault(str(guild_id), {})
    custom_presets = guild_conf.setdefault("custom_embed_presets", {})
    custom_presets[preset_name] = payload
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "CONFIG_CHANGE", f"Saved custom embed preset '{preset_name}'", guild_id)
    return {"status": "success"}

@router.delete("/api/guilds/{guild_id}/embeds/presets/{preset_name}")
async def delete_custom_preset(guild_id: str, preset_name: str, request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Mismatched guild ID.")
            
    config = utils.load_config()
    guild_configs = config.setdefault("guild_configs", {})
    guild_conf = guild_configs.get(str(guild_id), {})
    custom_presets = guild_conf.get("custom_embed_presets", {}) if guild_conf else None
    if not custom_presets or preset_name not in custom_presets:
        raise HTTPException(status_code=404, detail="Preset not found.")
        
    del custom_presets[preset_name]
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "CONFIG_CHANGE", f"Deleted custom embed preset '{preset_name}'", guild_id)
    return {"status": "success"}

# Live Web Console WebSocket Endpoint
@router.websocket("/ws/logs")
async def websocket_logs(websocket: WebSocket, token: Optional[str] = None):
    # Retrieve token if not automatically populated
    if not token:
        token = websocket.query_params.get("token")
        
    role = None
    guild_id = None
    if token and auth.validate_session(token):
        role = auth.get_session_role(token)
        guild_id = auth.get_session_guild_id(token)
        
    # Authenticate WebSocket if password is set (Tier 6.1)
    if os.environ.get("ADMIN_PASSWORD_HASH"):
        if not role or role not in ("admin", "tenant"):
            await websocket.close(code=1008)  # Rejects handshake with 1008 Close Frame
            return
            
    # Default to guest if setup not completed yet
    if not role:
        role = "guest"
        
    await websocket.accept()
    
    # Map role and guild_id to websocket attributes for emit filtering
    websocket.role = role
    websocket.guild_id = guild_id
    
    utils.active_websockets.add(websocket)
    
    # Send historical logs first (filtered by role/guild_id) (Gap 1)
    try:
        for entry in list(utils.log_history):
            if role == "admin":
                await websocket.send_text(entry)
            elif role == "tenant" and guild_id and str(guild_id) in entry:
                await websocket.send_text(entry)
            
        # Keep connection open. WebConsoleHandler will push new logs.
        while True:
            # We don't expect messages from client, but we must read to detect disconnect
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        utils.active_websockets.discard(websocket)


# ==========================================
# GIVEAWAY SYSTEM ENDPOINTS
# ==========================================

@router.get("/api/guilds/{guild_id}/giveaways")
async def get_giveaways(guild_id: str):
    giveaways = await utils.load_giveaways()
    
    bot = get_active_bot()
    guild = None
    if bot:
        try:
            guild = bot.get_guild(int(guild_id))
        except Exception:
            pass
            
    guild_gws = []
    for msg_id, gw in giveaways.items():
        if str(gw.get("guild_id")) == str(guild_id):
            resolved_winners = []
            for w in gw.get("winners", []):
                member = None
                if guild:
                    try:
                        member = guild.get_member(int(w))
                    except Exception:
                        pass
                if member:
                    resolved_winners.append(member.name)
                else:
                    if bot:
                        try:
                            user = bot.get_user(int(w))
                            if user:
                                resolved_winners.append(user.name)
                                continue
                        except Exception:
                            pass
                    resolved_winners.append(str(w))
            
            guild_gws.append({
                "message_id": msg_id,
                "channel_id": gw.get("channel_id"),
                "prize": gw.get("prize"),
                "winners_count": gw.get("winners_count"),
                "end_time": gw.get("end_time"),
                "entrants_count": len(gw.get("entrants", [])),
                "winners": resolved_winners,
                "ended": gw.get("ended", False),
                "host_id": gw.get("host_id"),
                "host_name": gw.get("host_name", "Aegis Suite")
            })
            
    guild_gws.sort(key=lambda x: (x["ended"], -x["end_time"]))
    return guild_gws

@router.post("/api/guilds/{guild_id}/giveaways/start")
async def start_giveaway_endpoint(guild_id: str, request: GiveawayStartRequest):
    bot = get_active_bot()
        
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    channel = guild.get_channel(parse_id(request.channel_id, "channel_id"))
    if not channel:
        raise HTTPException(status_code=404, detail="Target channel not found.")
        
    duration_secs = bot_manager.parse_duration(request.duration)
    if not duration_secs:
        raise HTTPException(status_code=400, detail="Invalid duration format. Use: 30s, 5m, 2h, 1d")
        
    try:
        msg_id = await bot_manager.start_giveaway_bot(
            channel,
            request.prize,
            request.winners_count,
            duration_secs,
            bot.user.id,
            host_name_custom=request.host
        )
        audit_log.log_action("dashboard", "GIVEAWAY_ACTION", f"Started giveaway for '{request.prize}' in #{channel.name}", guild_id)
        return {"status": "success", "message_id": msg_id}
    except Exception as e:
        logger.error(f"Failed to start giveaway from dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/guilds/{guild_id}/giveaways/{message_id}/end")
async def end_giveaway_endpoint(guild_id: str, message_id: str):
    bot = get_active_bot()
        
    async with utils.giveaways_lock:
        giveaways = await utils.load_giveaways()
        if message_id not in giveaways:
            raise HTTPException(status_code=404, detail="Giveaway not found in records.")
            
        gw = giveaways[message_id]
        if gw.get("ended", False):
            raise HTTPException(status_code=400, detail="This giveaway has already ended.")
            
        guild = bot.get_guild(parse_id(guild_id, "guild_id"))
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found.")
            
        channel = guild.get_channel(parse_id(gw["channel_id"], "channel_id"))
        if not channel:
            raise HTTPException(status_code=404, detail="Giveaway channel not found.")
            
        try:
            message = await channel.fetch_message(parse_id(message_id, "message_id"))
            await bot.end_giveaway_action(message, gw, giveaways)
            await utils.save_giveaways(giveaways)
            audit_log.log_action("dashboard", "GIVEAWAY_ACTION", f"Force ended giveaway '{gw.get('prize')}' early", guild_id)
            return {"status": "success"}
        except Exception as e:
            logger.error(f"Failed to force end giveaway: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/guilds/{guild_id}/giveaways/{message_id}/reroll")
async def reroll_giveaway_endpoint(guild_id: str, message_id: str):
    bot = get_active_bot()
        
    async with utils.giveaways_lock:
        giveaways = await utils.load_giveaways()
        if message_id not in giveaways:
            raise HTTPException(status_code=404, detail="Giveaway not found in records.")
            
        gw = giveaways[message_id]
        if not gw.get("ended", False):
            raise HTTPException(status_code=400, detail="This giveaway is still active. End it first.")
            
        guild = bot.get_guild(parse_id(guild_id, "guild_id"))
        if not guild:
            raise HTTPException(status_code=404, detail="Guild not found.")
            
        channel = guild.get_channel(parse_id(gw["channel_id"], "channel_id"))
        if not channel:
            raise HTTPException(status_code=404, detail="Giveaway channel not found.")
            
        try:
            res = await bot_manager.reroll_giveaway_bot(channel, parse_id(message_id, "message_id"))
            if res == "success":
                audit_log.log_action("dashboard", "GIVEAWAY_ACTION", f"Rerolled winners for giveaway '{gw.get('prize')}'", guild_id)
                return {"status": "success"}
            else:
                raise HTTPException(status_code=400, detail=res)
        except Exception as e:
            logger.error(f"Failed to reroll giveaway: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@router.delete("/api/guilds/{guild_id}/giveaways/{message_id}")
async def delete_giveaway_endpoint(guild_id: str, message_id: str):
    async with utils.giveaways_lock:
        giveaways = await utils.load_giveaways()
        if message_id not in giveaways:
            raise HTTPException(status_code=404, detail="Giveaway not found in records.")
            
        gw = giveaways[message_id]
        del giveaways[message_id]
        await utils.save_giveaways(giveaways)
        
    bot = bot_manager.get_bot()
    if bot:
        try:
            guild = bot.get_guild(parse_id(guild_id, "guild_id"))
            if guild:
                channel = guild.get_channel(parse_id(gw.get("channel_id"), "channel_id"))
                if channel:
                    msg = await channel.fetch_message(parse_id(message_id, "message_id"))
                    await msg.delete()
        except (discord.NotFound, discord.Forbidden) as e:
            logger.warning(f"Did not delete Discord message for deleted giveaway {message_id}: {e}")
        except Exception as e:
            logger.error(f"Failed to delete Discord message for deleted giveaway {message_id}: {e}")
            
    audit_log.log_action("dashboard", "GIVEAWAY_ACTION", f"Deleted giveaway log ID '{message_id}'", guild_id)
    return {"status": "success"}


# Serve Frontend

# Mount static files folder
# app.mount static handled in app.py

# root route served by wizard_router

def init_default_templates():
    import json
    templates_dir = utils.get_writeable_path("templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    # 1. Gaming Template
    gaming_path = os.path.join(templates_dir, "gaming.json")
    if not os.path.exists(gaming_path):
        gaming_tpl = {
            "name": "gaming",
            "verification_level": "medium",
            "explicit_content_filter": "all_members",
            "roles": [
                {"name": "Admin", "color": 15671396, "hoist": True, "permissions": 8, "position": 3},
                {"name": "Moderator", "color": 3900150, "hoist": True, "permissions": 268435486, "position": 2},
                {"name": "Member", "color": 1096065, "hoist": False, "permissions": 104324673, "position": 1}
            ],
            "categories": [
                {
                    "name": "🏆 INFORMATION",
                    "position": 1,
                    "overwrites": [],
                    "channels": [
                        {"name": "welcome", "type": "text", "position": 1, "overwrites": [{"target_type": "role", "target_name": "@everyone", "allow": 0, "deny": 2048}]},
                        {"name": "rules", "type": "text", "position": 2, "overwrites": [{"target_type": "role", "target_name": "@everyone", "allow": 0, "deny": 2048}]},
                        {"name": "announcements", "type": "text", "position": 3, "overwrites": [{"target_type": "role", "target_name": "@everyone", "allow": 0, "deny": 2048}]}
                    ]
                },
                {
                    "name": "💬 TEXT CHANNELS",
                    "position": 2,
                    "overwrites": [],
                    "channels": [
                        {"name": "general", "type": "text", "position": 1, "overwrites": []},
                        {"name": "clips-and-media", "type": "text", "position": 2, "overwrites": []},
                        {"name": "looking-for-group", "type": "text", "position": 3, "overwrites": []}
                    ]
                },
                {
                    "name": "🔊 VOICE CHANNELS",
                    "position": 3,
                    "overwrites": [],
                    "channels": [
                        {"name": "Lobby 1", "type": "voice", "position": 1, "overwrites": []},
                        {"name": "Lobby 2", "type": "voice", "position": 2, "overwrites": []},
                        {"name": "Gaming Voice 1", "type": "voice", "position": 3, "overwrites": []}
                    ]
                }
            ],
            "uncategorized_channels": []
        }
        with open(gaming_path, "w", encoding="utf-8") as f:
            json.dump(gaming_tpl, f, indent=2)
            
    # 2. Community Template
    community_path = os.path.join(templates_dir, "community.json")
    if not os.path.exists(community_path):
        community_tpl = {
            "name": "community",
            "verification_level": "low",
            "explicit_content_filter": "all_members",
            "roles": [
                {"name": "Staff", "color": 3900150, "hoist": True, "permissions": 268435486, "position": 3},
                {"name": "VIP", "color": 15485081, "hoist": True, "permissions": 104324673, "position": 2},
                {"name": "Member", "color": 9741240, "hoist": False, "permissions": 104324673, "position": 1}
            ],
            "categories": [
                {
                    "name": "📢 WELCOME & INFO",
                    "position": 1,
                    "overwrites": [],
                    "channels": [
                        {"name": "welcome", "type": "text", "position": 1, "overwrites": [{"target_type": "role", "target_name": "@everyone", "allow": 0, "deny": 2048}]},
                        {"name": "rules-and-info", "type": "text", "position": 2, "overwrites": [{"target_type": "role", "target_name": "@everyone", "allow": 0, "deny": 2048}]}
                    ]
                },
                {
                    "name": "💬 DISCUSSION",
                    "position": 2,
                    "overwrites": [],
                    "channels": [
                        {"name": "general-chat", "type": "text", "position": 1, "overwrites": []},
                        {"name": "off-topic", "type": "text", "position": 2, "overwrites": []},
                        {"name": "memes-and-media", "type": "text", "position": 3, "overwrites": []}
                    ]
                }
            ],
            "uncategorized_channels": []
        }
        with open(community_path, "w", encoding="utf-8") as f:
            json.dump(community_tpl, f, indent=2)

# Deprecated startup event removed (lifespan manager is used instead)
