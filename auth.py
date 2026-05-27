import hashlib
import os
import base64
import hmac
import time
import json

SESSION_EXPIRY_SECONDS = 24 * 60 * 60  # 24 hours
_revoked_tokens = set()

def get_jwt_secret() -> str:
    """Retrieves the JWT signing secret from the environment."""
    return os.environ.get("JWT_SECRET", "fallback-jwt-secret-key-3849182391283")

def base64url_encode(data: bytes) -> str:
    """Encodes bytes to a base64url string without padding."""
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('utf-8')
    
def base64url_decode(data: str) -> bytes:
    """Decodes a base64url string back to bytes, adding padding if necessary."""
    padding = '=' * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode((data + padding).encode('utf-8'))

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
    """Generates a custom signed session token (JWT-like format) containing guild_id and role."""
    secret = get_jwt_secret()
    payload = {
        "guild_id": guild_id,
        "role": role,
        "exp": time.time() + SESSION_EXPIRY_SECONDS
    }
    header = {"alg": "HS256", "typ": "JWT"}
    
    header_b64 = base64url_encode(json.dumps(header).encode('utf-8'))
    payload_b64 = base64url_encode(json.dumps(payload).encode('utf-8'))
    
    signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
    signature = hmac.new(secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
    signature_b64 = base64url_encode(signature)
    
    return f"{header_b64}.{payload_b64}.{signature_b64}"

def decode_token(token: str) -> dict:
    """Verifies and decodes a custom signed session token (JWT-like format)."""
    if not token:
        return None
    try:
        parts = token.split('.')
        if len(parts) != 3:
            return None
        header_b64, payload_b64, signature_b64 = parts
        
        secret = get_jwt_secret()
        signing_input = f"{header_b64}.{payload_b64}".encode('utf-8')
        expected_signature = hmac.new(secret.encode('utf-8'), signing_input, hashlib.sha256).digest()
        expected_signature_b64 = base64url_encode(expected_signature)
        
        # Use constant-time comparison to prevent timing attacks (Gap 2)
        if not hmac.compare_digest(signature_b64.encode('utf-8'), expected_signature_b64.encode('utf-8')):
            return None
            
        payload = json.loads(base64url_decode(payload_b64).decode('utf-8'))
        # Check expiration
        if time.time() > payload.get("exp", 0):
            return None
        return payload
    except Exception:
        return None

def is_token_revoked(token: str) -> bool:
    """Checks if the token is in the blacklisted revocation set."""
    return token in _revoked_tokens

_revoked_guilds = set()

def load_revoked_guilds():
    global _revoked_guilds
    try:
        import utils
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
    """Revokes all active sessions for a guild and saves it to config.json (Tier 8.5)"""
    global _revoked_guilds
    gid_str = str(guild_id)
    _revoked_guilds.add(gid_str)
    
    # Save to config.json
    try:
        import utils
        with utils.config_lock:
            config = utils.load_config()
            revoked_list = config.setdefault("revoked_guilds", [])
            if gid_str not in revoked_list:
                revoked_list.append(gid_str)
                utils.save_config(config)
    except Exception as e:
        print(f"Error saving revoked guilds to config: {e}")

def validate_session(token: str) -> bool:
    """Checks if a session token is valid, not expired, and not revoked."""
    if is_token_revoked(token):
        return False
    payload = decode_token(token)
    if payload is None:
        return False
    guild_id = payload.get("guild_id")
    if guild_id and is_guild_revoked(guild_id):
        return False
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
    """Revokes a session token by adding it to a local blacklist."""
    if token:
        _revoked_tokens.add(token)
        return True
    return False

def has_active_sessions() -> bool:
    """Cleans up the local blacklist and returns if there is active state (stub for backward compatibility)."""
    # Clean up expired revoked tokens to prevent memory leak
    now = time.time()
    for t in list(_revoked_tokens):
        payload = decode_token(t)
        if not payload or now > payload.get("exp", 0):
            _revoked_tokens.discard(t)
    return True
