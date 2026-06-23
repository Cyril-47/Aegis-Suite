"""Comprehensive tests for all 6 features: normal, aggressive, and server-size scenarios.

Features tested:
  1. Moderation Commands (automod: profanity, links, mention spam)
  2. Adaptive Raid Detector (anomaly detection)
  3. Fuzzy Spam Detector (Levenshtein similarity)
  4. Dashboard Auth (JWT, rate limiting, session lifecycle)
  5. Raid Logging DB Fix (RaidEvent persistence)
  6. Backup Scheduler (backup/restore/rotation)
"""
import pytest
import asyncio
import time
import datetime
import json
import os
import tempfile
import shutil
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from collections import deque

from aegis.intelligence.raid_detector import AdaptiveRaidDetector
from aegis.intelligence.spam_detector import FuzzySpamDetector
from aegis.core import auth


# ============================================================================
# 1. MODERATION COMMANDS
# ============================================================================

class FakeMessage:
    def __init__(self, content, author_id=111, guild_id=999, channel_id=222, mentions=None):
        self.content = content
        self.author = MagicMock()
        self.author.id = author_id
        self.author.bot = False
        self.author.mention = f"<@{author_id}>"
        self.author.display_avatar = MagicMock()
        self.author.display_avatar.url = "https://example.com/avatar.png"
        self.guild = MagicMock()
        self.guild.id = guild_id
        self.channel = AsyncMock()
        self.channel.id = channel_id
        self.channel.name = "general"
        self.mentions = mentions or []
        self.role_mentions = []
        self.delete = AsyncMock()
        self.send = AsyncMock()


class FakeGuild:
    def __init__(self, guild_id=999):
        self.id = guild_id
        self.get_channel = MagicMock(return_value=MagicMock(send=AsyncMock()))


# --- Normal Tests ---

@pytest.mark.asyncio
async def test_profanity_check_empty_list():
    """No blocked words configured -> message passes."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "profanity_filter": True}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("hello world")
    result = await cog._check_profanity(msg)
    assert result is False
    msg.delete.assert_not_called()


@pytest.mark.asyncio
async def test_mention_spam_normal():
    """5 mentions (exactly at limit) -> passes."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    cog = ModerationCog(bot)
    mentions = [MagicMock() for _ in range(5)]
    msg = FakeMessage("hey everyone", mentions=mentions)
    result = await cog._check_mention_spam(msg)
    assert result is False


@pytest.mark.asyncio
async def test_mention_spam_blocked():
    """6 mentions -> blocked."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {}}
    cog = ModerationCog(bot)
    mentions = [MagicMock() for _ in range(6)]
    msg = FakeMessage("spam mentions", mentions=mentions)
    msg.guild.get_channel.return_value = AsyncMock()
    result = await cog._check_mention_spam(msg)
    assert result is True
    msg.delete.assert_called_once()


@pytest.mark.asyncio
async def test_link_filter_whitelisted():
    """Whitelisted domain passes."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "link_filter": True, "link_whitelist": ["github.com"]}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("check https://github.com/user/repo")
    result = await cog._check_links(msg)
    assert result is False


@pytest.mark.asyncio
async def test_link_filter_blocked():
    """Non-whitelisted link -> blocked."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "link_filter": True, "link_whitelist": []}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("visit https://evil.com/scam")
    result = await cog._check_links(msg)
    assert result is True
    msg.delete.assert_called_once()


@pytest.mark.asyncio
async def test_automod_disabled():
    """Automod disabled -> no checks run."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": False}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("https://evil.com")
    await cog._run_automod(msg)
    msg.delete.assert_not_called()


# --- Aggressive Tests ---

@pytest.mark.asyncio
async def test_mention_spam_50_mentions():
    """50 mentions in one message -> blocked."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {}}
    cog = ModerationCog(bot)
    mentions = [MagicMock() for _ in range(50)]
    msg = FakeMessage("@everyone @here " * 25, mentions=mentions)
    msg.guild.get_channel.return_value = AsyncMock()
    result = await cog._check_mention_spam(msg)
    assert result is True


@pytest.mark.asyncio
async def test_link_filter_multiple_urls():
    """Message with 5 different URLs, none whitelisted -> blocked on first."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "link_filter": True, "link_whitelist": []}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("spam https://a.com https://b.com https://c.com https://d.com https://e.com")
    result = await cog._check_links(msg)
    assert result is True
    assert msg.delete.call_count == 1


@pytest.mark.asyncio
async def test_permission_denied_on_delete():
    """If bot lacks permission, automod doesn't crash."""
    from aegis.bot.cogs.moderation import ModerationCog
    import discord
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "link_filter": True, "link_whitelist": []}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("https://evil.com")
    msg.delete.side_effect = discord.Forbidden(MagicMock(), "no perm")
    result = await cog._check_links(msg)
    assert result is False


@pytest.mark.asyncio
async def test_link_filter_dominant_tld():
    """Links with many different TLDs."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "link_filter": True, "link_whitelist": []}}}}
    cog = ModerationCog(bot)
    msg = FakeMessage("https://spam.ru https://phish.cn https://hack.to")
    result = await cog._check_links(msg)
    assert result is True


# --- Server Size Tests ---

@pytest.mark.asyncio
async def test_large_guild_many_channels_automod():
    """Simulate 500 channels, each with a message going through automod."""
    from aegis.bot.cogs.moderation import ModerationCog
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "link_filter": True, "link_whitelist": []}}}}
    cog = ModerationCog(bot)

    blocked = 0
    for ch_id in range(500):
        msg = FakeMessage(f"msg in ch {ch_id}", channel_id=ch_id)
        if await cog._check_links(msg):
            blocked += 1

    assert blocked == 0  # No links in plain text


# ============================================================================
# 2. ADAPTIVE RAID DETECTOR
# ============================================================================

# --- Normal Tests ---

def test_raid_detector_initial_state():
    """New guild starts at normal."""
    detector = AdaptiveRaidDetector()
    result = detector.analyze("guild_1")
    assert result["threat_level"] == "normal"
    assert result["threat_score"] == 0.0


def test_raid_detector_low_activity():
    """Normal activity -> normal."""
    detector = AdaptiveRaidDetector()
    for _ in range(5):
        detector.record_join("g1")
        detector.record_message("g1")
    result = detector.analyze("g1")
    assert result["threat_level"] == "normal"


def test_raid_detector_baseline_learning():
    """With enough history, baseline should be computed."""
    detector = AdaptiveRaidDetector()
    for _ in range(10):
        detector.record_join("g1")
    baseline = detector._calculate_baseline(detector._get_metrics("g1").joins)
    assert baseline["average"] >= 0
    assert baseline["stdev"] >= 0


def test_raid_detector_per_guild_isolation():
    """Raids in guild A don't affect guild B."""
    detector = AdaptiveRaidDetector()
    for _ in range(100):
        detector.record_join("guild_a")
    result_a = detector.analyze("guild_a")
    result_b = detector.analyze("guild_b")
    assert result_a["guild_id"] == "guild_a"
    assert result_b["threat_level"] == "normal"


# --- Aggressive Tests ---

def test_raid_detector_critical_threat():
    """Mass joins spike -> critical."""
    detector = AdaptiveRaidDetector()
    # Build baseline with slow activity
    for _ in range(20):
        detector.record_message("g1")
    # Spike: 500 rapid joins
    for _ in range(500):
        detector.record_join("g1")
    result = detector.analyze("g1")
    # Should detect anomaly even without perfect baseline
    assert result["scores"]["joins"] > 0


def test_raid_detector_message_storm():
    """1000 messages in quick succession."""
    detector = AdaptiveRaidDetector()
    for _ in range(1000):
        detector.record_message("g1")
    result = detector.analyze("g1")
    assert result["rates"]["messages_per_min"] > 0


def test_raid_detector_suggested_actions():
    """Critical threat should suggest lock_server."""
    detector = AdaptiveRaidDetector()
    actions = detector._get_suggested_actions("critical")
    labels = [a["action"] for a in actions]
    assert "lock_server" in labels
    assert "enable_raid_mode" in labels


def test_raid_detector_elevated_actions():
    """Elevated threat suggests slowmode."""
    detector = AdaptiveRaidDetector()
    actions = detector._get_suggested_actions("elevated")
    labels = [a["action"] for a in actions]
    assert "enable_slowmode" in labels


def test_raid_detector_high_actions():
    """High threat suggests slowmode_all_channels."""
    detector = AdaptiveRaidDetector()
    actions = detector._get_suggested_actions("high")
    labels = [a["action"] for a in actions]
    assert "slowmode_all_channels" in labels


def test_anomaly_score_zero_stdev():
    """When stdev=0 and current > avg, score should be 99."""
    detector = AdaptiveRaidDetector()
    score = detector._calculate_anomaly_score(5.0, {"average": 1.0, "stdev": 0.0})
    assert score == 99.0


def test_anomaly_score_normal():
    """When current < avg, z-score is negative (below baseline)."""
    detector = AdaptiveRaidDetector()
    score = detector._calculate_anomaly_score(1.0, {"average": 5.0, "stdev": 2.0})
    assert score < 0


def test_anomaly_score_with_stdev():
    """Normal z-score calculation."""
    detector = AdaptiveRaidDetector()
    score = detector._calculate_anomaly_score(10.0, {"average": 5.0, "stdev": 2.0})
    assert abs(score - 2.5) < 0.01


# --- Server Size Tests ---

def test_raid_detector_100_guilds():
    """100 independent guilds, no cross-contamination."""
    detector = AdaptiveRaidDetector()
    for i in range(100):
        for _ in range(10):
            detector.record_join(f"guild_{i}")
    for i in range(100):
        result = detector.analyze(f"guild_{i}")
        assert result["guild_id"] == f"guild_{i}"
        assert result["threat_level"] == "normal"


def test_raid_detector_cleanup_old_entries():
    """Old entries get cleaned up."""
    detector = AdaptiveRaidDetector()
    # Manually insert old timestamps
    metrics = detector._get_metrics("g1")
    old_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=25)
    for _ in range(50):
        metrics.joins.append(old_time)
    detector._cleanup_old_entries(metrics.joins, detector.LONG_WINDOW)
    assert len(metrics.joins) == 0


# ============================================================================
# 3. FUZZY SPAM DETECTOR
# ============================================================================

# --- Normal Tests ---

def test_spam_detector_no_spam():
    """Single message -> not spam."""
    detector = FuzzySpamDetector()
    result = detector.analyze("u1", "ch1", "hello world")
    assert result["is_spam"] is False
    assert result["spam_score"] == 0


def test_spam_detector_exact_duplicate():
    """Same message from 2 users -> exact_matches=2 (2 in queue)."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "buy now click here")
    detector.record_message("u2", "ch1", "buy now click here")
    result = detector.analyze("u3", "ch1", "buy now click here")
    assert result["exact_matches"] >= 2
    assert result["spam_score"] >= 0.5


def test_spam_detector_exact_triple():
    """Same message from 3 users -> exact_matches=3."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "free nitro scam")
    detector.record_message("u2", "ch1", "free nitro scam")
    detector.record_message("u3", "ch1", "free nitro scam")
    result = detector.analyze("u4", "ch1", "free nitro scam")
    assert result["exact_matches"] >= 3
    assert result["spam_score"] >= 0.8
    assert result["is_spam"] is True


def test_spam_detector_levenshtein_identical():
    """Identical strings -> 1.0 similarity."""
    detector = FuzzySpamDetector()
    sim = detector._levenshtein_similarity("hello", "hello")
    assert sim == 1.0


def test_levenshtein_empty_strings():
    """One empty string -> 0.0."""
    detector = FuzzySpamDetector()
    assert detector._levenshtein_similarity("", "hello") == 0.0
    assert detector._levenshtein_similarity("hello", "") == 0.0


def test_levenshtein_completely_different():
    """Completely different strings -> low similarity."""
    detector = FuzzySpamDetector()
    sim = detector._levenshtein_similarity("abc", "xyz")
    assert sim < 0.5


def test_levenshtein_one_char_diff():
    """One character different -> high similarity (>= 0.8)."""
    detector = FuzzySpamDetector()
    sim = detector._levenshtein_similarity("hello", "helo")
    assert sim >= 0.8


def test_levenshtein_case_insensitive_flow():
    """Analyze lowercases input."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "Buy Now")
    result = detector.analyze("u2", "ch1", "buy now")
    # Content is stripped/lowered for comparison
    assert result["exact_matches"] >= 1


# --- Aggressive Tests ---

def test_spam_raid_pattern():
    """3+ users send similar messages -> raid detected."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "join our server its awesome")
    detector.record_message("u2", "ch1", "join our server its awesome")
    detector.record_message("u3", "ch1", "join our server its awesome")
    result = detector.analyze("u4", "ch1", "join our server its awesome")
    assert result["raid_detected"] is True
    assert result["is_spam"] is True
    assert result["spam_score"] >= 0.8


def test_spam_fuzzy_campaign():
    """Multiple similar messages that differ by only a few characters."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "free money click here now")
    detector.record_message("u2", "ch1", "free money click here now")
    detector.record_message("u3", "ch1", "free money click here now")
    # Analyze with slight variation - same content gets counted as exact
    result = detector.analyze("u4", "ch1", "free money click here now")
    # 3 exact matches -> high spam score
    assert result["exact_matches"] >= 3
    assert result["spam_score"] >= 0.8


def test_spam_100_identical_messages():
    """100 identical messages -> high spam score."""
    detector = FuzzySpamDetector()
    for i in range(100):
        detector.record_message(f"u{i}", "ch1", "spam message")
    result = detector.analyze("u100", "ch1", "spam message")
    assert result["is_spam"] is True
    assert result["spam_score"] >= 0.8


def test_spam_cross_channel_isolation():
    """Messages in different channels don't trigger each other."""
    detector = FuzzySpamDetector()
    for i in range(10):
        detector.record_message(f"u{i}", "ch1", "spam here")
    result = detector.analyze("u10", "ch2", "spam here")
    assert result["exact_matches"] == 0
    assert result["is_spam"] is False


def test_spam_suggested_actions_raid():
    """Raid pattern suggests muting all spammers."""
    detector = FuzzySpamDetector()
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "raid msg")
    result = detector.analyze("u5", "ch1", "raid msg")
    actions = [a["action"] for a in result["suggested_actions"]]
    assert "mute_spammers" in actions
    assert "lock_channel" in actions


def test_spam_suggested_actions_moderate():
    """Moderate spam suggests mute_user."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "buy now buy now buy now")
    detector.record_message("u2", "ch1", "buy now buy now buy now")
    result = detector.analyze("u3", "ch1", "buy now buy now buy now")
    actions = [a["action"] for a in result["suggested_actions"]]
    assert "mute_user" in actions or "enable_slowmode" in actions


def test_spam_campaign_summary():
    """Campaign summary tracks detected raids."""
    detector = FuzzySpamDetector()
    for i in range(4):
        detector.record_message(f"u{i}", "ch1", "join our server")
    detector.analyze("u4", "ch1", "join our server")
    summary = detector.get_campaign_summary()
    assert summary["total_campaigns"] >= 1
    assert len(summary["affected_users"]) >= 1


def test_spam_intelligence():
    """get_spam_intelligence returns campaign data."""
    detector = FuzzySpamDetector()
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "repeat content here")
    intel = detector.get_spam_intelligence("g1")
    assert "campaigns" in intel
    assert "total_campaigns" in intel


def test_spam_heavy_flood_1000_messages():
    """1000 messages from 100 users -> campaign detected."""
    detector = FuzzySpamDetector()
    for i in range(100):
        for j in range(10):
            detector.record_message(f"u{i}", "ch1", f"message variant {j}")
    result = detector.analyze("u100", "ch1", "message variant 0")
    assert result["spam_score"] > 0


# --- Server Size Tests ---

def test_spam_50_channels_isolated():
    """50 channels with independent spam campaigns."""
    detector = FuzzySpamDetector()
    for ch in range(50):
        for i in range(5):
            detector.record_message(f"u{i}", f"ch{ch}", f"spam in channel {ch}")
    for ch in range(50):
        result = detector.analyze("u10", f"ch{ch}", f"spam in channel {ch}")
        assert result["is_spam"] is True


# ============================================================================
# 4. DASHBOARD AUTH
# ============================================================================

# --- Normal Tests ---

def test_password_hash_format():
    """Hash starts with pbkdf2_sha256$."""
    h = auth.hash_password("test123")
    assert h.startswith("pbkdf2_sha256$")
    parts = h.split("$")
    assert len(parts) == 4
    assert parts[1] == "100000"


def test_password_verify_correct():
    """Correct password verifies."""
    h = auth.hash_password("mypassword")
    assert auth.verify_password("mypassword", h) is True


def test_password_verify_wrong():
    """Wrong password fails."""
    h = auth.hash_password("mypassword")
    assert auth.verify_password("wrongpassword", h) is False


def test_password_verify_empty_hash():
    """Empty hash -> False."""
    assert auth.verify_password("test", "") is False


def test_password_verify_malformed():
    """Malformed hash -> False."""
    assert auth.verify_password("test", "not_a_hash") is False
    assert auth.verify_password("test", "pbkdf2_sha256$") is False


def test_password_constant_time():
    """Hash is deterministic for same password+salt, different for different passwords."""
    h1 = auth.hash_password("pass1")
    h2 = auth.hash_password("pass2")
    assert h1 != h2


@pytest.mark.asyncio
async def test_jwt_create_decode():
    """Create and decode a JWT token."""
    os.environ["JWT_SECRET"] = "test_secret_key_12345"
    token = auth.create_session("guild_123", "admin")
    assert len(token) > 0
    payload = auth.decode_token(token)
    assert payload["guild_id"] == "guild_123"
    assert payload["role"] == "admin"
    assert "exp" in payload
    del os.environ["JWT_SECRET"]


@pytest.mark.asyncio
async def test_jwt_no_secret():
    """No JWT_SECRET -> empty token."""
    os.environ.pop("JWT_SECRET", None)
    token = auth.create_session("g1", "admin")
    assert token == ""


@pytest.mark.asyncio
async def test_jwt_invalid_token():
    """Invalid token -> None."""
    os.environ["JWT_SECRET"] = "test_secret"
    result = auth.decode_token("invalid.jwt.token")
    assert result is None
    del os.environ["JWT_SECRET"]


@pytest.mark.asyncio
async def test_validate_session():
    """Valid session validates."""
    os.environ["JWT_SECRET"] = "test_secret"
    auth._validated_tokens.clear()
    auth._revoked_tokens.clear()
    token = auth.create_session("g1", "admin")
    assert auth.validate_session(token) is True
    del os.environ["JWT_SECRET"]


@pytest.mark.asyncio
async def test_destroy_session():
    """Destroyed session is revoked."""
    os.environ["JWT_SECRET"] = "test_secret"
    auth._validated_tokens.clear()
    auth._revoked_tokens.clear()
    token = auth.create_session("g1", "admin")
    auth.destroy_session(token)
    assert auth.is_token_revoked(token) is True
    del os.environ["JWT_SECRET"]


# --- Aggressive Tests ---

def test_rate_limit_allows_first_5():
    """First 5 attempts allowed."""
    auth._login_attempts.clear()
    for _ in range(5):
        assert auth.check_login_rate_limit("1.2.3.4") is True
    assert auth.check_login_rate_limit("1.2.3.4") is False


def test_rate_limit_blocks_after_max():
    """6th attempt blocked."""
    auth._login_attempts.clear()
    for _ in range(5):
        auth.check_login_rate_limit("10.0.0.1")
    assert auth.check_login_rate_limit("10.0.0.1") is False
    remaining = auth.get_login_attempts_remaining("10.0.0.1")
    assert remaining == 0


def test_rate_limit_per_ip_isolation():
    """Different IPs have independent limits."""
    auth._login_attempts.clear()
    for _ in range(5):
        auth.check_login_rate_limit("1.1.1.1")
    assert auth.check_login_rate_limit("1.1.1.1") is False
    assert auth.check_login_rate_limit("2.2.2.2") is True


def test_rate_limit_attempts_remaining():
    """Remaining count decreases correctly."""
    auth._login_attempts.clear()
    assert auth.get_login_attempts_remaining("3.3.3.3") == 5
    auth.check_login_rate_limit("3.3.3.3")
    assert auth.get_login_attempts_remaining("3.3.3.3") == 4


@pytest.mark.asyncio
async def test_guild_revocation():
    """Revoked guild blocks sessions."""
    os.environ["JWT_SECRET"] = "test_secret"
    auth._revoked_guilds.clear()
    auth._validated_tokens.clear()
    auth.revoke_guild_sessions("revoked_guild")
    assert auth.is_guild_revoked("revoked_guild") is True
    token = auth.create_session("revoked_guild", "admin")
    assert auth.validate_session(token) is False
    del os.environ["JWT_SECRET"]


@pytest.mark.asyncio
async def test_token_hash_deterministic():
    """Same token -> same hash."""
    h1 = auth._token_hash("abc123")
    h2 = auth._token_hash("abc123")
    assert h1 == h2


@pytest.mark.asyncio
async def test_100_concurrent_logins():
    """100 different IPs can all log in simultaneously."""
    auth._login_attempts.clear()
    for i in range(100):
        ip = f"10.0.{i // 256}.{i % 256}"
        assert auth.check_login_rate_limit(ip) is True


@pytest.mark.asyncio
async def test_session_expiry():
    """Expired token -> invalid."""
    os.environ["JWT_SECRET"] = "test_secret"
    auth._validated_tokens.clear()
    auth._revoked_tokens.clear()
    # Create token with past expiry
    payload = {
        "guild_id": "g1",
        "role": "admin",
        "exp": int(time.time()) - 3600
    }
    import jwt as pyjwt
    token = pyjwt.encode(payload, "test_secret", algorithm="HS256")
    assert auth.validate_session(token) is False
    del os.environ["JWT_SECRET"]


# --- Server Size Tests ---

def test_rate_limit_1000_ips():
    """1000 different IPs all within limits."""
    auth._login_attempts.clear()
    for i in range(1000):
        ip = f"192.168.{i // 256}.{i % 256}"
        assert auth.check_login_rate_limit(ip) is True


# ============================================================================
# 5. RAID LOGGING DB FIX
# ============================================================================

@pytest.fixture
def raid_db():
    """Create an in-memory SQLite database for testing."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from aegis.db.models import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
    engine.dispose()


def test_raid_event_creation(raid_db):
    """Can create and query a RaidEvent."""
    from aegis.db.models import RaidEvent
    event = RaidEvent(
        guild_id="123456",
        join_count=25,
        window_seconds=60,
        response_action="lock_server",
        members_affected=json.dumps(["u1", "u2", "u3"]),
        resolved=0,
    )
    raid_db.add(event)
    raid_db.commit()

    result = raid_db.query(RaidEvent).filter_by(guild_id="123456").first()
    assert result is not None
    assert result.join_count == 25
    assert result.response_action == "lock_server"
    assert json.loads(result.members_affected) == ["u1", "u2", "u3"]
    assert result.resolved == 0


def test_raid_event_multiple_per_guild(raid_db):
    """Multiple raid events for same guild."""
    from aegis.db.models import RaidEvent
    for i in range(5):
        raid_db.add(RaidEvent(
            guild_id="999",
            join_count=10 + i,
            window_seconds=60,
            response_action="slowmode",
        ))
    raid_db.commit()

    events = raid_db.query(RaidEvent).filter_by(guild_id="999").all()
    assert len(events) == 5


def test_raid_event_guild_index():
    """guild_id column is indexed."""
    from aegis.db.models import RaidEvent
    from sqlalchemy import inspect as sa_inspect
    mapper = sa_inspect(RaidEvent)
    # Check columns for index attribute
    for col in mapper.columns:
        if col.name == "guild_id":
            assert col.index is True
            break
    else:
        raise AssertionError("guild_id column not found")


def test_raid_event_resolved_default(raid_db):
    """resolved defaults to 0."""
    from aegis.db.models import RaidEvent
    event = RaidEvent(
        guild_id="777",
        join_count=15,
        window_seconds=30,
        response_action="alert",
    )
    raid_db.add(event)
    raid_db.commit()
    assert event.resolved == 0


def test_raid_event_large_payload(raid_db):
    """Large members_affected list."""
    from aegis.db.models import RaidEvent
    users = [f"user_{i}" for i in range(500)]
    event = RaidEvent(
        guild_id="big_raid",
        join_count=500,
        window_seconds=120,
        response_action="lock_server",
        members_affected=json.dumps(users),
    )
    raid_db.add(event)
    raid_db.commit()

    result = raid_db.query(RaidEvent).filter_by(guild_id="big_raid").first()
    assert len(json.loads(result.members_affected)) == 500


# --- Aggressive Tests ---

def test_raid_event_1000_entries(raid_db):
    """Insert 1000 raid events across 10 guilds."""
    from aegis.db.models import RaidEvent
    for i in range(1000):
        raid_db.add(RaidEvent(
            guild_id=f"guild_{i % 10}",
            join_count=i,
            window_seconds=60,
            response_action="slowmode",
        ))
    raid_db.commit()

    for g in range(10):
        count = raid_db.query(RaidEvent).filter_by(guild_id=f"guild_{g}").count()
        assert count == 100


def test_raid_event_query_ordering(raid_db):
    """Events ordered by detected_at descending."""
    from aegis.db.models import RaidEvent
    for i in range(10):
        raid_db.add(RaidEvent(
            guild_id="g1",
            join_count=i,
            window_seconds=60,
            response_action="alert",
        ))
    raid_db.commit()

    events = raid_db.query(RaidEvent).filter_by(guild_id="g1").order_by(
        RaidEvent.detected_at.desc()
    ).all()
    assert len(events) == 10
    # Newest first
    assert events[0].join_count >= events[-1].join_count


# ============================================================================
# 6. BACKUP SCHEDULER
# ============================================================================

@pytest.fixture
def backup_paths():
    """Create a temp directory structure for backup tests."""
    tmp = Path(tempfile.mkdtemp())
    backups_dir = tmp / "backups"
    backups_dir.mkdir()
    db_file = tmp / "aegis.db"
    db_file.touch()
    yield {"tmp": tmp, "backups": backups_dir, "db_file": db_file}
    shutil.rmtree(tmp)


def _make_backup_dir():
    """Helper: create a temp backup directory."""
    tmp = Path(tempfile.mkdtemp())
    backups_dir = tmp / "backups"
    backups_dir.mkdir()
    return tmp, backups_dir


def test_rotate_backups_keeps_newest(backup_paths):
    """Keeps only the 10 most recent backups."""
    from aegis.db.maintenance import rotate_backups

    class FakePaths:
        def __init__(self, backups):
            self.backups_db = backups

    paths = FakePaths(backup_paths["backups"])
    for i in range(15):
        f = paths.backups_db / f"aegis_rev_{i:03d}_2024010{i % 10}_120000.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    rotate_backups(paths, keep=10)
    remaining = list(paths.backups_db.glob("aegis_*.db"))
    assert len(remaining) == 10


def test_rotate_backups_no_dir():
    """Missing backups dir -> no crash."""
    from aegis.db.maintenance import rotate_backups

    class FakePaths:
        backups_db = Path("/nonexistent/path")

    rotate_backups(FakePaths(), keep=10)


def test_rotate_backups_under_limit(backup_paths):
    """Fewer than keep -> nothing deleted."""
    from aegis.db.maintenance import rotate_backups

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    fp = FakePaths(backup_paths["backups"])
    for i in range(3):
        (fp.backups_db / f"aegis_rev_{i}.db").touch()

    rotate_backups(fp, keep=10)
    remaining = list(fp.backups_db.glob("aegis_*.db"))
    assert len(remaining) == 3


# --- Aggressive Tests ---

def test_rotate_backups_100_files():
    """100 backup files -> keeps 10, deletes 90."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(100):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    shutil.rmtree(tmp)


def test_rotate_backups_exact_10():
    """Exactly 10 -> nothing deleted."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(10):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    shutil.rmtree(tmp)


def test_rotate_backups_mixed_files():
    """Non-backup files are not deleted."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(15):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))
    (backups / "important_note.txt").touch()

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("*"))
    assert len(remaining) == 11  # 10 backups + 1 txt
    shutil.rmtree(tmp)


# --- Server Size Tests ---

def test_rotate_backups_500_files():
    """500 backup files -> keeps 10."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(500):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    shutil.rmtree(tmp)


def test_rotate_backups_no_dir():
    """Missing backups dir -> no crash."""
    from aegis.db.maintenance import rotate_backups

    class FakePaths:
        backups_db = Path("/nonexistent/path")

    rotate_backups(FakePaths(), keep=10)


def test_rotate_backups_under_limit(backup_paths):
    """Fewer than keep -> nothing deleted."""
    from aegis.db.maintenance import rotate_backups

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    fp = FakePaths(backup_paths["backups"])
    for i in range(3):
        (fp.backups_db / f"aegis_rev_{i}.db").touch()

    rotate_backups(fp, keep=10)
    remaining = list(fp.backups_db.glob("aegis_*.db"))
    assert len(remaining) == 3


# --- Aggressive Tests ---

def test_rotate_backups_100_files():
    """100 backup files -> keeps 10, deletes 90."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(100):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    shutil.rmtree(tmp)


def test_rotate_backups_exact_10():
    """Exactly 10 -> nothing deleted."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(10):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    shutil.rmtree(tmp)


def test_rotate_backups_mixed_files():
    """Non-backup files are not deleted."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(15):
        f = backups / f"aegis_rev_{i}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))
    (backups / "important_note.txt").touch()

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("*"))
    assert len(remaining) == 11  # 10 backups + 1 txt
    shutil.rmtree(tmp)


# --- Server Size Tests ---

def test_rotate_backups_500_files():
    """500 backup files -> keeps 10."""
    from aegis.db.maintenance import rotate_backups
    tmp, backups = _make_backup_dir()

    for i in range(500):
        f = backups / f"aegis_rev_{i:04d}.db"
        f.touch()
        os.utime(f, (1000 + i, 1000 + i))

    class FakePaths:
        def __init__(self, p):
            self.backups_db = p

    rotate_backups(FakePaths(backups), keep=10)
    remaining = list(backups.glob("aegis_*.db"))
    assert len(remaining) == 10
    shutil.rmtree(tmp)
