import re
import time
import logging
from datetime import datetime, timezone
from typing import Optional, Dict, List
from collections import defaultdict

SUSPICIOUS_USERNAME_PATTERN = re.compile(r'^user\d{4,}$', re.IGNORECASE)

logger = logging.getLogger("aegis.bot.anti_raid")


class AntiRaidEngine:
    """Detects mass-join raids using a sliding window algorithm."""

    def __init__(self, threshold: int = 5, window_seconds: int = 30):
        self._threshold = threshold
        self._window_seconds = window_seconds
        self._joins: Dict[str, List[float]] = defaultdict(list)
        self._alert_callback = None
        self._lockdown_callback = None
        self._verify_callback = None

    def record_join(self, guild_id: str, user_id: str, now: float = None) -> Optional[dict]:
        if now is None:
            now = time.time()
        guild_joins = self._joins[guild_id]
        cutoff = now - self._window_seconds
        guild_joins[:] = [t for t in guild_joins if t > cutoff]
        guild_joins.append(now)
        if len(guild_joins) > self._threshold:
            return {
                "type": "raid_detected",
                "guild_id": guild_id,
                "join_count": len(guild_joins),
                "window_seconds": self._window_seconds,
                "timestamp": now,
            }
        return None

    def reset_guild(self, guild_id: str):
        self._joins.pop(guild_id, None)

    def set_alert_callback(self, callback):
        self._alert_callback = callback

    def set_lockdown_callback(self, callback):
        self._lockdown_callback = callback

    def set_verify_callback(self, callback):
        self._verify_callback = callback

    def execute_response(self, mode: str, guild_id: str, context: dict):
        if mode == "passive":
            return
        elif mode == "alert":
            if self._alert_callback:
                join_count = context.get("join_count", 0)
                msg = f"Raid detected: {join_count} joins in {self._window_seconds}s"
                self._alert_callback(guild_id, msg)
        elif mode == "lockdown":
            if self._lockdown_callback:
                duration = context.get("duration_seconds", 300)
                self._lockdown_callback(guild_id, duration)
        elif mode == "auto_verify":
            if self._verify_callback:
                self._verify_callback(guild_id)

    def check_account_age(self, account_created_at: datetime, min_age_days: int = 7) -> bool:
        """Return True if account is younger than min_age_days (suspicious)."""
        now = datetime.now(timezone.utc)
        if account_created_at.tzinfo is None:
            account_created_at = account_created_at.replace(tzinfo=timezone.utc)
        age_days = (now - account_created_at).total_seconds() / 86400
        return age_days < min_age_days

    def calculate_suspicious_score(
        self,
        account_created_at: datetime,
        is_default_avatar: bool = False,
        username: str = "",
        is_raid_window: bool = False,
        first_msg_mention_count: int = 0,
    ) -> int:
        score = 0
        now = datetime.now(timezone.utc)
        if account_created_at.tzinfo is None:
            account_created_at = account_created_at.replace(tzinfo=timezone.utc)
        age_days = (now - account_created_at).total_seconds() / 86400
        if age_days < 7:
            score += 30
        elif age_days < 30:
            score += 15
        if is_raid_window:
            score += 25
        if is_default_avatar:
            score += 10
        if username and SUSPICIOUS_USERNAME_PATTERN.match(username):
            score += 20
        if first_msg_mention_count >= 5:
            score += 15
        return min(score, 100)
