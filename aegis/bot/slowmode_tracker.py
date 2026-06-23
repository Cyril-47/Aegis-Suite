import time
import logging
import asyncio
from collections import defaultdict, deque
from typing import Dict, Optional

logger = logging.getLogger("aegis.slowmode_tracker")


class SlowmodeTracker:
    """
    Unified Adaptive Slowmode Tracker.
    
    4 layers of intelligence:
    1. Dynamic Threshold (baseline * multiplier + floor)
    2. Unique Senders (anti-single-user-spam)
    3. Sustained Duration (anti-accidental-trigger)
    4. Progressive Escalation (anti-persistent-raid)
    """

    def __init__(self):
        self._channel_timestamps: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5000))
        self._channel_senders: Dict[str, deque] = defaultdict(lambda: deque(maxlen=5000))
        self._applied_slowmodes: Dict[str, float] = {}
        self._applied_values: Dict[str, int] = {}
        self._burst_start_times: Dict[str, float] = {}
        self._trigger_counts: Dict[str, list] = defaultdict(list)
        self._raid_threat_level: str = "normal"
        self._raid_threat_guild: str = None
        self._raid_threat_time: float = 0

    def record_message(self, channel_id: str, user_id: str = "unknown"):
        """Store a message timestamp and user."""
        now = time.time()
        self._channel_timestamps[channel_id].append(now)
        self._channel_senders[channel_id].append((now, user_id))

    def _get_rate(self, channel_id: str, window_seconds: int) -> float:
        """Calculate messages per second over a specific rolling window."""
        timestamps = self._channel_timestamps.get(channel_id)
        if not timestamps:
            return 0.0

        now = time.time()
        cutoff = now - window_seconds

        count = 0
        for ts in timestamps:
            if ts > cutoff:
                count += 1

        return count / window_seconds

    def _get_unique_senders(self, channel_id: str, window_seconds: int) -> int:
        """Get unique user count in window."""
        senders = self._channel_senders.get(channel_id)
        if not senders:
            return 0

        now = time.time()
        cutoff = now - window_seconds
        seen = set()
        for ts, uid in senders:
            if ts > cutoff:
                seen.add(uid)
        return len(seen)

    def get_rate(self, channel_id: str, window_seconds: int = 10) -> float:
        """Public method to get rate."""
        return self._get_rate(channel_id, window_seconds)

    def set_raid_threat(self, threat_level: str, guild_id: str = None):
        """Set raid threat level from AdaptiveRaidDetector."""
        self._raid_threat_level = threat_level
        self._raid_threat_guild = guild_id
        self._raid_threat_time = time.time()
        if threat_level in ["high", "critical"]:
            logger.warning("Raid threat level set to %s for guild %s", threat_level, guild_id)

    async def check_and_apply(self, guild, channel, slowmode_settings: dict):
        """Apply slowmode using the Unified Adaptive Algorithm."""
        channel_id = str(channel.id)
        if channel_id in slowmode_settings.get("whitelisted_channels", []):
            return

        # Raid hook: if threat level is high/critical, force slowmode immediately
        # Guild-scoped: only applies if threat is for THIS guild
        if (self._raid_threat_level in ["high", "critical"]
            and self._raid_threat_guild == str(guild.id)
            and (time.time() - self._raid_threat_time) < 300):
            # Respect cooldown even for raid hook
            now = time.time()
            last_applied = self._applied_slowmodes.get(channel_id, 0)
            if now - last_applied < slowmode_settings.get("cooldown_seconds", 30):
                return

            if channel.slowmode_delay == 0:
                try:
                    if guild.me.guild_permissions.manage_channels:
                        duration = 10 if self._raid_threat_level == "critical" else 5
                        await channel.edit(
                            slowmode_delay=duration,
                            reason="Raid Detector: %s threat level" % self._raid_threat_level
                        )
                        self._applied_slowmodes[channel_id] = now
                        self._applied_values[channel_id] = duration
                        logger.warning(
                            "Raid hook: Applied %ds slowmode to #%s (%s threat)",
                            duration, channel.name, self._raid_threat_level
                        )
                        asyncio.create_task(self._auto_remove_slowmode(channel, duration))
                except Exception as e:
                    logger.error("Raid hook failed for #%s: %s", channel.name, e)
            return

        # Normal slowmode logic (only runs if raid hook didn't apply)
        if not slowmode_settings.get("enabled", False):
            return

        # --- 1. MEASURE CONTEXT ---
        current_rate = self._get_rate(channel_id, 10)
        short_baseline = self._get_rate(channel_id, 300)   # 5 min
        long_baseline = self._get_rate(channel_id, 3600)   # 1 hour
        # Baseline drift protection: use minimum to prevent poisoning
        baseline_rate = min(short_baseline, long_baseline) if long_baseline > 0 else short_baseline
        unique_senders = self._get_unique_senders(channel_id, 10)

        # --- 2. DYNAMIC THRESHOLD ---
        member_count = getattr(guild, 'member_count', 100) or 100
        if member_count < 100:
            multiplier = 1.3
        elif member_count < 1000:
            multiplier = 1.6
        else:
            multiplier = 2.0

        dynamic_threshold = max(3.0, baseline_rate * multiplier)

        # Scaled unique sender requirement (stronger for larger floods)
        min_senders = max(3, int(current_rate / 10))

        # --- 3. THE DECISION ENGINE (6 Layers) ---
        triggered = False
        reason = ""

        # Layer 1: Absolute flood (30+ msg/s = true emergency, no questions asked)
        if current_rate >= 30:
            triggered = True
            reason = "Absolute flood (%.1f msg/s)" % current_rate

        # Layer 2: Baseline-aware flood (15+ msg/s on normally quiet channels)
        elif current_rate >= 15 and unique_senders >= 3 and baseline_rate < 5:
            triggered = True
            reason = "Baseline-aware flood (%.1f msg/s, baseline: %.1f, %d senders)" % (current_rate, baseline_rate, unique_senders)

        # Layer 3: Dynamic threshold check
        elif current_rate >= dynamic_threshold:
            # Layer 4: Sustained duration (must last 2+ seconds)
            if channel_id not in self._burst_start_times:
                self._burst_start_times[channel_id] = time.time()
            else:
                burst_duration = time.time() - self._burst_start_times[channel_id]
                if burst_duration >= 2.0:
                    # Layer 5: Unique senders (scaled requirement)
                    if unique_senders >= min_senders:
                        triggered = True
                        reason = "Sustained spike (%.1f >= %.1f, Senders: %d/%d)" % (current_rate, dynamic_threshold, unique_senders, min_senders)
        else:
            self._burst_start_times.pop(channel_id, None)

        if not triggered:
            return

        # --- 4. APPLY SLOWMODE ---
        now = time.time()
        cooldown_seconds = slowmode_settings.get("cooldown_seconds", 30)
        if now - self._applied_slowmodes.get(channel_id, 0) < cooldown_seconds:
            return

        if channel.slowmode_delay > 0:
            return

        # Progressive escalation: track triggers in 10-minute window
        self._trigger_counts[channel_id].append(now)
        cutoff = now - 600
        self._trigger_counts[channel_id] = [t for t in self._trigger_counts[channel_id] if t > cutoff]
        trigger_count = len(self._trigger_counts[channel_id])

        # Tiered duration with escalation
        if current_rate >= 30:
            duration = 10
        elif current_rate >= 15:
            duration = 5
        else:
            duration = 3

        # Progressive escalation
        if trigger_count >= 3:
            duration = max(duration, 10)
        elif trigger_count >= 2:
            duration = max(duration, 5)

        duration = min(duration, slowmode_settings.get("max_slowmode_duration", 10))

        try:
            if guild.me.guild_permissions.manage_channels:
                await channel.edit(
                    slowmode_delay=duration,
                    reason="Adaptive: %.1f msg/s (Threshold: %.1f, Trigger #%d)" % (current_rate, dynamic_threshold, trigger_count)
                )
                self._applied_slowmodes[channel_id] = now
                self._applied_values[channel_id] = duration

                logger.warning(
                    "Applied %ds slowmode to #%s (%.1f msg/s, Trigger #%d)",
                    duration, channel.name, current_rate, trigger_count
                )

                asyncio.create_task(self._auto_remove_slowmode(channel, duration))
        except Exception as e:
            logger.error("Failed to apply slowmode to #%s: %s", channel.name, e)

    async def _auto_remove_slowmode(self, channel, applied_duration: int):
        await asyncio.sleep(applied_duration * 3)
        channel_id = str(channel.id)
        try:
            expected = self._applied_values.get(channel_id)
            if channel.slowmode_delay > 0 and channel.slowmode_delay == expected:
                await channel.edit(
                    slowmode_delay=0,
                    reason="Adaptive Slowmode: burst passed, removing slowmode"
                )
                logger.info("Removed slowmode from #%s", channel.name)
            elif channel.slowmode_delay != expected:
                logger.info(
                    "Skipping auto-remove on #%s: slowmode changed from %ss to %ss (admin override?)",
                    channel.name, expected, channel.slowmode_delay
                )
        except Exception as e:
            logger.error("Failed to remove slowmode from #%s: %s", channel.name, e)

    def get_status(self, channel_id: str = None) -> dict:
        """Get current rate and baseline for debugging."""
        if channel_id:
            return {
                "current_rate_10s": self._get_rate(channel_id, 10),
                "baseline_rate_15min": self._get_rate(channel_id, 900),
                "unique_senders": self._get_unique_senders(channel_id, 10),
                "trigger_count": len(self._trigger_counts.get(channel_id, [])),
            }
        result = {}
        for ch_id in self._channel_timestamps:
            result[ch_id] = {
                "rate": self._get_rate(ch_id, 10),
                "baseline_15min": self._get_rate(ch_id, 900),
                "unique_senders": self._get_unique_senders(ch_id, 10),
            }
        return result


slowmode_tracker = SlowmodeTracker()
