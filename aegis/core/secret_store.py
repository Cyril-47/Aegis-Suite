"""Encrypted secret storage for the Aegis Suite local Windows EXE deployment.

This module wraps Windows DPAPI (`win32crypt.CryptProtectData`) so the
maintainer's secrets — `DISCORD_BOT_TOKEN`, `JWT_SECRET`,
`ADMIN_PASSWORD_HASH`, `BOT_API_URL` — can live on disk in
`.env.enc` instead of plaintext `.env`.

Threat model
============
DPAPI encrypts under the current Windows user's credentials. The protected
file CANNOT be decrypted by:
  * a different Windows user account on the same machine,
  * the same account on a different machine,
  * an offline attacker who copies the file off the disk.

It CAN be decrypted by:
  * any process running as the same Windows user (this is intrinsic — the
    bot itself needs to read the secret to use it),
  * malware running with that user's privileges.

This is the standard tradeoff for desktop secret storage and matches what
password managers and Discord's own client use for token-at-rest. For
multi-user or transferable encryption, use the passphrase-based mode
(``mode="passphrase"``, future work).

Layout
======
The encrypted file is JSON with a magic header so the loader can refuse to
silently treat random bytes as a valid blob::

    {
      "magic": "AEGIS_DPAPI_V1",
      "ciphertext_b64": "<base64-encoded DPAPI ciphertext>"
    }

The plaintext is the same `KEY=VALUE` line format as `.env` so the parser
in `utils.load_env_file` can be reused after decryption.

Cross-platform fallback
=======================
On non-Windows hosts (Render Linux containers, CI runners), DPAPI
is unavailable. ``encrypt_env_file`` raises ``DPAPIUnavailableError``,
``decrypt_env_file`` returns ``None`` so the loader silently falls back
to ``.env`` plaintext or, in cloud deployments, the platform-injected
environment variables. This keeps the deployment path completely unchanged.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from typing import Optional

MAGIC = "AEGIS_DPAPI_V1"
ENC_DESCRIPTION = "Aegis Suite secrets"


class DPAPIUnavailableError(RuntimeError):
    """Raised when DPAPI cannot be used (non-Windows host or missing pywin32)."""


class CorruptedSecretFile(RuntimeError):
    """Raised when an encrypted secret file is malformed or signature-invalid."""


def is_dpapi_available() -> bool:
    """Return True iff this process can call CryptProtectData/CryptUnprotectData."""
    if sys.platform != "win32":
        return False
    try:
        import win32crypt  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return True


# ---------------------------------------------------------------------------
# Low-level encrypt / decrypt
# ---------------------------------------------------------------------------


def _dpapi_encrypt(plaintext: bytes) -> bytes:
    if not is_dpapi_available():
        raise DPAPIUnavailableError(
            "Windows DPAPI is not available on this host. Install pywin32 "
            "(`pip install pywin32`) on a Windows machine to use encrypted "
            "secret storage. On Render / self-hosted environments, set the secrets via the "
            "platform's environment variable UI instead."
        )
    import win32crypt  # type: ignore

    # CryptProtectData signature: (DataIn, DataDescr, OptionalEntropy,
    # Reserved, PromptStruct, Flags). Flags=0 means CRYPTPROTECT_LOCAL_MACHINE
    # is OFF, so the blob is bound to the current user (not the machine).
    blob = win32crypt.CryptProtectData(plaintext, ENC_DESCRIPTION, None, None, None, 0)
    return blob


def _dpapi_decrypt(ciphertext: bytes) -> bytes:
    if not is_dpapi_available():
        raise DPAPIUnavailableError(
            "Windows DPAPI is not available on this host."
        )
    import win32crypt  # type: ignore

    # CryptUnprotectData returns (description, plaintext_bytes).
    _description, plaintext = win32crypt.CryptUnprotectData(
        ciphertext, None, None, None, 0
    )
    return plaintext


# ---------------------------------------------------------------------------
# File-level helpers
# ---------------------------------------------------------------------------


def encrypt_env_file(plaintext_env_path: Path, encrypted_path: Path) -> Path:
    """Read ``plaintext_env_path`` and write the DPAPI-encrypted blob to ``encrypted_path``.

    Returns the path that was written. Raises ``DPAPIUnavailableError`` if
    DPAPI cannot be reached and ``FileNotFoundError`` if the source file is
    missing.
    """
    plaintext_env_path = Path(plaintext_env_path)
    encrypted_path = Path(encrypted_path)
    if not plaintext_env_path.is_file():
        raise FileNotFoundError(
            f"Source plaintext file not found: {plaintext_env_path}"
        )
    plaintext = plaintext_env_path.read_bytes()

    ciphertext = _dpapi_encrypt(plaintext)
    payload = {
        "magic": MAGIC,
        "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
    }
    encrypted_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return encrypted_path


def decrypt_env_file(encrypted_path: Path) -> Optional[bytes]:
    """Read ``encrypted_path`` and return decrypted plaintext bytes.

    Returns ``None`` when DPAPI is unavailable (non-Windows / missing
    pywin32) or when the file does not exist. Raises ``CorruptedSecretFile``
    when the file exists but the magic header or base64 is malformed.
    """
    encrypted_path = Path(encrypted_path)
    if not encrypted_path.is_file():
        return None
    if not is_dpapi_available():
        return None

    try:
        payload = json.loads(encrypted_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise CorruptedSecretFile(
            f"{encrypted_path} is not valid JSON: {exc}"
        ) from exc

    if not isinstance(payload, dict) or payload.get("magic") != MAGIC:
        raise CorruptedSecretFile(
            f"{encrypted_path} does not have the expected {MAGIC!r} magic header. "
            "Refusing to attempt decryption."
        )
    ciphertext_b64 = payload.get("ciphertext_b64")
    if not isinstance(ciphertext_b64, str):
        raise CorruptedSecretFile(
            f"{encrypted_path} is missing or has an invalid `ciphertext_b64` field."
        )
    try:
        ciphertext = base64.b64decode(ciphertext_b64.encode("ascii"))
    except (ValueError, UnicodeEncodeError) as exc:
        raise CorruptedSecretFile(
            f"{encrypted_path} `ciphertext_b64` is not valid base64: {exc}"
        ) from exc

    try:
        return _dpapi_decrypt(ciphertext)
    except Exception as exc:
        # The ctypes/win32crypt error messages are already descriptive
        # enough; re-raise with a clearer wrapper.
        raise CorruptedSecretFile(
            f"DPAPI rejected {encrypted_path}: {exc}. The file may have "
            "been encrypted by a different Windows user or on a different "
            "machine."
        ) from exc


# ---------------------------------------------------------------------------
# CLI entrypoints (`python -m secret_store ...`)
# ---------------------------------------------------------------------------


def _cli_encrypt(args) -> int:
    src = Path(args.source)
    dst = Path(args.dest)
    if not src.is_file():
        print(f"[-] Source file not found: {src}")
        return 1
    if not is_dpapi_available():
        print(
            "[-] Windows DPAPI is not available on this host. Encryption is "
            "only supported on Windows with pywin32 installed."
        )
        return 2
    encrypt_env_file(src, dst)
    print(f"[+] Encrypted {src} -> {dst}")
    if args.delete_source:
        try:
            src.unlink()
            print(f"[+] Deleted plaintext source {src}")
        except OSError as exc:
            print(f"[!] Could not delete plaintext source {src}: {exc}")
    else:
        print(
            f"[!] The plaintext file {src} is still on disk. Run the same "
            "command with `--delete-source` to remove it, or delete it "
            "manually once you have verified the bot starts correctly."
        )
    return 0


def _cli_decrypt(args) -> int:
    enc = Path(args.source)
    plaintext = decrypt_env_file(enc)
    if plaintext is None:
        print(f"[-] Could not decrypt {enc} (file missing or DPAPI unavailable)")
        return 1
    if args.dest:
        Path(args.dest).write_bytes(plaintext)
        print(f"[+] Wrote decrypted plaintext to {args.dest}")
    else:
        sys.stdout.buffer.write(plaintext)
    return 0


def _cli_rotate(args) -> int:
    """Decrypt + re-encrypt under the current Windows user.

    Useful after a user-credential password change or when migrating between
    user profiles on the same machine.
    """
    enc = Path(args.source)
    plaintext = decrypt_env_file(enc)
    if plaintext is None:
        print(f"[-] Could not decrypt {enc} (file missing or DPAPI unavailable)")
        return 1
    backup = enc.with_suffix(enc.suffix + ".bak")
    enc.replace(backup)
    try:
        ciphertext = _dpapi_encrypt(plaintext)
        payload = {
            "magic": MAGIC,
            "ciphertext_b64": base64.b64encode(ciphertext).decode("ascii"),
        }
        enc.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        # Restore the backup if anything went wrong before unlinking it.
        backup.replace(enc)
        raise
    backup.unlink(missing_ok=True)
    print(f"[+] Rotated DPAPI ciphertext for {enc}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="python -m secret_store",
        description=(
            "Encrypt and decrypt the Aegis Suite local .env file using "
            "Windows DPAPI. Cloud deployments (Render / self-hosted) should use "
            "the platform's environment variable UI instead and ignore this "
            "module."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    enc = sub.add_parser("encrypt", help="Encrypt a plaintext .env file")
    enc.add_argument("--source", default=".env")
    enc.add_argument("--dest", default=".env.enc")
    enc.add_argument(
        "--delete-source",
        action="store_true",
        help="Delete the plaintext .env after successful encryption.",
    )
    enc.set_defaults(func=_cli_encrypt)

    dec = sub.add_parser("decrypt", help="Decrypt a .env.enc file")
    dec.add_argument("--source", default=".env.enc")
    dec.add_argument(
        "--dest",
        default=None,
        help="Write plaintext to this path. Defaults to stdout.",
    )
    dec.set_defaults(func=_cli_decrypt)

    rot = sub.add_parser(
        "rotate",
        help="Re-encrypt a .env.enc file under the current Windows user.",
    )
    rot.add_argument("--source", default=".env.enc")
    rot.set_defaults(func=_cli_rotate)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    raise SystemExit(main())
