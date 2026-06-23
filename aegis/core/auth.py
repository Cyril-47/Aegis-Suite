import hashlib
import os
import base64
import hmac
import time
import jwt
import logging

logger = logging.getLogger("aegis.auth")

SESSION_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours
_revoked_tokens = set()
_validated_tokens = {}  # token_hash -> expiry_timestamp
_db_engine = None

# Rate limiting for login attempts
_login_attempts = {}  # ip -> [timestamps]
MAX_LOGIN_ATTEMPTS = 5
LOGIN_WINDOW_SECONDS = 15 * 60  # 15 minutes

def set_db_engine(engine):
    """Sets the database engine explicitly for testing or startup config."""
    global _db_engine
    _db_engine = engine

def get_db_session():
    """Retrieves a new SQLAlchemy database session if available, falling back to active cores."""
    global _db_engine
    engine = _db_engine
    if engine is None:
        from aegis.core.app_core import _active_cores
        if _active_cores:
            engine = _active_cores[-1].db
    if engine is not None:
        from sqlalchemy.orm import sessionmaker
        return sessionmaker(bind=engine)()
    return None

def get_jwt_secret() -> str:
    """Retrieves the JWT signing secret from the environment."""
    secret = os.environ.get("JWT_SECRET")
    if not secret:
        return None
    return secret

def hash_password(password: str) -> str:
    """Hashes a password using PBKDF2-SHA256."""
    salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    salt_b64 = base64.b64encode(salt).decode('utf-8')
    key_b64 = base64.b64encode(key).decode('utf-8')
    return f"pbkdf2_sha256$100000${salt_b64}${key_b64}"

def verify_password(password: str, hashed_password: str) -> bool:
    """Verifies a password against its PBKDF2-SHA256 hash using constant-time comparison."""
    if not hashed_password:
        return False
    try:
        parts = hashed_password.split('$')
        if len(parts) != 4 or parts[0] != 'pbkdf2_sha256':
            return False
        iterations = int(parts[1])
        salt = base64.b64decode(parts[2])
        key = base64.b64decode(parts[3])
        new_key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)
        return hmac.compare_digest(key, new_key)
    except Exception:
        return False

def create_session(guild_id: str = "global", role: str = "admin") -> str:
    """Generates a signed session token (JWT) containing guild_id and role."""
    secret = get_jwt_secret()
    if not secret:
        return ""
    payload = {
        "guild_id": guild_id,
        "role": role,
        "exp": int(time.time() + SESSION_EXPIRY_SECONDS)
    }
    return jwt.encode(payload, secret, algorithm="HS256")

def decode_token(token: str) -> dict:
    """Verifies and decodes a signed session token (JWT)."""
    if not token:
        return None
    secret = get_jwt_secret()
    if not secret:
        return None
    try:
        return jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None

def _token_hash(token: str) -> str:
    """Returns a short SHA-256 fingerprint of the token for cache keys."""
    return hashlib.sha256(token.encode()).hexdigest()[:16]

def is_token_revoked(token: str) -> bool:
    """Checks if the token is in the blacklisted revocation set or database."""
    if token in _revoked_tokens:
        return True

    session = get_db_session()
    if session is not None:
        try:
            from aegis.db.models import RevokedToken
            row = session.query(RevokedToken).filter(RevokedToken.token == token).first()
            if row is not None:
                _revoked_tokens.add(token)
                return True
        except Exception as e:
            logger.error(f"Error checking revoked token in DB: {e}")
        finally:
            session.close()

    return False

_revoked_guilds = set()

def load_revoked_guilds():
    global _revoked_guilds
    try:
        import aegis.core.utils as utils
        config = utils.load_config()
        _revoked_guilds = set(config.get("revoked_guilds", []))
    except Exception:
        pass

# Initialize revoked guilds set
load_revoked_guilds()

def is_guild_revoked(guild_id: str) -> bool:
    """Checks if a guild has been revoked/unlinked."""
    return str(guild_id) in _revoked_guilds

def revoke_guild_sessions(guild_id: str):
    """Revokes all active sessions for a guild and saves it to config.json"""
    global _revoked_guilds
    gid_str = str(guild_id)
    _revoked_guilds.add(gid_str)
    
    try:
        import aegis.core.utils as utils
        with utils.config_lock:
            config = utils.load_config()
            revoked_list = config.setdefault("revoked_guilds", [])
            if gid_str not in revoked_list:
                revoked_list.append(gid_str)
                utils.save_config(config)
    except Exception as e:
        logger.error(f"Error saving revoked guilds to config: {e}")

def validate_session(token: str) -> bool:
    """Checks if a session token is valid, not expired, and not revoked.

    Uses a short-lived in-memory cache of validated token hashes to avoid a
    blocking SQLite round-trip on every API request.  Revoked tokens are always
    caught via the in-memory ``_revoked_tokens`` set which is updated eagerly
    on logout, so a cached positive entry can never mask a revocation.  Guild
    revocation is also re-checked on every call since ``_revoked_guilds`` is a
    lightweight in-memory set.
    """
    th = _token_hash(token)

    # Fast path – token was recently validated and not yet expired.
    if th in _validated_tokens:
        if time.time() < _validated_tokens[th]:
            # Re-check guild revocation (in-memory set, no I/O)
            payload = decode_token(token)
            if payload:
                guild_id = payload.get("guild_id")
                if guild_id and is_guild_revoked(guild_id):
                    _validated_tokens.pop(th, None)
                    return False
            return True
        # Expired entry – clean up and fall through.
        _validated_tokens.pop(th, None)

    if is_token_revoked(token):
        return False

    payload = decode_token(token)
    if payload is None:
        return False

    guild_id = payload.get("guild_id")
    if guild_id and is_guild_revoked(guild_id):
        return False

    _validated_tokens[th] = payload.get("exp", 0)
    return True

def get_session_guild_id(token: str) -> str:
    """Retrieves the guild ID associated with the session if valid."""
    payload = decode_token(token)
    if not payload:
        return None
    return payload.get("guild_id")

def get_session_role(token: str) -> str:
    """Retrieves the role associated with the session if valid."""
    payload = decode_token(token)
    if not payload:
        return None
    return payload.get("role")

def destroy_session(token: str) -> bool:
    """Revokes a session token by adding it to the local blacklist and database."""
    if token:
        _revoked_tokens.add(token)
        _validated_tokens.pop(_token_hash(token), None)
        session = get_db_session()
        if session is not None:
            try:
                from aegis.db.models import RevokedToken
                exists = session.query(RevokedToken).filter(RevokedToken.token == token).first()
                if not exists:
                    row = RevokedToken(token=token)
                    session.add(row)
                    session.commit()
            except Exception as e:
                logger.error(f"Error persisting revoked token to DB: {e}")
            finally:
                session.close()
        return True
    return False

def has_active_sessions() -> bool:
    """Prunes expired revoked tokens from memory and database."""
    now = time.time()

    # Prune expired validated-token cache entries
    for th in [k for k, exp in _validated_tokens.items() if now >= exp]:
        _validated_tokens.pop(th)

    for t in list(_revoked_tokens):
        payload = decode_token(t)
        if not payload or now > payload.get("exp", 0):
            _revoked_tokens.discard(t)
            
    session = get_db_session()
    if session is not None:
        try:
            from aegis.db.models import RevokedToken
            rows = session.query(RevokedToken).all()
            for row in rows:
                payload = decode_token(row.token)
                if not payload or now > payload.get("exp", 0):
                    session.delete(row)
            session.commit()
        except Exception as e:
            logger.error(f"Error pruning expired revoked tokens in DB: {e}")
        finally:
            session.close()
    return True


def check_login_rate_limit(ip_address: str) -> bool:
    """Check if an IP address has exceeded login rate limits.
    
    Returns True if the request is allowed, False if rate limited.
    """
    now = time.time()
    
    # Get or create attempt list for this IP
    if ip_address not in _login_attempts:
        _login_attempts[ip_address] = []
    
    # Clean up old attempts outside the window
    _login_attempts[ip_address] = [
        ts for ts in _login_attempts[ip_address]
        if now - ts < LOGIN_WINDOW_SECONDS
    ]
    
    # Check if rate limited
    if len(_login_attempts[ip_address]) >= MAX_LOGIN_ATTEMPTS:
        logger.warning(f"Login rate limit exceeded for IP: {ip_address}")
        return False
    
    # Record this attempt
    _login_attempts[ip_address].append(now)
    return True


def get_login_attempts_remaining(ip_address: str) -> int:
    """Get the number of login attempts remaining for an IP."""
    now = time.time()
    if ip_address not in _login_attempts:
        return MAX_LOGIN_ATTEMPTS
    
    # Clean up old attempts
    _login_attempts[ip_address] = [
        ts for ts in _login_attempts[ip_address]
        if now - ts < LOGIN_WINDOW_SECONDS
    ]
    
    return max(0, MAX_LOGIN_ATTEMPTS - len(_login_attempts[ip_address]))
