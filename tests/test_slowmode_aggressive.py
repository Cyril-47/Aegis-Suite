"""Aggressive real-world scenario tests for adaptive slowmode."""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock
from aegis.bot.slowmode_tracker import SlowmodeTracker


class FakeChannel:
    def __init__(self, ch_id=111, name="general"):
        self.id = ch_id
        self.name = name
        self.slowmode_delay = 0
        self._edit_count = 0

    async def edit(self, **kwargs):
        self.slowmode_delay = kwargs.get("slowmode_delay", 0)
        self._edit_count += 1


class FakeGuild:
    def __init__(self, can_manage=True, online=5):
        self.id = 9999
        self.me = MagicMock()
        self.me.guild_permissions.manage_channels = can_manage
        self.approximate_presence_count = online
        self.member_count = online


def make_settings(**overrides):
    base = {
        "enabled": True,
        "burst_window_seconds": 10,
        "min_trigger_rate": 3.0,
        "slowmode_duration": 3,
        "max_slowmode_duration": 10,
        "cooldown_seconds": 0,
        "whitelisted_channels": [],
    }
    base.update(overrides)
    return base


def inject_messages(tracker, channel_id, count, user_id="user"):
    now = time.time()
    for i in range(count):
        tracker._channel_timestamps[str(channel_id)].append(now - 0.5 + i * 0.01)
        tracker._channel_senders[str(channel_id)].append((now - 0.5 + i * 0.01, user_id))


def inject_multi_user(tracker, channel_id, users_per_msg):
    """Inject messages from multiple users over 3 seconds."""
    now = time.time()
    for i in range(users_per_msg * 10):
        uid = "user_%d" % (i % users_per_msg)
        # Spread over 3 seconds to pass sustained duration check
        ts = now - 3.0 + i * 0.03
        tracker._channel_timestamps[str(channel_id)].append(ts)
        tracker._channel_senders[str(channel_id)].append((ts, uid))


@pytest.mark.asyncio
async def test_raid_triggers():
    """30 messages from 5 users triggers slowmode."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=2001, name="general")
    guild = FakeGuild()
    settings = make_settings()
    inject_multi_user(tracker, channel.id, 5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3


@pytest.mark.asyncio
async def test_raid_triggers():
    """30 messages from 5 users triggers slowmode."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=2001, name="general")
    guild = FakeGuild()
    settings = make_settings()
    inject_multi_user(tracker, channel.id, 5)
    # First call sets burst start time
    await tracker.check_and_apply(guild, channel, settings)
    # Wait 3+ seconds for sustained duration
    await asyncio.sleep(3.5)
    # Second call triggers
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3


@pytest.mark.asyncio
async def test_cooldown_blocks():
    """Second burst blocked by cooldown."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=2003, name="general")
    guild = FakeGuild()
    settings = make_settings(cooldown_seconds=30)
    inject_multi_user(tracker, channel.id, 5)
    await asyncio.sleep(3.5)
    # First call sets burst start
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    # Second call triggers
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3
    # Third call blocked by cooldown
    inject_multi_user(tracker, channel.id, 5)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3


@pytest.mark.asyncio
async def test_auto_remove():
    """Slowmode auto-removes after 3x duration."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=2008, name="general")
    guild = FakeGuild()
    settings = make_settings()
    inject_multi_user(tracker, channel.id, 5)
    await asyncio.sleep(3.5)
    # First call sets burst start
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    # Second call triggers
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3
    await asyncio.sleep(10)
    assert channel.slowmode_delay == 0


@pytest.mark.asyncio
async def test_multi_channel_raid():
    """5 channels raided simultaneously."""
    tracker = SlowmodeTracker()
    guild = FakeGuild()
    settings = make_settings()
    channels = [FakeChannel(ch_id=3000 + i, name="ch-%d" % i) for i in range(5)]
    for ch in channels:
        inject_multi_user(tracker, ch.id, 5)
    await asyncio.sleep(3.5)
    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)
    await asyncio.sleep(3.5)
    for ch in channels:
        await tracker.check_and_apply(guild, ch, settings)
    for ch in channels:
        assert ch.slowmode_delay == 3


@pytest.mark.asyncio
async def test_status():
    """get_status returns correct data."""
    tracker = SlowmodeTracker()
    inject_multi_user(tracker, "1001", 3)
    status = tracker.get_status("1001")
    assert "current_rate_10s" in status
    assert "baseline_rate_15min" in status
    assert "unique_senders" in status
    assert "trigger_count" in status


@pytest.mark.asyncio
async def test_raid_hook_critical():
    """Raid detector critical threat forces 10s slowmode."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=4001, name="general")
    guild = FakeGuild()
    settings = make_settings(enabled=False)

    # Set raid threat for THIS guild
    tracker.set_raid_threat("critical", str(guild.id))

    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 10


@pytest.mark.asyncio
async def test_raid_hook_high():
    """Raid detector high threat forces 5s slowmode."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=4002, name="general")
    guild = FakeGuild()
    settings = make_settings(enabled=False)

    tracker.set_raid_threat("high", str(guild.id))

    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 5


@pytest.mark.asyncio
async def test_raid_hook_normal_threat():
    """Normal threat does NOT trigger."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=4003, name="general")
    guild = FakeGuild()
    settings = make_settings(enabled=False)

    tracker.set_raid_threat("normal", str(guild.id))

    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 0


@pytest.mark.asyncio
async def test_raid_hook_respects_cooldown():
    """Raid hook respects cooldown."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=4004, name="general")
    guild = FakeGuild()
    settings = make_settings(cooldown_seconds=30)

    tracker.set_raid_threat("critical", str(guild.id))
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 10

    # Second raid hook should be blocked by cooldown
    channel.slowmode_delay = 0
    tracker.set_raid_threat("critical", str(guild.id))
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 0


@pytest.mark.asyncio
async def test_raid_hook_respects_admin():
    """Raid hook respects admin manual slowmode."""
    tracker = SlowmodeTracker()
    channel = FakeChannel(ch_id=4005, name="general")
    channel.slowmode_delay = 120
    guild = FakeGuild()
    settings = make_settings()

    tracker.set_raid_threat("critical", str(guild.id))

    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 120
