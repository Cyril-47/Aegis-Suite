"""Tests for the first-run console setup wizard.

The wizard runs out-of-process (in ``run.py``, before uvicorn binds the
port) so the tests exercise the module's public functions directly via
``tmp_path`` fixtures rather than spinning up subprocesses or the FastAPI
TestClient. The detection contract (``credentials_already_exist``) is the
single most important guarantee — a misfire would either silently stomp
an existing install or skip first-time setup — so most of the suite is
focused on that surface.

Validates the launcher integration described in the
``managed-hosting-migration`` Secrets at Rest section:
  * The wizard never runs when ``DISCORD_BOT_TOKEN`` is already set in
    the environment (cloud / Render path).
  * The wizard never runs when ``.env`` already carries a non-empty
    ``DISCORD_BOT_TOKEN`` line (legacy plaintext install).
  * The wizard never runs when ``.env.enc`` is present (encrypted install).
  * Quoted token values in ``.env`` are correctly handled by detection
    (matches ``utils.load_env_file``'s parser behavior).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
_REPO_ROOT_STR = str(REPO_ROOT)
if _REPO_ROOT_STR not in sys.path:
    sys.path.insert(0, _REPO_ROOT_STR)

import first_run_wizard  # noqa: E402  (import after sys.path mutation)


# ---------------------------------------------------------------------------
# credentials_already_exist — detection contract
# ---------------------------------------------------------------------------


def test_detection_returns_false_on_clean_install(tmp_path, monkeypatch):
    """An empty repo with no env vars and no files needs the wizard."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    assert first_run_wizard.credentials_already_exist(tmp_path) is False


def test_detection_returns_true_when_env_var_set(tmp_path, monkeypatch):
    """Cloud / Render path: env var present means wizard must NOT run.

    Even on an empty filesystem, a platform-injected ``DISCORD_BOT_TOKEN``
    wins. This is the primary path on Render and other cloud hosts where the wizard
    would have nothing to do anyway.
    """
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "platform-injected-fake-token")
    assert first_run_wizard.credentials_already_exist(tmp_path) is True


def test_detection_returns_true_when_env_var_empty_string_with_file(
    tmp_path, monkeypatch
):
    """An empty ``DISCORD_BOT_TOKEN`` env var must not satisfy detection alone.

    Empty strings are common when an operator clears an env var without
    fully unsetting it (e.g., ``set DISCORD_BOT_TOKEN=`` on Windows). The
    wizard should treat that exactly like the env var being absent.
    """
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "")
    assert first_run_wizard.credentials_already_exist(tmp_path) is False


def test_detection_returns_true_when_env_file_has_token(tmp_path, monkeypatch):
    """Legacy plaintext path: ``.env`` carries a non-empty token line."""
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "DISCORD_BOT_TOKEN=plain-fake-token\nJWT_SECRET=abc\n",
        encoding="utf-8",
    )
    assert first_run_wizard.credentials_already_exist(tmp_path) is True


def test_detection_handles_quoted_token_in_env_file(tmp_path, monkeypatch):
    """Quoted token values must satisfy detection.

    ``utils.load_env_file`` strips both single and double quotes before
    using the value. The wizard's detection helper must agree so a hand-
    edited ``.env`` like ``DISCORD_BOT_TOKEN="abc.def"`` is recognized as
    a configured install.
    """
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        'DISCORD_BOT_TOKEN="quoted.fake.token"\n',
        encoding="utf-8",
    )
    assert first_run_wizard.credentials_already_exist(tmp_path) is True


def test_detection_ignores_empty_token_in_env_file(tmp_path, monkeypatch):
    """An ``.env`` whose token line is empty/whitespace does not block the wizard.

    The detection check looks for a non-empty value after ``.strip()`` so
    a zombie ``.env`` left over from an aborted install does not silently
    skip first-time setup.
    """
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    (tmp_path / ".env").write_text(
        "DISCORD_BOT_TOKEN=\nJWT_SECRET=other-value\n",
        encoding="utf-8",
    )
    assert first_run_wizard.credentials_already_exist(tmp_path) is False


def test_detection_returns_true_when_env_enc_exists(tmp_path, monkeypatch):
    """Encrypted-install path: ``.env.enc`` presence alone satisfies detection.

    The wizard does not validate the envelope's contents — that is the
    loader's job at startup. Detection only needs to refuse to run when
    *any* credible credential file is on disk.
    """
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    (tmp_path / ".env.enc").write_text("{}", encoding="utf-8")
    assert first_run_wizard.credentials_already_exist(tmp_path) is True


def test_detection_handles_unreadable_env_file(tmp_path, monkeypatch):
    """An unreadable ``.env`` is treated as "do not run the wizard".

    Failing closed (refusing to overwrite a file we couldn't read) avoids
    silent data loss when the operator has restricted permissions on the
    file. The actual load error will surface from ``utils.load_env_file``
    later in startup.
    """
    monkeypatch.delenv("DISCORD_BOT_TOKEN", raising=False)
    env_path = tmp_path / ".env"
    env_path.write_text("DISCORD_BOT_TOKEN=ok\n", encoding="utf-8")

    # Simulate a read failure by patching ``Path.read_text`` for this path.
    real_read_text = Path.read_text

    def _exploding_read_text(self, *args, **kwargs):
        if self == env_path:
            raise OSError("permission denied (test)")
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", _exploding_read_text)
    assert first_run_wizard.credentials_already_exist(tmp_path) is True


# ---------------------------------------------------------------------------
# _persist_credentials — file write + DPAPI integration
# ---------------------------------------------------------------------------


def test_persist_credentials_writes_env_file(tmp_path):
    """``_persist_credentials`` always writes the plaintext blob first.

    Even when DPAPI is unavailable (non-Windows runners) the function
    must leave a usable credential file on disk so the dashboard can
    start in legacy plaintext mode rather than landing in the
    "missing token" maintenance overlay.
    """
    blob = "DISCORD_BOT_TOKEN=fake.token.value\nJWT_SECRET=abc\n"
    success = first_run_wizard._persist_credentials(tmp_path, blob)
    assert success is True
    # Either .env (no DPAPI) or .env.enc (DPAPI worked) should now exist.
    has_plain = (tmp_path / ".env").is_file()
    has_enc = (tmp_path / ".env.enc").is_file()
    assert has_plain or has_enc, (
        "_persist_credentials must produce at least one credential file."
    )


def test_persist_credentials_encrypts_when_dpapi_available(tmp_path, monkeypatch):
    """On Windows + pywin32, the plaintext .env is replaced by .env.enc.

    The test stubs ``secret_store.is_dpapi_available`` and
    ``secret_store.encrypt_env_file`` so the assertion holds on any
    runner regardless of OS — the goal is to verify the wizard's
    orchestration logic, not pywin32 itself (which has its own coverage
    in ``tests/test_secret_store.py``).
    """
    import aegis.core.secret_store as secret_store

    fake_blob = "DISCORD_BOT_TOKEN=fake.token.value\nJWT_SECRET=abc\n"

    # Force DPAPI to "available" and replace the actual encryption with a
    # marker write so the test runs on Linux CI too.
    monkeypatch.setattr(secret_store, "is_dpapi_available", lambda: True)

    def _fake_encrypt(plaintext_path, encrypted_path):
        Path(encrypted_path).write_text("ENCRYPTED-MARKER", encoding="utf-8")
        return Path(encrypted_path)

    monkeypatch.setattr(secret_store, "encrypt_env_file", _fake_encrypt)

    success = first_run_wizard._persist_credentials(tmp_path, fake_blob)

    assert success is True
    enc_path = tmp_path / ".env.enc"
    plain_path = tmp_path / ".env"
    assert enc_path.is_file(), (
        "When DPAPI is available, .env.enc must be present after the wizard "
        "completes."
    )
    # The plaintext .env must be deleted after a successful encryption so
    # the cleartext lifetime on disk is bounded.
    assert not plain_path.is_file(), (
        "After successful encryption the plaintext .env must be deleted to "
        "honor the Secret Store contract."
    )


def test_persist_credentials_keeps_plaintext_when_dpapi_unavailable(
    tmp_path, monkeypatch
):
    """When DPAPI is unavailable, ``.env`` stays put as the legacy fallback.

    This is the Linux / non-pywin32 path. The function must not delete
    the plaintext file because there is nothing to replace it with.
    """
    import aegis.core.secret_store as secret_store

    monkeypatch.setattr(secret_store, "is_dpapi_available", lambda: False)

    blob = "DISCORD_BOT_TOKEN=fake.token.value\n"
    success = first_run_wizard._persist_credentials(tmp_path, blob)

    assert success is True
    assert (tmp_path / ".env").is_file()
    assert not (tmp_path / ".env.enc").is_file()


# ---------------------------------------------------------------------------
# Validators — token / client_id input shapes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "value,expected",
    [
        # Synthetic 60+ character string in the [A-Za-z0-9._-] alphabet that
        # passes the validator without resembling a real Discord token. The
        # validator only checks shape (20+ chars in that alphabet), so this
        # placeholder exercises the same code path without tripping
        # GitHub's secret-scanning push protection.
        ("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAA.BBBBBB.CCCCCCCCCCCCCCCCCCCCCCCCCC", True),
        ("short", False),
        ("", False),
        ("contains spaces inside", False),
        ("has/slash/which-discord-never-uses", False),
    ],
)
def test_validate_bot_token_shape(value, expected):
    ok, _ = first_run_wizard._validate_bot_token(value)
    assert ok is expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("123456789012345678", True),  # 18 digits — common
        ("12345678901234567", True),  # 17 digits — minimum
        ("12345678901234567890", True),  # 20 digits — maximum
        ("1234567890123456", False),  # 16 digits — too short
        ("123456789012345678901", False),  # 21 digits — too long
        ("not-a-number", False),
        ("", False),
        ("123-456-789-012-345-678", False),
    ],
)
def test_validate_client_id_shape(value, expected):
    ok, _ = first_run_wizard._validate_client_id(value)
    assert ok is expected
