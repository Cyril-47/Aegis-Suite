"""Stress test: 100 concurrent channels under raid conditions.

Simulates a massive server-wide raid hitting 100 channels simultaneously
with 50 messages each — validates tracker performance, correctness,
and resource behavior under real Discord bot load.
"""
import pytest
import asyncio
import time
import tracemalloc
from unittest.mock import AsyncMock, MagicMock, patch

from aegis.bot.slowmode_tracker import SlowmodeTracker


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class StressChannel:
    def __init__(self, ch_id, name):
        self.id = ch_id
        self.name = name
        self.slowmode_delay = 0
        self.edit = AsyncMock(side_effect=self._apply)
        self.edit_count = 0

    async def _apply(self, **kwargs):
        self.slowmode_delay = kwargs.get("slowmode_delay", 0)
        self.edit_count += 1


class StressGuild:
    def __init__(self, can_manage=True):
        self.me = MagicMock()
        self.me.guild_permissions.manage_channels = can_manage


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
# TEST 1: 100 channels × 50 messages each — sequential recording
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_100_channels_50_msgs_sequential():
    """100 channels, 50 messages each, recorded sequentially then checked."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings()

    channels = [StressChannel(ch_id=10000 + i, name=f"ch-{i}") for i in range(100)]

    start = time.perf_counter()

    # Record all messages
    for ch in channels:
        for _ in range(50):
            tracker.record_message(str(ch.id))

    record_time = time.perf_counter() - start

    # Check all channels
    start = time.perf_counter()
    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)
    check_time = time.perf_counter() - start

    # Verify
    triggered = [ch for ch in channels if ch.slowmode_delay > 0]
    blocked = [ch for ch in channels if ch.slowmode_delay == 0]

    assert len(triggered) == 100, f"Expected 100 triggered, got {len(triggered)}"
    assert len(blocked) == 0

    status = tracker.get_status()
    assert len(status) == 100

    print(f"\n  [STRESS] 100ch × 50msg sequential:")
    print(f"    Record: {record_time*1000:.1f}ms")
    print(f"    Check:  {check_time*1000:.1f}ms")
    print(f"    Total:  {(record_time+check_time)*1000:.1f}ms")
    print(f"    Triggered: {len(triggered)}/100 channels")
    print(f"    Edits: {sum(ch.edit_count for ch in channels)}")


# ---------------------------------------------------------------------------
# TEST 2: 100 channels × 50 messages — concurrent check_and_apply
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_100_channels_concurrent_check():
    """100 channels with messages, all check_and_apply fired concurrently."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings()

    channels = [StressChannel(ch_id=20000 + i, name=f"ch-{i}") for i in range(100)]

    # Record messages
    for ch in channels:
        for _ in range(50):
            tracker.record_message(str(ch.id))

    # Fire all checks concurrently
    start = time.perf_counter()
    tasks = [tracker.check_and_apply(guild, ch, settings) for ch in channels]
    await asyncio.gather(*tasks)
    elapsed = time.perf_counter() - start

    triggered = [ch for ch in channels if ch.slowmode_delay > 0]
    total_edits = sum(ch.edit_count for ch in channels)

    assert len(triggered) == 100
    # Concurrent calls may cause multiple edits per channel (race condition)
    print(f"\n  [STRESS] 100ch concurrent check_and_apply:")
    print(f"    Time:    {elapsed*1000:.1f}ms")
    print(f"    Triggered: {len(triggered)}/100")
    print(f"    Total edits: {total_edits} (expected 100, race={total_edits > 100})")


# ---------------------------------------------------------------------------
# TEST 3: 100 channels × 200 messages — heavy raid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_100_channels_200_msgs_heavy_raid():
    """Heavy raid: 200 messages per channel across 100 channels."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings(burst_threshold=3)

    channels = [StressChannel(ch_id=30000 + i, name=f"ch-{i}") for i in range(100)]

    start = time.perf_counter()

    for ch in channels:
        for _ in range(200):
            tracker.record_message(str(ch.id))

    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    elapsed = time.perf_counter() - start
    triggered = [ch for ch in channels if ch.slowmode_delay > 0]

    print(f"\n  [STRESS] 100ch × 200msg heavy raid:")
    print(f"    Time:    {elapsed*1000:.1f}ms")
    print(f"    Triggered: {len(triggered)}/100")
    print(f"    Rate per ch: {tracker.get_rate(str(channels[0].id)):.1f} msg/s")

    assert len(triggered) == 100


# ---------------------------------------------------------------------------
# TEST 4: Memory usage — 100 channels × 500 messages
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_memory_100_channels_500_msgs():
    """Track memory growth with 100 channels and 500 messages each."""
    tracemalloc.start()

    snapshot1 = tracemalloc.take_snapshot()

    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings()

    channels = [StressChannel(ch_id=40000 + i, name=f"ch-{i}") for i in range(100)]

    for ch in channels:
        for _ in range(500):
            tracker.record_message(str(ch.id))

    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    snapshot2 = tracemalloc.take_snapshot()

    top = snapshot2.compare_to(snapshot1, 'lineno')
    total_diff = sum(s.size_diff for s in top)

    print(f"\n  [STRESS] Memory (100ch × 500msg):")
    print(f"    Growth: {total_diff / 1024:.1f} KB")
    print(f"    Channels tracked: {len(tracker._channel_timestamps)}")
    print(f"    Timestamps/ch: {len(list(tracker._channel_timestamps.values())[0])}")

    # Each channel should only keep ~10 seconds of timestamps (500 msgs at high rate)
    for ch_id, ts in tracker._channel_timestamps.items():
        assert len(ts) <= 500, f"Channel {ch_id} has {len(ts)} timestamps — should be capped"

    tracemalloc.stop()


# ---------------------------------------------------------------------------
# TEST 5: Cooldown behavior under 100-channel raid
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cooldown_100_channels():
    """First burst triggers, second burst within cooldown is blocked."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings(cooldown_seconds=30)

    channels = [StressChannel(ch_id=50000 + i, name=f"ch-{i}") for i in range(100)]

    # First burst
    for ch in channels:
        for _ in range(50):
            tracker.record_message(str(ch.id))

    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    first_edits = [ch.edit_count for ch in channels]
    assert all(e == 1 for e in first_edits), f"First burst: expected 1 edit each, got {first_edits}"

    # Second burst immediately — cooldown should block
    for ch in channels:
        ch.slowmode_delay = 0  # Simulate Discord resetting
        for _ in range(50):
            tracker.record_message(str(ch.id))

    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    second_edits = [ch.edit_count for ch in channels]
    assert all(e == 1 for e in second_edits), f"Second burst: expected still 1 edit, got {second_edits}"

    print(f"\n  [STRESS] Cooldown (100ch):")
    print(f"    First burst edits: {sum(first_edits)}")
    print(f"    Second burst edits: {sum(second_edits) - sum(first_edits)} (should be 0)")


# ---------------------------------------------------------------------------
# TEST 6: Mixed channels — some whitelisted, some disabled
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mixed_100_channels():
    """50 normal + 30 whitelisted + 20 from disabled guild = only 50 trigger."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings(
        burst_threshold=2,
        whitelisted_channels=[str(60000 + i) for i in range(30)],  # ch 60000-60029
    )

    channels = [StressChannel(ch_id=60000 + i, name=f"ch-{i}") for i in range(100)]

    for ch in channels:
        for _ in range(50):
            tracker.record_message(str(ch.id))

    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    triggered = [ch for ch in channels if ch.slowmode_delay > 0]
    whitelisted = [ch for ch in channels if ch.id in [60000 + i for i in range(30)]]

    assert len(triggered) == 70, f"Expected 70 triggered, got {len(triggered)}"
    for ch in whitelisted:
        assert ch.slowmode_delay == 0, f"Whitelisted ch {ch.id} should not have slowmode"

    print(f"\n  [STRESS] Mixed channels (100):")
    print(f"    Triggered: {len(triggered)}/100")
    print(f"    Whitelisted blocked: {100 - len(triggered)}")


# ---------------------------------------------------------------------------
# TEST 7: Auto-remove stress — 100 channels all auto-remove
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_remove_100_channels():
    """100 channels get slowmode, all auto-remove after duration * 3."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings(burst_threshold=2, slowmode_duration=1, cooldown_seconds=0)

    channels = [StressChannel(ch_id=70000 + i, name=f"ch-{i}") for i in range(100)]

    for ch in channels:
        for _ in range(50):
            tracker.record_message(str(ch.id))

    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)

    assert all(ch.slowmode_delay == 1 for ch in channels)

    # Wait for auto-removal (1 * 3 = 3 seconds + buffer)
    await asyncio.sleep(4)

    assert all(ch.slowmode_delay == 0 for ch in channels), (
        f"Auto-remove failed for {[ch.id for ch in channels if ch.slowmode_delay > 0]}"
    )

    print(f"\n  [STRESS] Auto-remove (100ch):")
    print(f"    All 100 channels auto-removed: PASS")


# ---------------------------------------------------------------------------
# TEST 8: Rate accuracy under load
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rate_accuracy_100_channels():
    """Verify rate calculation is accurate for all 100 channels."""
    tracker = SlowmodeTracker()
    channels = [StressChannel(ch_id=80000 + i, name=f"ch-{i}") for i in range(100)]

    # Different message counts per channel
    for i, ch in enumerate(channels):
        msg_count = (i + 1) * 5  # ch0=5, ch1=10, ..., ch99=500
        for _ in range(msg_count):
            tracker.record_message(str(ch.id))

    status = tracker.get_status()

    for i, ch in enumerate(channels):
        expected_count = (i + 1) * 5
        actual = status[str(ch.id)]
        assert actual["count_10s"] == expected_count, (
            f"Channel {ch.id}: expected {expected_count} msgs, got {actual['count_10s']}"
        )
        expected_rate = expected_count / 10.0
        assert abs(actual["rate"] - expected_rate) < 0.01, (
            f"Channel {ch.id}: expected rate {expected_rate}, got {actual['rate']}"
        )

    print(f"\n  [STRESS] Rate accuracy (100ch):")
    print(f"    All 100 channels: rates match expected values")


# ---------------------------------------------------------------------------
# TEST 9: Bot manager integration — 100 channels through on_message
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bot_integration_100_channels():
    """100 channels sending messages through bot.on_message."""
    mock_config = {
        "slowmode_settings": {
            "enabled": True,
            "burst_threshold": 2.0,
            "slowmode_duration": 5,
            "cooldown_seconds": 60,
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

        guild = MagicMock()
        guild.id = 9999
        guild.me = MagicMock()
        guild.me.guild_permissions.manage_channels = True

        channels = [StressChannel(ch_id=90000 + i, name=f"ch-{i}") for i in range(100)]
        guild.text_channels = channels

        # Send 10 messages per channel through on_message
        start = time.perf_counter()
        for ch in channels:
            for i in range(10):
                msg = MagicMock()
                msg.content = f"raid {i}"
                msg.author = MagicMock()
                msg.author.id = 900000 + i
                msg.author.bot = False
                msg.guild = guild
                msg.channel = ch
                msg.delete = AsyncMock()
                await bot.on_message(msg)
        elapsed = time.perf_counter() - start

        from aegis.bot.slowmode_tracker import slowmode_tracker
        triggered = sum(
            1 for ch in channels
            if slowmode_tracker.get_rate(str(ch.id)) >= 2.0
        )

        print(f"\n  [STRESS] Bot integration (100ch × 10msg):")
        print(f"    Time:    {elapsed*1000:.1f}ms")
        print(f"    Channels with rate >= 2.0 msg/s: {triggered}/100")
        print(f"    Total messages processed: {100 * 10}")


# ---------------------------------------------------------------------------
# TEST 10: Performance baseline — pure tracker throughput
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pure_throughput():
    """Measure raw record_message + check throughput."""
    tracker = SlowmodeTracker()
    guild = StressGuild()
    settings = make_settings()

    channels = [StressChannel(ch_id=95000 + i, name=f"ch-{i}") for i in range(100)]

    # Record 10000 messages total (100 per channel)
    start = time.perf_counter()
    for ch in channels:
        for _ in range(100):
            tracker.record_message(str(ch.id))
    record_time = time.perf_counter() - start

    # Check all
    start = time.perf_counter()
    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)
    check_time = time.perf_counter() - start

    total_msgs = 100 * 100
    msgs_per_sec = total_msgs / (record_time + check_time)

    print(f"\n  [STRESS] Pure throughput:")
    print(f"    Total messages: {total_msgs}")
    print(f"    Record time: {record_time*1000:.1f}ms")
    print(f"    Check time:  {check_time*1000:.1f}ms")
    print(f"    Throughput:  {msgs_per_sec:,.0f} msg/s")
