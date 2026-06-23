"""
Tests for authentication module.
"""

import pytest
import time
import hashlib
import base64
import os
from unittest.mock import patch, MagicMock

# Add parent directory to path
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from aegis.core.auth import (
    hash_password,
    verify_password,
    create_session,
    decode_token,
    validate_session,
    check_login_rate_limit,
    get_login_attempts_remaining,
    _token_hash,
)


class TestPasswordHashing:
    """Tests for password hashing and verification."""

    def test_hash_password_returns_string(self):
        """Test that hash_password returns a string."""
        result = hash_password("test_password")
        assert isinstance(result, str)

    def test_hash_password_contains_pbkdf2(self):
        """Test that hash contains pbkdf2 prefix."""
        result = hash_password("test_password")
        assert result.startswith("pbkdf2_sha256$")

    def test_verify_password_correct(self):
        """Test password verification with correct password."""
        password = "secure_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password."""
        password = "secure_password_123"
        hashed = hash_password(password)
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_empty(self):
        """Test password verification with empty password."""
        assert verify_password("", "pbkdf2_sha256$100000$abc$def") is False

    def test_verify_password_invalid_format(self):
        """Test password verification with invalid hash format."""
        assert verify_password("password", "invalid_hash") is False


class TestJWTToken:
    """Tests for JWT token creation and validation."""

    @pytest.fixture(autouse=True)
    def setup_jwt_secret(self):
        """Set up JWT secret for testing."""
        orig_secret = os.environ.get("JWT_SECRET")
        os.environ["JWT_SECRET"] = "test_secret_key_for_testing"
        yield
        if orig_secret is not None:
            os.environ["JWT_SECRET"] = orig_secret
        elif "JWT_SECRET" in os.environ:
            del os.environ["JWT_SECRET"]

    def test_create_session_returns_string(self):
        """Test that create_session returns a string."""
        token = create_session("123456789", "admin")
        assert isinstance(token, str)

    def test_create_session_contains_payload(self):
        """Test that token contains expected payload."""
        token = create_session("123456789", "admin")
        payload = decode_token(token)
        assert payload is not None
        assert payload["guild_id"] == "123456789"
        assert payload["role"] == "admin"

    def test_decode_valid_token(self):
        """Test decoding a valid token."""
        token = create_session("123456789", "admin")
        payload = decode_token(token)
        assert payload is not None
        assert "exp" in payload

    def test_decode_invalid_token(self):
        """Test decoding an invalid token."""
        payload = decode_token("invalid_token")
        assert payload is None

    def test_validate_session_valid(self):
        """Test validating a valid session."""
        token = create_session("123456789", "admin")
        assert validate_session(token) is True

    def test_validate_session_invalid(self):
        """Test validating an invalid session."""
        assert validate_session("invalid_token") is False

    def test_token_hash_deterministic(self):
        """Test that token hash is deterministic."""
        token = "test_token"
        hash1 = _token_hash(token)
        hash2 = _token_hash(token)
        assert hash1 == hash2


class TestLoginRateLimit:
    """Tests for login rate limiting."""

    @pytest.fixture(autouse=True)
    def clear_rate_limit(self):
        """Clear login attempts before and after each test."""
        from aegis.core.auth import _login_attempts
        _login_attempts.clear()
        yield
        _login_attempts.clear()

    def test_allows_initial_requests(self):
        """Test that initial requests are allowed."""
        assert check_login_rate_limit("192.168.1.1") is True

    def test_blocks_after_max_attempts(self):
        """Test that requests are blocked after max attempts."""
        ip = "192.168.1.2"
        for _ in range(5):
            check_login_rate_limit(ip)
        
        assert check_login_rate_limit(ip) is False

    def test_get_attempts_remaining(self):
        """Test getting remaining attempts."""
        ip = "192.168.1.3"
        remaining = get_login_attempts_remaining(ip)
        assert remaining == 5

    def test_attempts_decrease(self):
        """Test that attempts decrease after use."""
        ip = "192.168.1.4"
        check_login_rate_limit(ip)
        remaining = get_login_attempts_remaining(ip)
        assert remaining == 4
