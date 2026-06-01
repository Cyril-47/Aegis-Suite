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

# Regex for detecting Discord tokens in values
DISCORD_TOKEN_RE = re.compile(r'[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6}\.[A-Za-z0-9_-]{27,}')

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
        # Heuristic check for Discord token inside the string
        if DISCORD_TOKEN_RE.search(obj):
            return DISCORD_TOKEN_RE.sub("***REDACTED***", obj)
        return obj
    else:
        return obj
