"""Real-world admin override scenario test.

Simulates the exact scenario described:
  Admin sets 2hr slowmode -> Bot fires -> Bot's auto-remove must NOT destroy admin's.
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from aegis.bot.slowmode_tracker import SlowmodeTracker


class RealChannel:
    """Simulates a Discord channel with realistic slowmode behavior."""
    def __init__(self, ch_id, name, slowmode_delay=0):
        self.id = ch_id
        self.name = name
        self.slowmode_delay = slowmode_delay
        self.edit_log = []  # Track every edit call with reason

    async def edit(self, **kwargs):
        old = self.slowmode_delay
        self.slowmode_delay = kwargs.get("slowmode_delay", 0)
        self.edit_log.append({
            "old": old,
            "new": self.slowmode_delay,
            "reason": kwargs.get("reason", ""),
            "time": time.time(),
        })


class RealGuild:
    def __init__(self, can_manage=True):
        self.me = MagicMock()
        self.me.guild_permissions.manage_channels = can_manage


def record_burst(tracker, channel_id, count=50):
    """Record burst messages with multiple unique users."""
    for i in range(count):
        tracker.record_message(str(channel_id), f"user_{i % 10}")


def make_settings(**overrides):
    base = {
        "enabled": True,
        "burst_threshold": 3,
        "slowmode_duration": 5,
        "cooldown_seconds": 30,
        "whitelisted_channels": [],
    }
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# THE EXACT SCENARIO FROM THE BUG REPORT
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_exact_scenario_admin_2hr_bot_auto_remove():
    """Admin sets 2hr slowmode. Bot fires. Bot's auto-remove must NOT destroy admin's.

    Timeline:
      T+0s   Admin sets 7200s slowmode on #general
      T+0.1s Raid begins — 50 messages flood in
      T+0.2s Bot processes messages, tracker checks channel
      T+0.2s Bot sees slowmode_delay=7200, SKIPS (correct)
      T+15s  Auto-remove task fires (but no bot slowmode was set)
      T+15s  Admin's 7200s MUST still be intact
    """
    tracker = SlowmodeTracker()
    guild = RealGuild()
    channel = RealChannel(ch_id=50001, name="general", slowmode_delay=7200)
    settings = make_settings(burst_threshold=1.0, slowmode_duration=5)

    # T+0: Admin has already set 2hr slowmode
    assert channel.slowmode_delay == 7200

    # T+0.1: Raid — 50 messages flood in
    record_burst(tracker, channel.id)

    rate = tracker.get_rate(str(channel.id))
    assert rate >= 1.0, "Raid should exceed threshold"

    # T+0.2: Bot processes — should SKIP because admin slowmode is active
    await tracker.check_and_apply(guild, channel, settings)

    # Bot did NOT apply slowmode
    assert channel.slowmode_delay == 7200, "Admin's 2hr slowmode must not be touched"
    assert len(channel.edit_log) == 0, "Bot should not have called edit() at all"

    # Wait for auto-remove task to fire (5*3=15s)
    # Even if a task was somehow scheduled, it should not clear admin's
    await asyncio.sleep(16)

    assert channel.slowmode_delay == 7200, (
        f"Admin's 2hr slowmode was destroyed! Got {channel.slowmode_delay}s"
    )
    print(f"\n  [PASS] Admin 2hr slowmode preserved after raid: {channel.slowmode_delay}s")


# ---------------------------------------------------------------------------
# SCENARIO 2: Bot fires first, THEN admin changes it
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bot_fires_then_admin_overrides():
    """Bot applies 5s slowmode. Admin changes to 1hr. Auto-remove must preserve admin's.

    Timeline:
      T+0s   Raid hits, bot applies 5s slowmode
      T+0s   Auto-remove scheduled for T+15s
      T+2s   Admin sees bot's 5s, overrides with 3600s (1hr)
      T+15s  Auto-remove fires — sees 3600, NOT 5, SKIPS
      T+15s  Admin's 3600s intact
    """
    tracker = SlowmodeTracker()
    guild = RealGuild()
    channel = RealChannel(ch_id=50002, name="general")
    settings = make_settings(burst_threshold=1.0, slowmode_duration=5, cooldown_seconds=0)

    # T+0: Raid — bot applies 5s
    record_burst(tracker, channel.id)

    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 5
    assert len(channel.edit_log) == 1
    assert channel.edit_log[0]["new"] == 5

    # T+2: Admin overrides with 1hr
    await asyncio.sleep(2)
    await channel.edit(slowmode_delay=3600, reason="Admin override: need longer")
    assert channel.slowmode_delay == 3600

    # T+15: Auto-remove fires (5*3=15s from T+0)
    await asyncio.sleep(14)

    assert channel.slowmode_delay == 3600, (
        f"Auto-remove destroyed admin's 1hr! Got {channel.slowmode_delay}s"
    )

    # Verify auto-remove logged a skip
    bot_edits = [e for e in channel.edit_log if "Dynamic Slowmode" in e.get("reason", "")]
    admin_edits = [e for e in channel.edit_log if "Admin override" in e.get("reason", "")]
    assert len(bot_edits) == 1, f"Bot should have edited once, got {len(bot_edits)}"
    assert len(admin_edits) == 1, f"Admin should have edited once, got {len(admin_edits)}"
    print(f"\n  [PASS] Auto-remove preserved admin override: {channel.edit_log}")


# ---------------------------------------------------------------------------
# SCENARIO 3: Admin sets, removes, bot fires, admin overrides again
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_full_lifecycle():
    """Full real-world lifecycle: admin -> bot -> admin -> auto-remove.

    Timeline:
      T+0s    Admin sets 7200s
      T+0.5s  Admin removes it (slowmode_delay=0)
      T+1s    Raid hits, bot applies 5s
      T+3s    Admin changes to 1800s (30min)
      T+16s   Auto-remove fires — preserves admin's 1800s
    """
    tracker = SlowmodeTracker()
    guild = RealGuild()
    channel = RealChannel(ch_id=50003, name="general")
    settings = make_settings(burst_threshold=1.0, slowmode_duration=5, cooldown_seconds=0)

    # T+0: Admin sets 2hr
    await channel.edit(slowmode_delay=7200, reason="Admin: server event")
    assert channel.slowmode_delay == 7200

    # T+0.5: Admin removes it
    await asyncio.sleep(0.5)
    await channel.edit(slowmode_delay=0, reason="Admin: event over")
    assert channel.slowmode_delay == 0

    # T+1: Raid hits, bot applies 5s
    await asyncio.sleep(0.5)
    record_burst(tracker, channel.id)

    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 5

    # T+3: Admin changes to 30min
    await asyncio.sleep(2)
    await channel.edit(slowmode_delay=1800, reason="Admin: need longer")
    assert channel.slowmode_delay == 1800

    # T+16: Auto-remove fires (5*3=15s from T+1)
    await asyncio.sleep(14)

    assert channel.slowmode_delay == 1800, (
        f"Auto-remove destroyed admin's 30min! Got {channel.slowmode_delay}s"
    )

    # Verify full edit log
    assert len(channel.edit_log) == 4
    print(f"\n  [PASS] Full lifecycle:")
    for i, entry in enumerate(channel.edit_log):
        print(f"    Edit {i+1}: {entry['old']}s -> {entry['new']}s ({entry['reason']})")


# ---------------------------------------------------------------------------
# SCENARIO 4: Multiple channels, mixed admin/bot states
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_multi_channel_mixed_states():
    """5 channels with different admin states — each handled independently.

    Ch1: Admin has 7200s -> Bot skips
    Ch2: No admin slowmode -> Bot applies 5s -> Auto-remove clears
    Ch3: Admin had slowmode, removed -> Bot applies 5s -> Admin sets 3600s -> Preserved
    Ch4: Bot applies -> Admin removes -> Bot applies again
    Ch5: Admin always has slowmode -> Bot never touches
    """
    tracker = SlowmodeTracker()
    guild = RealGuild()
    settings = make_settings(burst_threshold=1.0, slowmode_duration=5, cooldown_seconds=0)

    ch1 = RealChannel(ch_id=60001, name="admin-2hr", slowmode_delay=7200)
    ch2 = RealChannel(ch_id=60002, name="no-admin")
    ch3 = RealChannel(ch_id=60003, name="admin-then-bot")
    ch4 = RealChannel(ch_id=60004, name="bot-admin-bot")
    ch5 = RealChannel(ch_id=60005, name="admin-always", slowmode_delay=3600)

    channels = [ch1, ch2, ch3, ch4, ch5]

    # Raid hits all channels
    for ch in channels:
        record_burst(tracker, ch.id)

    # Bot processes all
    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    # Ch1: Bot skipped (admin 7200 active)
    assert ch1.slowmode_delay == 7200
    # Ch2: Bot applied 5s
    assert ch2.slowmode_delay == 5
    # Ch3: Bot applied 5s (admin had removed)
    assert ch3.slowmode_delay == 5
    # Ch4: Bot applied 5s
    assert ch4.slowmode_delay == 5
    # Ch5: Bot skipped (admin 3600 active)
    assert ch5.slowmode_delay == 3600

    # Admin intervenes on Ch3 and Ch4
    await asyncio.sleep(2)
    await ch3.edit(slowmode_delay=3600, reason="Admin: need longer on ch3")
    await ch4.edit(slowmode_delay=0, reason="Admin: remove slowmode on ch4")

    # Wait for auto-remove (5*3=15s)
    await asyncio.sleep(14)

    # Ch1: Still admin's 7200
    assert ch1.slowmode_delay == 7200
    # Ch2: Auto-remove cleared bot's 5s
    assert ch2.slowmode_delay == 0
    # Ch3: Auto-remove preserved admin's 3600
    assert ch3.slowmode_delay == 3600
    # Ch4: Admin removed it, auto-remove sees 0 ≠ 5, skips
    assert ch4.slowmode_delay == 0
    # Ch5: Still admin's 3600
    assert ch5.slowmode_delay == 3600

    print(f"\n  [PASS] Multi-channel mixed states:")
    for ch in channels:
        edits = len(ch.edit_log)
        print(f"    #{ch.name}: {ch.slowmode_delay}s ({edits} edits)")


# ---------------------------------------------------------------------------
# SCENARIO 5: Bot via full on_message integration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_on_message_admin_override():
    """Full bot_manager.on_message flow with admin slowmode active."""
    mock_config = {
        "slowmode_settings": {
            "enabled": True,
            "burst_threshold": 1.0,
            "slowmode_duration": 5,
            "cooldown_seconds": 0,
            "whitelisted_channels": [],
        },
        "guild_configs": {},
        "auto_responders": [],
        "welcome_settings": {},
        "automod_settings": {"enabled": False},
    }

    with patch("aegis.bot.bot_manager.utils") as mock_utils:
        mock_utils.get_guild_slowmode_settings.return_value = mock_config["slowmode_settings"]
        mock_utils.get_guild_config.return_value = {}

        from aegis.bot.bot_manager import DiscordOptimizerBot

        bot = DiscordOptimizerBot.__new__(DiscordOptimizerBot)
        bot.config = mock_config
        bot.stats = {"messages_today": 0, "commands_today": 0, "joins_today": 0}
        bot._new_members = []
        bot.process_commands = AsyncMock()
        bot.check_stats_reset = MagicMock()
        bot._recent_messages = {}
        bot._message_times = {}
        bot._message_counts = {}

        # Channel has admin's 7200s slowmode
        channel = RealChannel(ch_id=70001, name="general", slowmode_delay=7200)

        guild = MagicMock()
        guild.id = 9999
        guild.me = MagicMock()
        guild.me.guild_permissions.manage_channels = True
        guild.text_channels = [channel]
        guild.get_member.return_value = MagicMock()

        # Send 30 messages through on_message (raid)
        for i in range(30):
            msg = MagicMock()
            msg.content = f"raid {i}"
            msg.author = MagicMock()
            msg.author.id = 80000 + i
            msg.author.bot = False
            msg.guild = guild
            msg.channel = channel
            msg.delete = AsyncMock()
            await bot.on_message(msg)

        # Bot should NOT have changed admin's slowmode
        assert channel.slowmode_delay == 7200, (
            f"Bot destroyed admin's slowmode! Got {channel.slowmode_delay}s"
        )

        # Wait for any auto-remove tasks
        await asyncio.sleep(16)

        assert channel.slowmode_delay == 7200, (
            f"Auto-remove destroyed admin's slowmode! Got {channel.slowmode_delay}s"
        )
        print(f"\n  [PASS] on_message + admin 2hr preserved: {channel.slowmode_delay}s")


# ---------------------------------------------------------------------------
# SCENARIO 6: Rapid admin changes during raid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rapid_admin_changes_during_raid():
    """Admin rapidly changes slowmode while raid is in progress.

    Timeline:
      T+0s    Raid begins
      T+0.1s  Bot applies 5s
      T+0.5s  Admin changes to 60s
      T+1s    Admin changes to 120s
      T+2s    Admin changes to 0 (removes)
      T+3s    Another raid burst, bot applies 5s
      T+4s    Admin changes to 7200s
      T+18s   Auto-remove fires — must preserve admin's 7200s
    """
    tracker = SlowmodeTracker()
    guild = RealGuild()
    channel = RealChannel(ch_id=80001, name="general")
    settings = make_settings(burst_threshold=1.0, slowmode_duration=5, cooldown_seconds=0)

    # T+0: First raid
    record_burst(tracker, channel.id)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 5

    # T+0.5: Admin changes to 60s
    await asyncio.sleep(0.5)
    await channel.edit(slowmode_delay=60, reason="Admin: adjusting")
    assert channel.slowmode_delay == 60

    # T+1: Admin changes to 120s
    await asyncio.sleep(0.5)
    await channel.edit(slowmode_delay=120, reason="Admin: longer")
    assert channel.slowmode_delay == 120

    # T+2: Admin removes
    await asyncio.sleep(1)
    await channel.edit(slowmode_delay=0, reason="Admin: removed")
    assert channel.slowmode_delay == 0

    # T+3: Second raid burst — bot applies again
    await asyncio.sleep(1)
    record_burst(tracker, channel.id)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 5

    # T+4: Admin changes to 2hr
    await asyncio.sleep(1)
    await channel.edit(slowmode_delay=7200, reason="Admin: 2hr for safety")
    assert channel.slowmode_delay == 7200

    # T+18: Auto-remove fires for the SECOND bot application (5*3=15s from T+3)
    await asyncio.sleep(15)

    assert channel.slowmode_delay == 7200, (
        f"Auto-remove destroyed admin's 2hr! Got {channel.slowmode_delay}s"
    )

    # Verify edit history
    print(f"\n  [PASS] Rapid admin changes during raid:")
    for i, entry in enumerate(channel.edit_log):
        print(f"    Edit {i+1}: {entry['old']}s -> {entry['new']}s ({entry['reason']})")
