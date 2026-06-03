import re
from typing import Any, Dict, List, Union

# Case-insensitive set of keys whose values must be redacted
SECRET_KEYS = {
    "bot_token",
    "discord_bot_token",
    "jwt_secret",
    "admin_password_hash",
    "bot_api_url",
    "client_secret",
    "bearer",
    "token"
}

# Specific Discord token pattern
DISCORD_TOKEN_RE_SPECIFIC = re.compile(r'[a-zA-Z0-9_\-\.]{24,36}\.[a-zA-Z0-9_\-\.]{6}\.[a-zA-Z0-9_\-\.]{27,43}')
# Broad Discord token pattern
DISCORD_TOKEN_RE_BROAD = re.compile(r'[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{20,}')
# JWT pattern
JWT_RE = re.compile(r'eyJ[a-zA-Z0-9_-]{2,}\.[a-zA-Z0-9_-]{2,}\.[a-zA-Z0-9_-]{2,}')
# PBKDF2 pattern
PBKDF2_RE = re.compile(r'pbkdf2:sha256:[a-zA-Z0-9$:]+')

# Catch key-value assignments/pairs (case-insensitive keys)
ENV_VAR_RE = re.compile(
    r'(?i)(bot_token|discord_bot_token|jwt_secret|admin_password_hash|bot_api_url|client_secret|bearer|token|password|cookie|session|database_pwd|db_password|db_pass)\s*([=:])\s*([^\s,\'"\)]+|"[^"]*"|\'[^\']*\')'
)

# Catch database URLs with passwords
DB_URL_RE = re.compile(r'(?i)([a-z0-9]+):\/\/([^:\s@]+):([^@\s]+)@([^\s]+)')

# Catch JSON keys
JSON_SECRET_RE = re.compile(
    r'(?i)(["\']?)(bot_token|discord_bot_token|jwt_secret|admin_password_hash|bot_api_url|client_secret|bearer|token|password|cookie|session|database_pwd|db_password|db_pass)(["\']?)\s*:\s*([^\s,\'"\)\}]+|"[^"]*"|\'[^\']*\')'
)

def redact_text(text: str) -> str:
    """Sanitizes sensitive information from raw text."""
    if not isinstance(text, str):
        return text

    # Redact Discord tokens
    text = DISCORD_TOKEN_RE_SPECIFIC.sub("***REDACTED***", text)
    text = DISCORD_TOKEN_RE_BROAD.sub("***REDACTED***", text)

    # Redact JWTs
    text = JWT_RE.sub("***REDACTED***", text)

    # Redact PBKDF2 hashes
    text = PBKDF2_RE.sub("***REDACTED***", text)

    # Redact DB passwords in connection strings
    def db_repl(match):
        return f"{match.group(1)}://{match.group(2)}:***REDACTED***@{match.group(4)}"
    text = DB_URL_RE.sub(db_repl, text)

    # Redact key-value pairs (env or config-like)
    def env_repl(match):
        key = match.group(1)
        op = match.group(2)
        val = match.group(3)
        if val.startswith('"') and val.endswith('"'):
            return f"{key}{op}\"***REDACTED***\""
        elif val.startswith("'") and val.endswith("'"):
            return f"{key}{op}'***REDACTED***'"
        return f"{key}{op}***REDACTED***"
    text = ENV_VAR_RE.sub(env_repl, text)

    # Redact JSON properties
    def json_repl(match):
        q1 = match.group(1)
        key = match.group(2)
        q2 = match.group(3)
        val = match.group(4)
        if val.startswith('"') and val.endswith('"'):
            return f"{q1}{key}{q2}: \"***REDACTED***\""
        elif val.startswith("'") and val.endswith("'"):
            return f"{q1}{key}{q2}: '***REDACTED***'"
        return f"{q1}{key}{q2}: ***REDACTED***"
    text = JSON_SECRET_RE.sub(json_repl, text)

    return text

def sanitize(obj: Any) -> Any:
    """Recursively deep-copies and redacts secret values from the input object."""
    if isinstance(obj, dict):
        sanitized_dict = {}
        for k, v in obj.items():
            k_lower = str(k).lower()
            if k_lower in SECRET_KEYS:
                sanitized_dict[k] = "***REDACTED***"
            else:
                sanitized_dict[k] = sanitize(v)
        return sanitized_dict
    elif isinstance(obj, list):
        return [sanitize(item) for item in obj]
    elif isinstance(obj, str):
        return redact_text(obj)
    else:
        return obj

