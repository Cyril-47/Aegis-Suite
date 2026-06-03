"""Console-based first-run wizard for self-hosted Aegis Suite installations.

This module is invoked exactly once on a fresh install: when the launcher
detects that no credential source exists (no ``DISCORD_BOT_TOKEN`` in the
environment, no ``.env`` file, and no DPAPI-encrypted ``.env.enc`` file).
The wizard prompts the operator for the four secrets the bot needs and
persists them. On Windows it writes the DPAPI-encrypted ``.env.enc`` and
deletes the plaintext file; on other hosts (or when ``pywin32`` is missing)
it leaves a plaintext ``.env`` in place as the legacy fallback path.

Why a console wizard rather than a dashboard wizard?
====================================================
The ``managed-hosting-migration`` spec deliberately removed the
in-dashboard token-entry surface — every HTTP request handler that wrote
``DISCORD_BOT_TOKEN`` was deleted, the ``ConfigModel.bot_token`` field was
dropped, the Setup Wizard DOM was removed, and ``/api/bot/start`` /
``/api/bot/stop`` were retired. That contract is locked in by acceptance
criteria R1.1, R2.1, R2.2, R2.4 and the regression suite in
``tests/test_managed_hosting.py``. A console wizard is a different
surface: it runs out-of-process before uvicorn binds the port, the
secrets never traverse the network or the FastAPI app, and the dashboard
itself remains read-only with respect to credentials.

What the wizard collects
========================
* ``DISCORD_BOT_TOKEN`` — required. The Discord application's bot token
  (created at https://discord.com/developers).
* ``CLIENT_ID`` — required for the Invite Bot button URL on the dashboard
  login page. The application's 17-19 digit numeric ID.
* ``ADMIN_PASSWORD_HASH`` — derived from a plaintext password the operator
  enters. The wizard hashes via ``auth.hash_password`` (PBKDF2-SHA256,
  100k iterations) so the plaintext is never written to disk.
* ``JWT_SECRET`` — auto-generated via ``secrets.token_hex(32)`` when not
  already set.
* ``BOT_API_URL`` — optional, asked only when the operator confirms they
  intend to expose the dashboard behind a reverse proxy.

Detection contract
==================
The launcher calls ``credentials_already_exist(repo_root)`` which returns
``True`` when at least one of:

  * ``os.environ["DISCORD_BOT_TOKEN"]`` is set and non-empty (Render or other cloud path), or
  * ``.env`` exists and contains a non-empty ``DISCORD_BOT_TOKEN=`` line
    (legacy plaintext install), or
  * ``.env.enc`` exists and is a valid DPAPI envelope (encrypted install).

When the function returns ``False``, the launcher invokes
``run_first_run_wizard(repo_root)`` which prints a header, reads the four
fields from stdin, writes the appropriate file, and returns ``True`` on
success or ``False`` when the operator aborts (Ctrl+C, empty token, etc.).
"""

from __future__ import annotations

import getpass
import os
import re
import secrets as secrets_module
import sys
from pathlib import Path
from typing import Optional


# Field names live in module scope so test-only imports can reuse them.
ENV_FILENAME = ".env"
ENC_FILENAME = ".env.enc"


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


def credentials_already_exist(repo_root: Path) -> bool:
    """Return ``True`` when the launcher should NOT run the wizard.

    The wizard is opt-out: any plausible credential source counts as
    "already set up" so an operator running the EXE after a manual ``.env``
    edit, after a previous wizard run, or on a cloud host with platform
    env vars never sees the prompt.
    """
    repo_root = Path(repo_root)

    # 1. Cloud / pre-set environment variable.
    if os.environ.get("DISCORD_BOT_TOKEN"):
        return True

    # 2. Plaintext .env carrying a non-empty token.
    env_path = repo_root / ENV_FILENAME
    if env_path.is_file():
        try:
            for raw_line in env_path.read_text(encoding="utf-8").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" not in line:
                    continue
                key, _, val = line.partition("=")
                if key.strip() == "DISCORD_BOT_TOKEN" and _strip_quotes(val.strip()):
                    return True
        except OSError:
            # Unreadable .env counts as "do not run the wizard"; the loader
            # will surface the read error itself.
            return True

    # 3. DPAPI-encrypted .env.enc on disk.
    enc_path = repo_root / ENC_FILENAME
    if enc_path.is_file():
        return True

    return False


def _strip_quotes(value: str) -> str:
    """Match ``utils.load_env_file``'s quote-handling so detection agrees with loading."""
    if (value.startswith('"') and value.endswith('"')) or (
        value.startswith("'") and value.endswith("'")
    ):
        return value[1:-1]
    return value


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------


_VALID_TOKEN_RE = re.compile(r"^[A-Za-z0-9._-]{20,}$")
_VALID_CLIENT_ID_RE = re.compile(r"^\d{17,20}$")


def _prompt_required(prompt: str, *, secret: bool, validator=None) -> Optional[str]:
    """Prompt until a non-empty (and optionally validator-passing) value is entered.

    Returns ``None`` when the operator aborts via Ctrl+C / Ctrl+D.
    """
    reader = getpass.getpass if secret else input
    for attempt in range(1, 6):
        try:
            value = reader(prompt).strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[!] Aborted by user.")
            return None
        if not value:
            print("    Value cannot be empty. Try again.")
            continue
        if validator is not None:
            ok, error_message = validator(value)
            if not ok:
                print(f"    {error_message}")
                continue
        return value
    print("[!] Too many invalid attempts; aborting wizard.")
    return None


def _validate_bot_token(value: str):
    if not _VALID_TOKEN_RE.match(value):
        return False, (
            "That does not look like a Discord bot token (expected 20+ "
            "characters, letters/digits/dot/dash/underscore). Re-copy the "
            "token from the Bot tab of your Discord application."
        )
    return True, ""


def _validate_client_id(value: str):
    if not _VALID_CLIENT_ID_RE.match(value):
        return False, (
            "Client ID must be a 17-20 digit number copied from the OAuth2 "
            "tab of your Discord application."
        )
    return True, ""


def _prompt_password_with_confirmation() -> Optional[str]:
    """Prompt for a password twice and return the plaintext when both match."""
    for attempt in range(1, 6):
        try:
            pwd = getpass.getpass(
                "Choose an admin password (min 8 chars, will be hashed): "
            ).strip()
            confirm = getpass.getpass("Confirm admin password: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n[!] Aborted by user.")
            return None
        if len(pwd) < 8:
            print("    Password must be at least 8 characters. Try again.")
            continue
        if pwd != confirm:
            print("    The two entries did not match. Try again.")
            continue
        return pwd
    print("[!] Too many invalid attempts; aborting wizard.")
    return None


def _prompt_optional(prompt: str) -> str:
    """Prompt for an optional field; return ``""`` on empty / abort."""
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return ""


# ---------------------------------------------------------------------------
# Wizard entry point
# ---------------------------------------------------------------------------


def run_first_run_wizard(repo_root: Path) -> bool:
    """Run the first-run console wizard. Returns ``True`` on success.

    The wizard is idempotent at the call-site level: the launcher should
    only call it when ``credentials_already_exist`` returned ``False``. The
    function itself does not double-check, so callers are responsible for
    not stomping a pre-existing ``.env`` or ``.env.enc``.
    """
    repo_root = Path(repo_root)

    print()
    print("=" * 60)
    print("            Aegis Suite — First-Run Setup Wizard")
    print("=" * 60)
    print(
        "No credentials were found on this install. This wizard will "
        "collect the four values\nthe bot needs and write them to an "
        "encrypted file on this machine. The values are\nbound to your "
        "Windows user account via DPAPI when available, so copying the\n"
        "encrypted file off this PC will NOT decrypt it."
    )
    print()
    print(
        "You will need:\n"
        "  1. Your Discord bot token (Discord Developer Portal -> Your\n"
        "     App -> Bot tab). IMPORTANT: Under the 'Bot' tab, you MUST\n"
        "     enable all 'Privileged Gateway Intents' (Presence Intent,\n"
        "     Server Members Intent, and Message Content Intent) or the bot\n"
        "     will fail to start or respond to commands.\n"
        "  2. Your application's Client ID (OAuth2 tab; a 17-20 digit\n"
        "     number).\n"
        "  3. A password you will use to log into the dashboard."
    )
    print()

    bot_token = _prompt_required(
        "Bot token (input hidden): ",
        secret=True,
        validator=_validate_bot_token,
    )
    if not bot_token:
        return False

    client_id = _prompt_required(
        "Application Client ID: ",
        secret=False,
        validator=_validate_client_id,
    )
    if not client_id:
        return False

    admin_password = _prompt_password_with_confirmation()
    if not admin_password:
        return False

    bot_api_url = _prompt_optional(
        "Public dashboard URL (optional, leave blank for local-only "
        "install) [default: blank]: "
    )

    # Hash the password right away so the plaintext never reaches disk.
    # Importing ``auth`` lazily (rather than at module top) lets the
    # wizard module be imported by tests that don't need the full
    # FastAPI / discord.py dependency stack.
    sys.path.insert(0, str(repo_root))
    import auth  # type: ignore  # noqa: WPS433 (intentional late import)

    admin_password_hash = auth.hash_password(admin_password)
    jwt_secret = secrets_module.token_hex(32)

    env_lines = [
        f"DISCORD_BOT_TOKEN={bot_token}",
        f"CLIENT_ID={client_id}",
        f"JWT_SECRET={jwt_secret}",
        f"ADMIN_PASSWORD_HASH={admin_password_hash}",
    ]
    if bot_api_url:
        env_lines.append(f"BOT_API_URL={bot_api_url}")
    plaintext_blob = "\n".join(env_lines) + "\n"

    # Persist the client_id to config.json as well so the dashboard's
    # "Invite Bot" button can build its OAuth URL. The bot token, password
    # hash, and JWT secret stay in .env / .env.enc only — config.json must
    # never carry credentials per the managed-hosting-migration contract.
    _persist_client_id_to_config(repo_root, client_id)

    return _persist_credentials(repo_root, plaintext_blob)


def _persist_client_id_to_config(repo_root: Path, client_id: str) -> None:
    """Write ``client_id`` into ``config.json`` so the dashboard sees it.

    The dashboard's ``GET /api/config`` endpoint reads the client_id from
    ``config.json`` (not the env), so the wizard has to mirror it there.
    A failure here is non-fatal — the dashboard will still start, the
    operator can paste the ID into the Settings tab manually.
    """
    import json
    config_path = repo_root / "config.json"
    try:
        if config_path.is_file():
            data = json.loads(config_path.read_text(encoding="utf-8"))
        else:
            data = {}
        data["client_id"] = client_id
        config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        print(f"[+] Saved client_id to {config_path.name}.")
    except Exception as exc:
        print(
            f"[!] Could not write client_id to {config_path.name}: {exc}. "
            "You can set it later from the dashboard's settings panel."
        )


def _persist_credentials(repo_root: Path, plaintext_blob: str) -> bool:
    """Write the credential blob to disk, encrypted via DPAPI when possible.

    Returns ``True`` when at least one of ``.env.enc`` or ``.env`` was
    successfully written; ``False`` otherwise (the launcher should refuse
    to start the bot in that case).
    """
    env_path = repo_root / ENV_FILENAME
    enc_path = repo_root / ENC_FILENAME

    # Always write the plaintext first — this is the source of truth that
    # ``encrypt_env_file`` consumes. We delete it after a successful
    # encryption so the cleartext lifetime on disk is as short as possible.
    try:
        env_path.write_text(plaintext_blob, encoding="utf-8")
    except OSError as exc:
        print(f"\n[-] Could not write {env_path}: {exc}")
        return False

    sys.path.insert(0, str(repo_root))
    try:
        import secret_store  # type: ignore  # noqa: WPS433
    except ImportError as exc:
        print(
            f"\n[!] Could not import secret_store ({exc}); leaving the "
            f"plaintext .env in place at {env_path}. The dashboard will "
            "still start."
        )
        return True

    if not secret_store.is_dpapi_available():
        print(
            "\n[!] Windows DPAPI is not available on this host. The "
            f"plaintext .env at {env_path} is the credential source. "
            "On Windows with pywin32 installed, the wizard would encrypt "
            "the file and delete the cleartext."
        )
        return True

    try:
        secret_store.encrypt_env_file(env_path, enc_path)
    except Exception as exc:  # pragma: no cover — defensive against pywin32 errors
        print(
            f"\n[!] Could not write {enc_path}: {exc}. The plaintext .env "
            f"at {env_path} is the credential source instead."
        )
        return True

    # Encryption worked. Remove the cleartext to honor the secret-store
    # contract that secrets at rest should be DPAPI-protected on Windows.
    try:
        env_path.unlink()
    except OSError as exc:
        print(
            f"\n[!] Could not delete the plaintext {env_path} after "
            f"encryption: {exc}. Delete it manually so credentials are "
            "not duplicated on disk."
        )

    print()
    print(f"[+] Credentials encrypted and written to {enc_path}.")
    print(
        "[+] You can re-run the wizard later by deleting that file. "
        "Use `python -m secret_store decrypt` to inspect it."
    )
    return True


# ---------------------------------------------------------------------------
# CLI entry point — `python -m first_run_wizard`
# ---------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> int:
    repo_root = Path(__file__).resolve().parent
    if credentials_already_exist(repo_root):
        print(
            "[+] Credentials already configured. Skipping wizard. To "
            "re-run, delete .env / .env.enc and re-launch."
        )
        return 0
    success = run_first_run_wizard(repo_root)
    return 0 if success else 1


if __name__ == "__main__":  # pragma: no cover — CLI entry
    raise SystemExit(main())
