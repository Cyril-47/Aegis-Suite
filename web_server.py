import logging
import os
import asyncio
import discord
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Body, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, HTMLResponse
from pydantic import BaseModel, Field
from typing import List, Optional
import utils
import bot_manager
import auth
import audit_log

# Configure logging
logger = logging.getLogger("WebServer")

from contextlib import asynccontextmanager
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
    bot = bot_manager.get_bot()
    return bot

# Lifespan Context Manager (Tier 4.6 & 4.7 & 8.6)
def _bootstrap_hosting_mode_from_env() -> None:
    """One-time AEGIS_HOSTING_MODE bootstrap for headless cloud deploys.

    Honored only when ``config.json`` does not already carry a valid
    ``hosting_mode``. A pre-existing persisted value is never overwritten so
    a stale Railway / Render env var cannot silently stomp an explicit
    Maintainer choice (Requirement 6.3). Invalid env values are logged at
    WARNING level and ignored (Requirement 6.2). Extracted as a module-level
    helper so tests can call it directly without spinning up uvicorn.
    """
    valid = ("local_pc", "cloud")
    config = utils.load_config()
    if config.get("hosting_mode") in valid:
        # Persisted choice already exists — do not consult the env var at all.
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
    # Re-read under the config lock so a concurrent admin PUT that lands
    # during startup wins. We only write when the persisted value is still
    # empty / invalid, preserving Requirement 6.3.
    with utils.config_lock:
        cfg = utils.load_config()
        if cfg.get("hosting_mode") in valid:
            return
        cfg["hosting_mode"] = env_val
        utils.save_config(cfg)
    logger.info(f"Hosting mode bootstrapped from AEGIS_HOSTING_MODE: {env_val}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    utils.setup_logging()
    logger.info("FastAPI Web Server starting up...")
    init_default_templates()
    
    # Start the rate-limiter GC task (Tier 8.6)
    gc_task = asyncio.create_task(utils.prune_stale_rate_limiters())
    
    # Hosting Mode env-var bootstrap (Requirement 6) — must run before the
    # bot service starts so config.json carries the correct mode by the time
    # the bot is connecting.
    try:
        _bootstrap_hosting_mode_from_env()
    except Exception as e:
        logger.error(f"Hosting mode bootstrap failed: {e}")

    # Try starting the bot if token is already configured
    config = utils.load_config()
    token = utils.get_bot_token(config)
    if token:
        logger.info("Saved bot token found. Starting Discord bot on startup...")
        try:
            await bot_manager.start_bot_service(token)
        except Exception as e:
            logger.error(f"Failed to start bot on startup: {e}")
    else:
        logger.error("DISCORD_BOT_TOKEN is missing from environment. Set it in the server's .env. Bot will not start.")
        
    yield
    
    # Shutdown actions (Graceful Shutdown)
    logger.info("FastAPI Web Server shutting down...")
    
    # Cancel rate-limiter GC task
    gc_task.cancel()
    try:
        await gc_task
    except asyncio.CancelledError:
        pass
        
    bot = bot_manager.get_bot()
    if bot:
        logger.info("Stopping Discord bot on shutdown...")
        try:
            await bot_manager.stop_bot_service()
        except Exception as e:
            logger.error(f"Failed to stop bot on shutdown: {e}")

app = FastAPI(title="Discord Server Optimizer Dashboard", lifespan=lifespan)

@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
        
    # Block endpoints if admin password setup is incomplete (Tier 2.2 / Tier 6.1)
    if not os.environ.get("ADMIN_PASSWORD_HASH"):
        if path not in ["/api/auth/setup-status", "/api/auth/setup", "/api/status", "/api/auth/login"]:
            return JSONResponse(status_code=403, content={"detail": "Forbidden: Complete password setup first."})
        return await call_next(request)
        
    # Allow status and auth endpoints without authentication
    if path == "/api/status" or path.startswith("/api/auth/"):
        return await call_next(request)
        
    auth_header = request.headers.get("Authorization")
    token = None
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        
    if not token or not auth.validate_session(token):
        return JSONResponse(status_code=401, content={"detail": "Unauthorized: Invalid or missing token"})
        
    # Enforce guild-level access restriction for tenant sessions (Tier 5.5 / Tier 6.6 / Tier 8.2)
    session_role = auth.get_session_role(token)
    if session_role == "tenant":
        session_guild_id = auth.get_session_guild_id(token)
        
        # Enforce Sliding-Window Rate Limiting (Tier 8.2)
        if not utils.check_guild_rate_limit(session_guild_id):
            return JSONResponse(status_code=429, content={"detail": "Too many requests. Rate limit is 60 requests per minute."})
            
        # Strictly block global admin routes (Tier 8.2)
        if path in ["/api/bot/start", "/api/bot/stop"] or (path.startswith("/api/templates/") and request.method == "DELETE"):
            return JSONResponse(status_code=403, content={"detail": "Forbidden: Tenant users cannot access global administrative endpoints"})
            
        import re as pyre
        guild_match = pyre.search(r"/api/guilds/(\d+)", path)
        if guild_match:
            requested_guild_id = guild_match.group(1)
            if requested_guild_id != session_guild_id:
                return JSONResponse(status_code=403, content={"detail": "Forbidden: Session not authorized for this server"})
        
    return await call_next(request)



# Ensure static folder exists in development
if not getattr(sys, 'frozen', False):
    os.makedirs(utils.get_writeable_path("static"), exist_ok=True)

from typing import List, Optional, Dict, Any, Literal

# Pydantic models for configuration
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

class ConfigModel(BaseModel):
    client_id: str
    welcome_settings: WelcomeSettingsModel
    automod_settings: AutomodSettingsModel
    ticket_settings: Optional[TicketSettingsModel] = None
    custom_commands: Optional[dict] = Field(default_factory=dict)
    admin_password_hash: Optional[str] = ""
    command_permissions: Dict[str, CommandPermissionRule] = Field(default_factory=dict)
    permission_roles: PermissionRoles = Field(default_factory=PermissionRoles)

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
    confirm: bool = False
    customizations: Optional[dict] = None

class PermissionsPutRequest(BaseModel):
    command_permissions: Dict[str, CommandPermissionRule]
    permission_roles: PermissionRoles

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

class LevelingConfigModel(BaseModel):
    enabled: bool
    xp_per_message: int
    xp_cooldown_seconds: int
    level_up_channel: Optional[str] = None
    level_roles: dict
    ignored_channels: List[str] = Field(default_factory=list)
    ignored_roles: List[str] = Field(default_factory=list)

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

# API Endpoints

@app.get("/api/auth/setup-status")
async def get_auth_setup_status():
    has_hash = bool(os.environ.get("ADMIN_PASSWORD_HASH"))
    return {"setup": has_hash}

@app.post("/api/auth/setup")
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

@app.post("/api/auth/login")
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

@app.post("/api/auth/logout")
async def logout_auth(request: Request):
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ")[1]
        auth.destroy_session(token)
        audit_log.log_action("system", "BOT_CONTROL", "Admin logged out")
    return {"status": "success"}

@app.get("/api/stats")
async def get_stats():
    return bot_manager.get_bot_stats()

@app.get("/api/status")
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

@app.get("/api/hosting-mode")
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

@app.put("/api/hosting-mode")
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

@app.get("/api/diagnostics/package")
@app.get("/api/diagnostics/download")
async def download_diagnostics_legacy(request: Request):
    from aegis.core.paths import Paths
    from aegis.diagnostics.packager import generate_package
    import time

    # Construct a core-like object for generate_package
    class SimpleCore:
        def __init__(self):
            self.paths = Paths()
            self.paths.ensure()
            self.db = None
            self._start_time = time.time()
            
            class State:
                current_state = "running"
                reason = None
            self.state = State()
            
            class Config:
                def as_dict(self):
                    import utils
                    return utils.load_config()
            self.config = Config()
            
    core = SimpleCore()
    try:
        zip_path = generate_package(core)
        return FileResponse(
            zip_path,
            media_type="application/zip",
            filename=zip_path.name
        )
    except Exception as e:
        logger.exception("Failed to generate diagnostics package")
        raise HTTPException(status_code=500, detail=f"Failed to generate diagnostics package: {e}")

@app.get("/api/config")
async def get_config(request: Request):
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
        
    if session_role == "tenant":
        # Resolve guild-specific configs (Tier 5.6)
        guild_conf = utils.get_guild_config(session_guild_id)
        config["welcome_settings"] = guild_conf["welcome_settings"]
        config["automod_settings"] = guild_conf["automod_settings"]
        config["ticket_settings"] = guild_conf["ticket_settings"]
        config["custom_commands"] = guild_conf["custom_commands"]
        config["command_permissions"] = guild_conf.get("command_permissions", {})
        config["permission_roles"] = guild_conf.get("permission_roles", {
            "admin_role_id": None,
            "moderator_role_id": None
        })
        
    return config

@app.post("/api/config")
async def save_config(config_data: ConfigModel, request: Request):
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
            
        # Dynamically update the running bot settings if running
        bot = bot_manager.get_bot()
        if bot and bot.is_ready():
            bot.config = current_config
            logger.info("Bot configuration updated in-memory.")
            
        audit_log.log_action("admin", "CONFIG_CHANGE", "Dashboard configuration saved")
        return {"status": "success", "token_changed": False}
        
    else:
        # Tenant administrator configuration saving (Tier 5.6)
        guild_conf = utils.get_guild_config(session_guild_id)
        guild_conf["welcome_settings"] = new_data["welcome_settings"]
        guild_conf["automod_settings"] = new_data["automod_settings"]
        if new_data.get("ticket_settings"):
            guild_conf["ticket_settings"] = new_data["ticket_settings"]
        if new_data.get("custom_commands"):
            guild_conf["custom_commands"] = new_data["custom_commands"]
        if "command_permissions" in new_data:
            guild_conf["command_permissions"] = new_data["command_permissions"]
        if "permission_roles" in new_data:
            guild_conf["permission_roles"] = new_data["permission_roles"]
            
        utils.save_guild_config(session_guild_id, guild_conf)
        
        # Update running bot references
        bot = bot_manager.get_bot()
        if bot and bot.is_ready():
            bot.config = utils.load_config()
            
        audit_log.log_action("admin", "CONFIG_CHANGE", f"Dashboard configuration saved for server {session_guild_id}", session_guild_id)
        return {"status": "success", "token_changed": False}

@app.get("/api/guilds")
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

@app.get("/api/guilds/{guild_id}/audit")
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

@app.post("/api/guilds/{guild_id}/optimize")
async def optimize_guild(guild_id: str, request: OptimizeRequest):
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

@app.get("/api/guilds/{guild_id}/channels")
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

@app.get("/api/commands")
async def get_commands(request: Request):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    config = utils.load_config()
    if session_role == "tenant" and session_guild_id:
        return utils.get_guild_custom_commands(config, session_guild_id)
    return config.get("custom_commands", {})

@app.post("/api/commands")
async def save_commands(request: Request, commands: dict = Body(...)):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        guild_conf = utils.get_guild_config(session_guild_id)
        guild_conf["custom_commands"] = commands
        utils.save_guild_config(session_guild_id, guild_conf)
        
        bot = bot_manager.get_bot()
        if bot and bot.is_ready():
            bot.config = utils.load_config()
            
        audit_log.log_action("admin", "CONFIG_CHANGE", f"Configured {len(commands)} custom commands for server {session_guild_id}", session_guild_id)
        return {"status": "success"}
        
    config = utils.load_config()
    config["custom_commands"] = commands
    success = utils.save_config(config)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save custom commands.")
    
    bot = bot_manager.get_bot()
    if bot and bot.is_ready():
        bot.config = config
        
    audit_log.log_action("admin", "CONFIG_CHANGE", f"Configured {len(commands)} custom commands")
    return {"status": "success"}

@app.post("/api/tickets/setup")
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

@app.get("/api/guilds/{guild_id}/roles")
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

@app.post("/api/guilds/{guild_id}/roles")
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

@app.delete("/api/guilds/{guild_id}/roles/{role_id}")
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

@app.post("/api/roles/panel/deploy")
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

@app.get("/api/guilds/{guild_id}/backup")
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

@app.post("/api/guilds/{guild_id}/restore")
async def restore_backup(guild_id: str, backup_data: dict = Body(...)):
    bot = get_active_bot()
        
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
        
    try:
        success = await bot_manager.restore_guild_layout(guild, backup_data)
        if success:
            audit_log.log_action("admin", "BACKUP_ACTION", "Restored server structure from backup file", guild_id)
            return {"status": "success", "message": "Server structure restored successfully."}
        else:
            raise HTTPException(status_code=500, detail="Failed to restore server structure.")
    except Exception as e:
        logger.error(f"Error restoring guild {guild_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/templates")
async def get_templates():
    templates_dir = utils.get_writeable_path("templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    templates_list = []
    for filename in os.listdir(templates_dir):
        if filename.endswith(".json"):
            name = filename[:-5]
            templates_list.append({
                "name": name
            })
    return templates_list

@app.post("/api/templates/save")
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

@app.get("/api/templates/{name}/preview")
async def preview_template(name: str, guild_id: str, req_data: Request):
    auth_header = req_data.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    if session_role == "tenant" and session_guild_id:
        if str(guild_id) != session_guild_id:
            raise HTTPException(status_code=403, detail="Forbidden: Session not authorized for this server")
            
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")

    templates_dir = utils.get_writeable_path("templates")
    import re
    import json
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
    file_path = os.path.join(templates_dir, f"{safe_name}.json")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Template '{name}' not found.")

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            template_data = json.load(f)
            
        roles_to_create = []
        roles_to_skip = []
        for r in template_data.get("roles", []):
            role_name = r["name"]
            existing = discord.utils.get(guild.roles, name=role_name)
            if existing:
                roles_to_skip.append(role_name)
            else:
                roles_to_create.append(role_name)

        categories_to_create = []
        categories_to_skip = []
        channels_to_create = []
        channels_to_skip = []

        for cat in template_data.get("categories", []):
            cat_name = cat["name"]
            existing_cat = discord.utils.get(guild.categories, name=cat_name)
            if existing_cat:
                categories_to_skip.append(cat_name)
            else:
                categories_to_create.append(cat_name)

            for ch in cat.get("channels", []):
                ch_name = ch["name"]
                ch_type = ch["type"]
                existing_ch = None
                if ch_type == "text":
                    existing_ch = discord.utils.get(guild.text_channels, name=ch_name)
                elif ch_type == "voice":
                    existing_ch = discord.utils.get(guild.voice_channels, name=ch_name)

                if existing_ch:
                    channels_to_skip.append(f"{ch_name} ({ch_type})")
                else:
                    channels_to_create.append(f"{ch_name} ({ch_type})")

        for ch in template_data.get("uncategorized_channels", []):
            ch_name = ch["name"]
            ch_type = ch["type"]
            existing_ch = None
            if ch_type == "text":
                existing_ch = discord.utils.get(guild.text_channels, name=ch_name)
            elif ch_type == "voice":
                existing_ch = discord.utils.get(guild.voice_channels, name=ch_name)

            if existing_ch:
                channels_to_skip.append(f"{ch_name} ({ch_type})")
            else:
                channels_to_create.append(f"{ch_name} ({ch_type})")

        return {
            "template_name": name,
            "summary": {
                "categories_to_create": categories_to_create,
                "categories_to_skip": categories_to_skip,
                "channels_to_create": channels_to_create,
                "channels_to_skip": channels_to_skip,
                "roles_to_create": roles_to_create,
                "roles_to_skip": roles_to_skip
            },
            "template_data": template_data
        }
    except Exception as e:
        logger.error(f"Error previewing template {name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/templates/apply")
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
        
    if not request.confirm:
        raise HTTPException(status_code=400, detail="Template deployment requires explicit confirmation.")
        
    templates_dir = utils.get_writeable_path("templates")
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', request.name)
    file_path = os.path.join(templates_dir, f"{safe_name}.json")
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Template '{request.name}' not found.")
        
    try:
        import json
        with open(file_path, "r", encoding="utf-8") as f:
            backup_data = json.load(f)
            
        if request.customizations:
            disabled = request.customizations.get("disabled_elements", [])
            renames = request.customizations.get("renames", {})

            # Mutate categories and channels
            new_categories = []
            for cat in backup_data.get("categories", []):
                if cat["name"] in disabled:
                    continue
                if cat["name"] in renames:
                    cat["name"] = renames[cat["name"]]
                
                new_channels = []
                for ch in cat.get("channels", []):
                    if ch["name"] in disabled:
                        continue
                    if ch["name"] in renames:
                        ch["name"] = renames[ch["name"]]
                    new_channels.append(ch)
                cat["channels"] = new_channels
                new_categories.append(cat)
            backup_data["categories"] = new_categories

            # Mutate uncategorized
            new_uncat = []
            for ch in backup_data.get("uncategorized_channels", []):
                if ch["name"] in disabled:
                    continue
                if ch["name"] in renames:
                    ch["name"] = renames[ch["name"]]
                new_uncat.append(ch)
            backup_data["uncategorized_channels"] = new_uncat

            # Mutate roles
            new_roles = []
            for role in backup_data.get("roles", []):
                if role["name"] in disabled:
                    continue
                if role["name"] in renames:
                    role["name"] = renames[role["name"]]
                new_roles.append(role)
            backup_data["roles"] = new_roles
            
        success = await bot_manager.restore_guild_layout(guild, backup_data)
        if success:
            audit_log.log_action("admin", "BACKUP_ACTION", f"Applied server layout template '{request.name}'", request.guild_id)
            return {"status": "success", "message": f"Template '{request.name}' applied successfully."}
        else:
            raise HTTPException(status_code=500, detail="Failed to apply template layout.")
    except Exception as e:
        logger.error(f"Error applying template {request.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/api/templates/{name}")
async def delete_template(name: str):
    templates_dir = utils.get_writeable_path("templates")
    import re
    safe_name = re.sub(r'[^a-zA-Z0-9_-]', '', name)
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

@app.get("/api/guilds/{guild_id}/permissions")
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

@app.put("/api/guilds/{guild_id}/permissions")
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
    
    # Update running bot configuration references
    bot = bot_manager.get_bot()
    if bot and bot.is_ready():
        bot.config = utils.load_config()
        
    audit_log.log_action("admin", "CONFIG_CHANGE", f"Command permissions updated for server {guild_id}", guild_id)
    return {"status": "success"}

# Music Bot Endpoints

@app.get("/api/guilds/{guild_id}/music/status")
async def get_music_status(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if not player:
        raise HTTPException(status_code=404, detail="Guild/Player not found.")
    return player.get_status()

@app.get("/api/guilds/{guild_id}/voice-channels")
async def get_voice_channels(guild_id: str):
    bot = get_active_bot()
    guild = bot.get_guild(parse_id(guild_id, "guild_id"))
    if not guild:
        raise HTTPException(status_code=404, detail="Guild not found.")
    return [{"id": str(ch.id), "name": ch.name, "type": "voice"} for ch in guild.voice_channels]

@app.post("/api/guilds/{guild_id}/music/play")
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

@app.post("/api/guilds/{guild_id}/music/pause")
async def music_pause_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.pause():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Paused playback", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot pause playback.")

@app.post("/api/guilds/{guild_id}/music/resume")
async def music_resume_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.resume():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Resumed playback", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot resume playback.")

@app.post("/api/guilds/{guild_id}/music/skip")
async def music_skip_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.skip():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Skipped song", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot skip playback.")

@app.post("/api/guilds/{guild_id}/music/stop")
async def music_stop_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and player.stop():
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Stopped playback", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Cannot stop playback.")

@app.post("/api/guilds/{guild_id}/music/volume")
async def music_volume_endpoint(guild_id: str, request: MusicVolumeRequest):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player:
        vol = player.set_volume(request.volume)
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Adjusted volume to {int(vol*100)}%", guild_id)
        return {"status": "success", "volume": vol}
    raise HTTPException(status_code=400, detail="Player not active.")

@app.post("/api/guilds/{guild_id}/music/queue/shuffle")
async def music_shuffle_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and len(player.queue) > 1:
        import random
        random.shuffle(player.queue)
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Shuffled queue", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Queue is too small to shuffle.")

@app.delete("/api/guilds/{guild_id}/music/queue/{index}")
async def music_remove_queue_endpoint(guild_id: str, index: int):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player and 0 <= index < len(player.queue):
        removed = player.queue.pop(index)
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Removed song '{removed['title']}' from queue", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=400, detail="Invalid queue index.")

@app.post("/api/guilds/{guild_id}/voice/join/{channel_id}")
async def voice_join_endpoint(guild_id: str, channel_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player:
        await player.join_channel(parse_id(channel_id, "channel_id"))
        audit_log.log_action("dashboard", "MUSIC_ACTION", f"Joined voice channel {channel_id}", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Player not found.")

@app.post("/api/guilds/{guild_id}/voice/leave")
async def voice_leave_endpoint(guild_id: str):
    bot = get_active_bot()
    player = bot.get_music_player(parse_id(guild_id, "guild_id"))
    if player:
        await player.leave_channel()
        audit_log.log_action("dashboard", "MUSIC_ACTION", "Left voice channel", guild_id)
        return {"status": "success"}
    raise HTTPException(status_code=404, detail="Player not found.")

# Scheduled Messages Endpoints

@app.get("/api/scheduled-messages")
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

@app.post("/api/scheduled-messages")
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

@app.delete("/api/scheduled-messages/{id}")
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

@app.patch("/api/scheduled-messages/{id}")
async def toggle_scheduled_message(id: str, request: Request, enabled: bool = Body(..., embed=True)):
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

@app.get("/api/guilds/{guild_id}/leaderboard")
async def get_leveling_leaderboard(guild_id: str):
    from leveling import leveling_system
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
            "avatar_url": str(member.display_avatar.url) if member and hasattr(member, 'display_avatar') else "https://discord.com/assets/c09c2a688b139c15814e578d0554c9a6.png"
        })
    return full_leaderboard

@app.get("/api/guilds/{guild_id}/members/{member_id}/rank")
async def get_member_rank(guild_id: str, member_id: str):
    from leveling import leveling_system
    rank = leveling_system.get_user_rank(guild_id, member_id)
    return rank

@app.get("/api/guilds/{guild_id}/leveling/config")
async def get_leveling_config(guild_id: str):
    config = utils.load_config()
    return config.get("leveling_settings", {})

@app.post("/api/guilds/{guild_id}/leveling/config")
async def save_leveling_config(guild_id: str, request: LevelingConfigModel):
    config = utils.load_config()
    config["leveling_settings"] = request.model_dump()
    utils.save_config(config)
    
    bot = bot_manager.get_bot()
    if bot:
        bot.config = config
        
    audit_log.log_action("dashboard", "LEVELING_ACTION", "Updated leveling settings", guild_id)
    return {"status": "success"}

@app.post("/api/guilds/{guild_id}/leveling/reset")
async def reset_leveling_endpoint(guild_id: str):
    from leveling import leveling_system
    leveling_system.reset_guild(guild_id)
    audit_log.log_action("dashboard", "LEVELING_ACTION", "Reset leveling data for server", guild_id)
    return {"status": "success"}

# Audit Log Endpoint

@app.get("/api/audit-log")
async def get_audit_log_endpoint(request: Request, category: Optional[str] = None, limit: int = 100, offset: int = 0):
    auth_header = request.headers.get("Authorization")
    token = auth_header.split(" ")[1] if auth_header and auth_header.startswith("Bearer ") else ""
    session_guild_id = auth.get_session_guild_id(token)
    session_role = auth.get_session_role(token)
    
    if session_role == "tenant" and session_guild_id:
        return audit_log.get_logs(category, limit, offset, guild_id=session_guild_id)
    return audit_log.get_logs(category, limit, offset)

# Auto-Responder Endpoints

@app.get("/api/auto-responders")
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

@app.post("/api/auto-responders")
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

@app.put("/api/auto-responders/{id}")
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

@app.delete("/api/auto-responders/{id}")
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

@app.post("/api/guilds/{guild_id}/embeds/send")
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

# Live Web Console WebSocket Endpoint
@app.websocket("/ws/logs")
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

@app.get("/api/guilds/{guild_id}/giveaways")
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
                "host_id": gw.get("host_id")
            })
            
    guild_gws.sort(key=lambda x: (x["ended"], -x["end_time"]))
    return guild_gws

@app.post("/api/guilds/{guild_id}/giveaways/start")
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
            bot.user.id
        )
        audit_log.log_action("dashboard", "GIVEAWAY_ACTION", f"Started giveaway for '{request.prize}' in #{channel.name}", guild_id)
        return {"status": "success", "message_id": msg_id}
    except Exception as e:
        logger.error(f"Failed to start giveaway from dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/guilds/{guild_id}/giveaways/{message_id}/end")
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

@app.post("/api/guilds/{guild_id}/giveaways/{message_id}/reroll")
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

@app.delete("/api/guilds/{guild_id}/giveaways/{message_id}")
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
app.mount("/static", StaticFiles(directory=utils.get_resource_path("static")), name="static")

@app.get("/")
async def get_index():
    index_path = utils.get_resource_path(os.path.join("static", "index.html"))
    if os.path.exists(index_path):
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                content = f.read()
            # Replace placeholder sentinel with env var (Tier 8.4)
            bot_api_url = os.environ.get("BOT_API_URL", "")
            content = content.replace("%%BOT_API_URL%%", bot_api_url)
            return HTMLResponse(content)
        except Exception as e:
            logger.error(f"Error loading and injecting index.html: {e}")
            return FileResponse(index_path)
    return {"message": "Server online. Frontend assets missing in static/"}

def init_default_templates():
    import shutil
    templates_dir = utils.get_writeable_path("templates")
    os.makedirs(templates_dir, exist_ok=True)
    
    # Dynamically initialize default templates by copying all builtin JSON templates
    builtin_dir = utils.get_resource_path(os.path.join("templates", "builtin"))
    if os.path.exists(builtin_dir):
        for filename in os.listdir(builtin_dir):
            if filename.endswith(".json"):
                src_path = os.path.join(builtin_dir, filename)
                dest_path = os.path.join(templates_dir, filename)
                if not os.path.exists(dest_path):
                    try:
                        shutil.copy2(src_path, dest_path)
                        logger.info(f"Initialized template: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to copy template {filename}: {e}")

# Deprecated startup event removed (lifespan manager is used instead)
