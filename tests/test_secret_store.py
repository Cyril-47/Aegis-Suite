"""Tests for the DPAPI-backed encrypted secret store.

Tests are skipped on non-Windows hosts (CI Linux runners, Render, etc.)
where DPAPI is unavailable. The skip is intentional: the cloud deploy path
uses platform-injected environment variables and never touches the
encryption module.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import aegis.core.secret_store as secret_store  # noqa: E402


pytestmark = pytest.mark.skipif(
    not secret_store.is_dpapi_available(),
    reason="Windows DPAPI is unavailable on this host (non-Windows or pywin32 missing).",
)


# ---------------------------------------------------------------------------
# Encrypt / decrypt round-trip
# ---------------------------------------------------------------------------


def test_encrypt_decrypt_roundtrip(tmp_path: Path) -> None:
    """A plaintext .env file encrypted via DPAPI must decrypt to the
    original byte sequence."""
    src = tmp_path / ".env"
    plaintext = (
        b"DISCORD_BOT_TOKEN=ABC.DEF.GHI\n"
        b"JWT_SECRET=" + b"a" * 64 + b"\n"
        b"ADMIN_PASSWORD_HASH=pbkdf2_sha256$100000$salt$key\n"
    )
    src.write_bytes(plaintext)

    enc = tmp_path / ".env.enc"
    secret_store.encrypt_env_file(src, enc)
    assert enc.is_file(), "encrypt_env_file did not create the destination file."

    payload = json.loads(enc.read_text(encoding="utf-8"))
    assert payload["magic"] == secret_store.MAGIC, (
        "Encrypted file is missing the AEGIS_DPAPI_V1 magic header."
    )
    assert isinstance(payload["ciphertext_b64"], str), (
        "Encrypted file does not carry a string `ciphertext_b64` field."
    )

    # The ciphertext must NOT contain the plaintext bytes anywhere — DPAPI
    # is supposed to actually encrypt, not just base64-encode.
    raw_ciphertext = enc.read_bytes()
    for sensitive in (b"ABC.DEF.GHI", b"pbkdf2_sha256$100000"):
        assert sensitive not in raw_ciphertext, (
            f"The encrypted file leaks plaintext fragment {sensitive!r}."
        )

    decrypted = secret_store.decrypt_env_file(enc)
    assert decrypted == plaintext, (
        "decrypt_env_file did not return the exact input bytes; "
        f"expected {plaintext!r}, got {decrypted!r}."
    )


# ---------------------------------------------------------------------------
# Magic header check
# ---------------------------------------------------------------------------


def test_decrypt_rejects_missing_magic_header(tmp_path: Path) -> None:
    """A JSON file lacking the magic header must raise CorruptedSecretFile."""
    enc = tmp_path / ".env.enc"
    enc.write_text(
        json.dumps({"ciphertext_b64": "QUFB"}),  # No "magic" field.
        encoding="utf-8",
    )
    with pytest.raises(secret_store.CorruptedSecretFile):
        secret_store.decrypt_env_file(enc)


def test_decrypt_rejects_unknown_magic_header(tmp_path: Path) -> None:
    """A JSON file with an unrecognized magic header must raise."""
    enc = tmp_path / ".env.enc"
    enc.write_text(
        json.dumps({"magic": "DIFFERENT_FORMAT_V99", "ciphertext_b64": "QUFB"}),
        encoding="utf-8",
    )
    with pytest.raises(secret_store.CorruptedSecretFile):
        secret_store.decrypt_env_file(enc)


def test_decrypt_rejects_non_json(tmp_path: Path) -> None:
    """A non-JSON file at the encrypted path must raise CorruptedSecretFile."""
    enc = tmp_path / ".env.enc"
    enc.write_bytes(b"this is not json")
    with pytest.raises(secret_store.CorruptedSecretFile):
        secret_store.decrypt_env_file(enc)


# ---------------------------------------------------------------------------
# Loader fallback chain
# ---------------------------------------------------------------------------


def test_load_env_file_prefers_encrypted_over_plaintext(
    tmp_path: Path, monkeypatch
) -> None:
    """When both .env and .env.enc exist, ``utils.load_env_file`` must use
    the encrypted file (treating plaintext .env as a legacy fallback)."""
    plaintext_token = "PLAINTEXT-TOKEN-SHOULD-NOT-WIN"
    encrypted_token = "ENCRYPTED-TOKEN-SHOULD-WIN"

    # Lay down both files in the temp dir, with different DISCORD_BOT_TOKEN
    # values so we can tell which one was loaded.
    env_dir = tmp_path
    plaintext_env = env_dir / ".env"
    plaintext_env.write_text(
        f"DISCORD_BOT_TOKEN={plaintext_token}\n", encoding="utf-8"
    )
    encrypted_env = env_dir / ".env.enc"
    src = env_dir / ".env.source"
    src.write_text(
        f"DISCORD_BOT_TOKEN={encrypted_token}\n", encoding="utf-8"
    )
    secret_store.encrypt_env_file(src, encrypted_env)
    src.unlink()

    # Reroute utils.get_writeable_path to our temp dir so load_env_file
    # reads the test files instead of the real repo-root .env.
    import aegis.core.utils as utils

    def fake_writeable_path(filename: str) -> str:
        return str(env_dir / filename)

    monkeypatch.setattr(utils, "get_writeable_path", fake_writeable_path)
    # Clear the real-env-loaded value so the loader has a blank slate.
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    # Pre-seed JWT_SECRET so load_env_file does not auto-write a new one
    # to the test env file.
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-loader-precedence")

    utils.load_env_file()

    import os

    assert os.environ.get("DISCORD_BOT_TOKEN") == encrypted_token, (
        "load_env_file loaded the plaintext .env value when both .env and "
        ".env.enc were present. The encrypted file must take priority. "
        f"Got: {os.environ.get('DISCORD_BOT_TOKEN')!r}"
    )


def test_load_env_file_platform_env_takes_precedence(
    tmp_path: Path, monkeypatch
) -> None:
    """Platform-injected environment variables (Render / other cloud) must win
    over both file-based sources. The file values may still populate keys
    that are absent from the environment, but they must never overwrite a
    pre-existing non-empty environment value."""
    platform_token = "CLOUD-PROVIDED-TOKEN"
    file_token = "FILE-PROVIDED-TOKEN"

    env_dir = tmp_path
    plaintext_env = env_dir / ".env"
    plaintext_env.write_text(
        f"DISCORD_BOT_TOKEN={file_token}\n", encoding="utf-8"
    )

    import aegis.core.utils as utils

    def fake_writeable_path(filename: str) -> str:
        return str(env_dir / filename)

    monkeypatch.setattr(utils, "get_writeable_path", fake_writeable_path)
    monkeypatch.setenv("DISCORD_BOT_TOKEN", platform_token)
    monkeypatch.setenv("JWT_SECRET", "test-jwt-secret-for-platform-precedence")

    utils.load_env_file()

    import os

    assert os.environ.get("DISCORD_BOT_TOKEN") == platform_token, (
        "load_env_file overwrote a pre-set DISCORD_BOT_TOKEN with the value "
        "from .env. Cloud hosts inject secrets via the environment and the "
        f"file path must never clobber them. Got: {os.environ.get('DISCORD_BOT_TOKEN')!r}"
    )
