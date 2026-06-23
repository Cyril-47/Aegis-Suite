"""Aggressive real-world scenario tests for Dashboard Auth.

Simulates actual attack conditions:
- Brute force login attempts
- Token reuse after logout
- Guild revocation mid-session
- Concurrent sessions across IPs
- Token expiry edge cases
"""
import pytest
import asyncio
import time
import os
from aegis.core import auth


@pytest.fixture(autouse=True)
def clean_auth_state():
    """Clean auth state before each test."""
    auth._login_attempts.clear()
    auth._revoked_tokens.clear()
    auth._validated_tokens.clear()
    auth._revoked_guilds.clear()
    os.environ["JWT_SECRET"] = "test_secret_key_for_auth_tests_32bytes!"
    yield
    auth._login_attempts.clear()
    auth._revoked_tokens.clear()
    auth._validated_tokens.clear()
    auth._revoked_guilds.clear()
    os.environ.pop("JWT_SECRET", None)


# --- BRUTE FORCE ATTACKS ---

def test_brute_force_5_attempts():
    """5 login attempts from same IP -> blocked on 6th."""
    for i in range(5):
        assert auth.check_login_rate_limit("192.168.1.100") is True
    assert auth.check_login_rate_limit("192.168.1.100") is False


def test_brute_force_100_attempts():
    """100 rapid attempts from same IP -> all blocked after 5th."""
    for i in range(5):
        auth.check_login_rate_limit("10.0.0.50")
    blocked = 0
    for i in range(100):
        if not auth.check_login_rate_limit("10.0.0.50"):
            blocked += 1
    assert blocked == 100


def test_brute_force_distributed():
    """100 different IPs each making 5 attempts -> all allowed."""
    for i in range(100):
        ip = f"10.0.{i // 256}.{i % 256}"
        for _ in range(5):
            assert auth.check_login_rate_limit(ip) is True


def test_brute_force_after_cooldown():
    """After 15 min window, attempts reset."""
    auth._login_attempts["10.0.0.1"] = [time.time() - 901]  # 15+ min ago
    assert auth.check_login_rate_limit("10.0.0.1") is True
    remaining = auth.get_login_attempts_remaining("10.0.0.1")
    assert remaining == 4  # 1 used + 4 remaining


def test_rate_limit_attempts_remaining():
    """Remaining count decreases correctly."""
    auth._login_attempts.clear()
    assert auth.get_login_attempts_remaining("1.1.1.1") == 5
    auth.check_login_rate_limit("1.1.1.1")
    assert auth.get_login_attempts_remaining("1.1.1.1") == 4
    auth.check_login_rate_limit("1.1.1.1")
    assert auth.get_login_attempts_remaining("1.1.1.1") == 3


# --- TOKEN SECURITY ---

def test_password_hash_uniqueness():
    """Same password -> different hashes (random salt)."""
    h1 = auth.hash_password("secure_password_123")
    h2 = auth.hash_password("secure_password_123")
    assert h1 != h2


def test_password_verify_correct():
    """Correct password verifies."""
    h = auth.hash_password("my_secret")
    assert auth.verify_password("my_secret", h) is True


def test_password_verify_wrong():
    """Wrong password fails."""
    h = auth.hash_password("my_secret")
    assert auth.verify_password("wrong_password", h) is False


def test_password_verify_empty():
    """Empty password or hash -> False."""
    assert auth.verify_password("", "pbkdf2_sha256$100000$abc$def") is False
    assert auth.verify_password("test", "") is False
    assert auth.verify_password("test", None) is False


def test_password_verify_malformed():
    """Malformed hash -> False."""
    assert auth.verify_password("test", "not_a_hash") is False
    assert auth.verify_password("test", "pbkdf2_sha256$") is False
    assert auth.verify_password("test", "sha256$abc$def") is False


# --- JWT TOKEN LIFECYCLE ---

def test_jwt_create_and_decode():
    """Create and decode a JWT token."""
    token = auth.create_session("guild_123", "admin")
    assert len(token) > 0
    payload = auth.decode_token(token)
    assert payload["guild_id"] == "guild_123"
    assert payload["role"] == "admin"
    assert "exp" in payload


def test_jwt_no_secret():
    """No JWT_SECRET -> empty token."""
    os.environ.pop("JWT_SECRET", None)
    token = auth.create_session("g1", "admin")
    assert token == ""


def test_jwt_invalid_token():
    """Invalid token -> None."""
    result = auth.decode_token("invalid.jwt.token")
    assert result is None


def test_jwt_empty_token():
    """Empty token -> None."""
    assert auth.decode_token("") is None
    assert auth.decode_token(None) is None


def test_session_validate_and_destroy():
    """Create -> validate -> destroy -> validate fails."""
    token = auth.create_session("g1", "admin")
    assert auth.validate_session(token) is True
    auth.destroy_session(token)
    assert auth.validate_session(token) is False
    assert auth.is_token_revoked(token) is True


def test_session_destroy_empty():
    """Destroy empty token -> False."""
    assert auth.destroy_session("") is False
    assert auth.destroy_session(None) is False


def test_session_expiry():
    """Expired token -> invalid."""
    import jwt as pyjwt
    payload = {
        "guild_id": "g1",
        "role": "admin",
        "exp": int(time.time()) - 3600
    }
    token = pyjwt.encode(payload, os.environ["JWT_SECRET"], algorithm="HS256")
    assert auth.validate_session(token) is False


def test_session_not_yet_expired():
    """Token expiring in 1 hour -> valid."""
    token = auth.create_session("g1", "admin")
    assert auth.validate_session(token) is True


# --- GUILD REVOCATION ---

def test_guild_revocation():
    """Revoked guild blocks sessions."""
    auth.revoke_guild_sessions("bad_guild")
    assert auth.is_guild_revoked("bad_guild") is True
    token = auth.create_session("bad_guild", "admin")
    assert auth.validate_session(token) is False


def test_guild_revocation_doesnt_affect_others():
    """Revoking guild A doesn't affect guild B."""
    auth.revoke_guild_sessions("guild_a")
    token = auth.create_session("guild_b", "admin")
    assert auth.validate_session(token) is True


def test_multiple_guild_revocations():
    """Revoking multiple guilds."""
    for i in range(10):
        auth.revoke_guild_sessions(f"guild_{i}")
    for i in range(10):
        assert auth.is_guild_revoked(f"guild_{i}") is True
        token = auth.create_session(f"guild_{i}", "admin")
        assert auth.validate_session(token) is False


# --- CONCURRENT SECURITY ---

def test_1000_concurrent_ips():
    """1000 different IPs all within limits."""
    for i in range(1000):
        ip = f"192.168.{i // 256}.{i % 256}"
        assert auth.check_login_rate_limit(ip) is True


def test_token_hash_deterministic():
    """Same token -> same hash."""
    h1 = auth._token_hash("test_token_abc")
    h2 = auth._token_hash("test_token_abc")
    assert h1 == h2


def test_token_hash_unique():
    """Different tokens -> different hashes."""
    h1 = auth._token_hash("token_1")
    h2 = auth._token_hash("token_2")
    assert h1 != h2


def test_validated_tokens_cache():
    """Token validation uses cache on second call."""
    token = auth.create_session("g1", "admin")
    auth._validated_tokens.clear()

    # First call - validates and caches
    assert auth.validate_session(token) is True
    th = auth._token_hash(token)
    assert th in auth._validated_tokens

    # Second call - uses cache
    assert auth.validate_session(token) is True


def test_revoked_token_invalidates_cache():
    """Destroying token removes from cache."""
    token = auth.create_session("g1", "admin")
    auth.validate_session(token)
    th = auth._token_hash(token)
    assert th in auth._validated_tokens

    auth.destroy_session(token)
    assert th not in auth._validated_tokens


def test_session_guild_id_retrieval():
    """Get guild_id from token."""
    token = auth.create_session("guild_999", "admin")
    assert auth.get_session_guild_id(token) == "guild_999"


def test_session_role_retrieval():
    """Get role from token."""
    token = auth.create_session("g1", "moderator")
    assert auth.get_session_role(token) == "moderator"


def test_session_invalid_guild_retrieval():
    """Invalid token -> None for guild_id."""
    assert auth.get_session_guild_id("invalid") is None
    assert auth.get_session_role("invalid") is None
