import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path
from aegis.core.paths import Paths

# Thread-safe or simple global set of registered secrets
_registered_secrets = set()

# Regex pattern for Discord token (from design.md)
DISCORD_TOKEN_RE = re.compile(r'[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}')

# Regex pattern for key-value secrets (case-insensitive)
SECRET_KEY_RE = re.compile(
    r'(?i)\b(bot_token|discord_bot_token|jwt_secret|admin_password_hash|bot_api_url|client_secret|bearer|token)\b\s*[:=]\s*(["\']?)([^"\'\s]+)\2'
)


def register_secret(value: str) -> None:
    """Register a secret value to be globally redacted in logging output."""
    if value:
        _registered_secrets.add(value)


def redact_string(text: str) -> str:
    """Scrub known secrets and patterns from a string, replacing them with ***REDACTED***."""
    if not isinstance(text, str):
        return text

    # 1. Exact match redaction for registered secrets
    for secret in _registered_secrets:
        if secret:
            text = text.replace(secret, "***REDACTED***")

    # 2. Heuristic token regex redaction
    text = DISCORD_TOKEN_RE.sub("***REDACTED***", text)

    # 3. Heuristic secret key value redaction
    def repl(match: re.Match) -> str:
        full_match = match.group(0)
        val = match.group(3)
        
        # Locate the start and end of the value inside the full match
        start_val = match.start(3) - match.start(0)
        end_val = match.end(3) - match.start(0)
        return full_match[:start_val] + "***REDACTED***" + full_match[end_val:]

    text = SECRET_KEY_RE.sub(repl, text)
    return text


class RedactionFilter(logging.Filter):
    """Logging filter that redacts secrets from LogRecord messages, arguments, and traceback texts."""

    def filter(self, record: logging.LogRecord) -> bool:
        # Redact message and args
        if record.args:
            try:
                # Perform % formatting to combine msg and args so secrets in args are caught
                if isinstance(record.args, dict):
                    formatted_msg = str(record.msg) % record.args
                else:
                    args_tuple = record.args if isinstance(record.args, tuple) else (record.args,)
                    formatted_msg = str(record.msg) % args_tuple
            except Exception:
                # Fallback if formatting fails
                formatted_msg = f"{record.msg} {record.args}"
            
            record.msg = redact_string(formatted_msg)
            record.args = ()
        else:
            if isinstance(record.msg, str):
                record.msg = redact_string(record.msg)

        # Redact formatted traceback text if cached
        if record.exc_text:
            record.exc_text = redact_string(record.exc_text)
        elif record.exc_info:
            # Pre-format and redact to override default formatter formatting
            import traceback
            exc_text = "".join(traceback.format_exception(*record.exc_info))
            record.exc_text = redact_string(exc_text)

        # Redact stack info
        if record.stack_info:
            record.stack_info = redact_string(record.stack_info)

        return True


def setup_logging(paths: Paths) -> None:
    """Configures console and rotating file logging with global secret redaction."""
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    # Idempotent setup: Clear existing handlers first
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    redaction_filter = RedactionFilter()
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    # Configure Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(redaction_filter)
    root_logger.addHandler(console_handler)

    # Configure Rotating File Handlers (with fallback to console-only on failure)
    try:
        paths.log_file.parent.mkdir(parents=True, exist_ok=True)

        # Main log file
        info_handler = RotatingFileHandler(
            paths.log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8"
        )
        info_handler.setLevel(logging.INFO)
        info_handler.setFormatter(formatter)
        info_handler.addFilter(redaction_filter)
        root_logger.addHandler(info_handler)

        # Error log file
        err_handler = RotatingFileHandler(
            paths.err_log_file,
            maxBytes=5 * 1024 * 1024,  # 5MB
            backupCount=5,
            encoding="utf-8"
        )
        err_handler.setLevel(logging.ERROR)
        err_handler.setFormatter(formatter)
        err_handler.addFilter(redaction_filter)
        root_logger.addHandler(err_handler)

    except Exception as e:
        print(f"Logging setup warning: Failed to initialize file handlers ({e}). Falling back to console-only.")

    # Ensure uvicorn loggers propagate to root logger so their records are captured in aegis.log and redacted
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        u_logger = logging.getLogger(name)
        u_logger.propagate = True
        for h in list(u_logger.handlers):
            u_logger.removeHandler(h)


# Safe uvicorn access log formatting monkeypatch (to prevent crashes during non-standard logs to uvicorn.access)
try:
    import uvicorn.logging
    fallback_formatter = logging.Formatter('%(levelname)s: %(message)s')

    # 1. AccessFormatter
    orig_access = uvicorn.logging.AccessFormatter.formatMessage
    def safe_access_format(self, record):
        try:
            return orig_access(self, record)
        except Exception:
            return fallback_formatter.formatMessage(record)
    uvicorn.logging.AccessFormatter.formatMessage = safe_access_format

    # 2. DefaultFormatter
    orig_default = uvicorn.logging.DefaultFormatter.formatMessage
    def safe_default_format(self, record):
        try:
            return orig_default(self, record)
        except Exception:
            return fallback_formatter.formatMessage(record)
    uvicorn.logging.DefaultFormatter.formatMessage = safe_default_format
except Exception:
    pass
