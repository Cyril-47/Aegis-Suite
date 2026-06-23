"""Integration tests for adaptive slowmode."""
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


def inject_multi_user(tracker, channel_id, users_per_msg):
    """Inject messages from multiple users over 3 seconds."""
    now = time.time()
    for i in range(users_per_msg * 10):
        uid = "user_%d" % (i % users_per_msg)
        ts = now - 3.0 + i * 0.03
        tracker._channel_timestamps[str(channel_id)].append(ts)
        tracker._channel_senders[str(channel_id)].append((ts, uid))


@pytest.mark.asyncio
async def test_full_flow():
    """Dashboard enables -> User spams -> Bot applies slowmode."""
    tracker = SlowmodeTracker()
    guild = FakeGuild()
    channel = FakeChannel(ch_id=1001, name="general")
    settings = make_settings()
    inject_multi_user(tracker, channel.id, 5)
    await asyncio.sleep(3.5)
    # First call sets burst start
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    # Second call triggers
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3


@pytest.mark.asyncio
async def test_cooldown_auto_remove():
    """Cooldown blocks re-apply, auto-remove clears."""
    tracker = SlowmodeTracker()
    guild = FakeGuild()
    channel = FakeChannel(ch_id=1002, name="general")
    settings = make_settings(cooldown_seconds=30)

    inject_multi_user(tracker, channel.id, 5)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3

    inject_multi_user(tracker, channel.id, 5)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3

    await asyncio.sleep(10)
    assert channel.slowmode_delay == 0


@pytest.mark.asyncio
async def test_large_server_low_traffic():
    """Large server with low traffic doesn't trigger."""
    tracker = SlowmodeTracker()
    guild = FakeGuild(online=500)
    channel = FakeChannel(ch_id=1003, name="general")
    settings = make_settings()

    now = time.time()
    for i in range(300):
        tracker._channel_timestamps["1003"].append(now - 600 + i * (1/1))

    inject_multi_user(tracker, 1003, 2)

    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 0


@pytest.mark.asyncio
async def test_large_server_raid():
    """Large server raid: 10 msg/s triggers."""
    tracker = SlowmodeTracker()
    guild = FakeGuild(online=500)
    channel = FakeChannel(ch_id=1004, name="general")
    settings = make_settings()

    now = time.time()
    for i in range(600):
        tracker._channel_timestamps["1004"].append(now - 600 + i * 0.5)

    inject_multi_user(tracker, 1004, 10)

    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 3


@pytest.mark.asyncio
async def test_emergency_flood():
    """30+ msg/s triggers immediate response."""
    tracker = SlowmodeTracker()
    guild = FakeGuild()
    channel = FakeChannel(ch_id=1005, name="general")
    settings = make_settings()

    inject_multi_user(tracker, 1005, 30)

    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel, settings)
    assert channel.slowmode_delay == 10


@pytest.mark.asyncio
async def test_tiered_duration():
    """Duration scales with severity."""
    tracker = SlowmodeTracker()
    guild = FakeGuild()
    settings = make_settings()

    # Test 3s tier (3-14 msg/s)
    channel1 = FakeChannel(ch_id=2001, name="ch1")
    inject_multi_user(tracker, 2001, 5)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel1, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel1, settings)
    assert channel1.slowmode_delay == 3

    # Test 5s tier (15-29 msg/s)
    channel2 = FakeChannel(ch_id=2002, name="ch2")
    inject_multi_user(tracker, 2002, 20)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel2, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel2, settings)
    assert channel2.slowmode_delay == 5

    # Test 10s tier (30+ msg/s)
    channel3 = FakeChannel(ch_id=2003, name="ch3")
    inject_multi_user(tracker, 2003, 40)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel3, settings)
    await asyncio.sleep(3.5)
    await tracker.check_and_apply(guild, channel3, settings)
    assert channel3.slowmode_delay == 10
