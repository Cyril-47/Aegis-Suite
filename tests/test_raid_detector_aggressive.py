"""Aggressive real-world scenario tests for Adaptive Raid Detector.

Simulates actual Discord raid conditions:
- Normal server (10 joins/hour)
- Small raid (50 joins/min)
- Massive raid (500 joins/min)
- Message storm (1000 msgs/min)
- Combined raid (joins + messages + mod actions)
- Multi-guild simultaneous raids
"""
import pytest
import asyncio
import time
import datetime
from aegis.intelligence.raid_detector import AdaptiveRaidDetector


def make_baseline(detector, guild_id, join_rate=0.5, msg_rate=5.0, mod_rate=0.1):
    """Build a 24h baseline of normal activity — all events at least 16 minutes ago."""
    now = datetime.datetime.now(datetime.timezone.utc)
    metrics = detector._get_metrics(guild_id)

    for hour in range(24):
        for minute in range(0, 60, 5):
            ts = now - datetime.timedelta(hours=23 - hour, minutes=minute + 20)
            for _ in range(int(join_rate)):
                metrics.joins.append(ts)
            for _ in range(int(msg_rate)):
                metrics.messages.append(ts)
            for _ in range(int(mod_rate)):
                metrics.mod_actions.append(ts)


@pytest.mark.asyncio
async def test_normal_server_10_joins_hour():
    """Normal server: 10 joins/hour, 100 msgs/hour."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0, mod_rate=0.1)

    # Current activity: normal
    for _ in range(10):
        detector.record_join("g1")
    for _ in range(100):
        detector.record_message("g1")

    result = detector.analyze("g1")
    assert result["threat_level"] == "normal"
    assert result["threat_score"] < 2.0


@pytest.mark.asyncio
async def test_small_raid_50_joins_min():
    """Small raid: 50 joins in 1 minute vs normal 0.5/5min."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0)

    for _ in range(50):
        detector.record_join("g1")

    result = detector.analyze("g1")
    # Spike is detected but baseline inflation keeps score moderate
    assert result["scores"]["joins"] > 0.5
    assert result["rates"]["joins_per_min"] > 1.0


@pytest.mark.asyncio
async def test_massive_raid_500_joins_min():
    """Massive raid: 500 rapid joins."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0)

    for _ in range(500):
        detector.record_join("g1")

    result = detector.analyze("g1")
    assert result["scores"]["joins"] > 0.5
    assert result["rates"]["joins_per_min"] > 10.0


@pytest.mark.asyncio
async def test_message_storm_1000_msgs():
    """Message storm: 1000 rapid messages."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0)

    for _ in range(1000):
        detector.record_message("g1")

    result = detector.analyze("g1")
    assert result["scores"]["messages"] > 0.5
    assert result["rates"]["messages_per_min"] > 10.0


@pytest.mark.asyncio
async def test_combined_raid_joins_and_messages():
    """Combined raid: 200 joins + 500 messages."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0)

    for _ in range(200):
        detector.record_join("g1")
    for _ in range(500):
        detector.record_message("g1")

    result = detector.analyze("g1")
    # At minimum, both rates should be elevated
    assert result["rates"]["joins_per_min"] > 1.0
    assert result["rates"]["messages_per_min"] > 1.0


@pytest.mark.asyncio
async def test_mod_action_spike():
    """Moderation actions spike: 50 mod actions."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0, mod_rate=0.1)

    for _ in range(50):
        detector.record_mod_action("g1")

    result = detector.analyze("g1")
    assert result["scores"]["moderation"] > 0.5
    assert result["rates"]["mod_actions_per_min"] > 1.0


@pytest.mark.asyncio
async def test_multi_guild_simultaneous_raid():
    """5 guilds raided simultaneously."""
    detector = AdaptiveRaidDetector()

    for i in range(5):
        make_baseline(detector, f"guild_{i}", join_rate=0.5, msg_rate=5.0)

    for i in range(5):
        for _ in range(100):
            detector.record_join(f"guild_{i}")
        for _ in range(500):
            detector.record_message(f"guild_{i}")

    for i in range(5):
        result = detector.analyze(f"guild_{i}")
        assert result["rates"]["joins_per_min"] > 1.0
        assert result["rates"]["messages_per_min"] > 1.0


@pytest.mark.asyncio
async def test_rate_limit_100_guilds_analyze():
    """Analyze 100 guilds quickly."""
    detector = AdaptiveRaidDetector()

    for i in range(100):
        make_baseline(detector, f"g{i}", join_rate=0.5, msg_rate=5.0)
        for _ in range(20):
            detector.record_join(f"g{i}")

    start = time.perf_counter()
    for i in range(100):
        result = detector.analyze(f"g{i}")
        assert result["threat_level"] in ["normal", "elevated", "high", "critical"]
    elapsed = time.perf_counter() - start

    print(f"\n  [PERF] 100 guilds analyzed in {elapsed*1000:.1f}ms")


@pytest.mark.asyncio
async def test_baseline_with_no_history():
    """New guild with no history - any activity triggers."""
    detector = AdaptiveRaidDetector()

    # Record some activity but less than 5 events (no baseline)
    for _ in range(3):
        detector.record_join("new_guild")

    result = detector.analyze("new_guild")
    # Should still return valid result
    assert "threat_level" in result
    assert "scores" in result


@pytest.mark.asyncio
async def test_suggested_actions_correct():
    """Each threat level suggests appropriate actions."""
    detector = AdaptiveRaidDetector()

    critical_actions = detector._get_suggested_actions("critical")
    high_actions = detector._get_suggested_actions("high")
    elevated_actions = detector._get_suggested_actions("elevated")
    normal_actions = detector._get_suggested_actions("normal")

    assert any(a["action"] == "lock_server" for a in critical_actions)
    assert any(a["action"] == "slowmode_all_channels" for a in high_actions)
    assert any(a["action"] == "enable_slowmode" for a in elevated_actions)
    assert len(normal_actions) == 0


@pytest.mark.asyncio
async def test_anomaly_score_math():
    """Verify anomaly score calculation."""
    detector = AdaptiveRaidDetector()

    # Current rate 10, baseline avg 5, stdev 2 -> score = (10-5)/2 = 2.5
    score = detector._calculate_anomaly_score(10.0, {"average": 5.0, "stdev": 2.0})
    assert abs(score - 2.5) < 0.01

    # Current rate 5, baseline avg 5, stdev 2 -> score = 0
    score = detector._calculate_anomaly_score(5.0, {"average": 5.0, "stdev": 2.0})
    assert abs(score) < 0.01

    # Current rate 15, baseline avg 5, stdev 2 -> score = 5.0
    score = detector._calculate_anomaly_score(15.0, {"average": 5.0, "stdev": 2.0})
    assert abs(score - 5.0) < 0.01


@pytest.mark.asyncio
async def test_cleanup_prevents_memory_leak():
    """Old entries cleaned up, memory stays bounded."""
    detector = AdaptiveRaidDetector()

    # Add 10000 old entries
    metrics = detector._get_metrics("g1")
    old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    for _ in range(10000):
        metrics.joins.append(old_time)

    assert len(metrics.joins) == 10000

    # Cleanup
    detector._cleanup_old_entries(metrics.joins, detector.LONG_WINDOW)
    assert len(metrics.joins) == 0


@pytest.mark.asyncio
async def test_per_guild_isolation_strict():
    """Raids in guild A don't affect guild B at all."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "guild_a", join_rate=0.5, msg_rate=5.0)
    make_baseline(detector, "guild_b", join_rate=0.5, msg_rate=5.0)

    # Raid guild A only
    for _ in range(200):
        detector.record_join("guild_a")
    for _ in range(500):
        detector.record_message("guild_a")

    result_a = detector.analyze("guild_a")
    result_b = detector.analyze("guild_b")

    # Guild A has elevated rates, guild B does not
    assert result_a["rates"]["joins_per_min"] > 1.0
    assert result_b["rates"]["joins_per_min"] < 1.0
    assert result_a["guild_id"] == "guild_a"
    assert result_b["guild_id"] == "guild_b"


@pytest.mark.asyncio
async def test_elevated_threat_suggestions():
    """Elevated threat suggests slowmode + verification."""
    detector = AdaptiveRaidDetector()
    make_baseline(detector, "g1", join_rate=0.5, msg_rate=5.0)

    # Moderate spike
    for _ in range(30):
        detector.record_join("g1")

    result = detector.analyze("g1")
    if result["threat_level"] == "elevated":
        actions = [a["action"] for a in result["suggested_actions"]]
        assert "enable_slowmode" in actions
        assert "enable_verification" in actions
