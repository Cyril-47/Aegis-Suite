import time
from aegis.bot.anti_raid import AntiRaidEngine


def test_detects_mass_joins():
    engine = AntiRaidEngine(threshold=3, window_seconds=30)
    now = time.time()
    assert engine.record_join("guild1", "user1", now) is None
    assert engine.record_join("guild1", "user2", now + 5) is None
    assert engine.record_join("guild1", "user3", now + 10) is None
    result = engine.record_join("guild1", "user4", now + 15)
    assert result is not None
    assert result["join_count"] == 4
    assert result["guild_id"] == "guild1"


def test_ignores_joins_outside_window():
    engine = AntiRaidEngine(threshold=3, window_seconds=30)
    now = time.time()
    engine.record_join("guild1", "user1", now)
    engine.record_join("guild1", "user2", now + 5)
    result = engine.record_join("guild1", "user3", now + 60)
    assert result is None


def test_account_age_gate():
    from datetime import datetime, timezone, timedelta
    engine = AntiRaidEngine()
    created_at = datetime.now(timezone.utc) - timedelta(days=3)
    assert engine.check_account_age(created_at, min_age_days=7) is True
    created_at = datetime.now(timezone.utc) - timedelta(days=30)
    assert engine.check_account_age(created_at, min_age_days=7) is False


def test_suspicious_score():
    from datetime import datetime, timezone, timedelta
    engine = AntiRaidEngine()
    created_at = datetime.now(timezone.utc) - timedelta(days=2)
    score = engine.calculate_suspicious_score(
        account_created_at=created_at,
        is_default_avatar=True,
        username="user1234",
    )
    assert score >= 50


def test_suspicious_score_low_risk():
    from datetime import datetime, timezone, timedelta
    engine = AntiRaidEngine()
    created_at = datetime.now(timezone.utc) - timedelta(days=365)
    score = engine.calculate_suspicious_score(
        account_created_at=created_at,
        is_default_avatar=False,
        username="NormalUser",
    )
    assert score < 30


def test_separate_guilds_independent():
    engine = AntiRaidEngine(threshold=3, window_seconds=30)
    now = time.time()
    engine.record_join("guild1", "user1", now)
    engine.record_join("guild1", "user2", now + 5)
    engine.record_join("guild2", "user1", now)
    engine.record_join("guild2", "user2", now + 5)
    result1 = engine.record_join("guild1", "user3", now + 10)
    result2 = engine.record_join("guild2", "user3", now + 10)
    assert result1 is None
    assert result2 is None


def test_alert_response():
    engine = AntiRaidEngine()
    alerts = []
    engine.set_alert_callback(lambda guild_id, msg: alerts.append((guild_id, msg)))
    engine.execute_response("alert", "guild1", {"join_count": 10})
    assert len(alerts) == 1
    assert "guild1" in alerts[0][0]


def test_lockdown_response():
    engine = AntiRaidEngine()
    lockdowns = []
    engine.set_lockdown_callback(lambda guild_id, duration: lockdowns.append((guild_id, duration)))
    engine.execute_response("lockdown", "guild1", {"duration_seconds": 300})
    assert len(lockdowns) == 1
    assert lockdowns[0] == ("guild1", 300)


def test_passive_response_does_nothing():
    engine = AntiRaidEngine()
    alerts = []
    engine.set_alert_callback(lambda guild_id, msg: alerts.append(guild_id))
    engine.execute_response("passive", "guild1", {})
    assert len(alerts) == 0
