"""Aggressive real-world scenario tests for Fuzzy Spam Detector.

Simulates actual Discord spam conditions:
- Raid bots posting identical messages
- Slightly varied spam (typos, extra chars)
- Cross-channel spam
- legitimate similar messages (not spam)
- Massive floods
"""
import pytest
import asyncio
import time
from aegis.intelligence.spam_detector import FuzzySpamDetector


@pytest.mark.asyncio
async def test_raid_50_bots_identical():
    """50 bots post identical phishing message."""
    detector = FuzzySpamDetector()
    for i in range(50):
        detector.record_message(f"bot_{i}", "general", "FREE NITRO! Click here: discord.gift/fake")

    result = detector.analyze("bot_50", "general", "FREE NITRO! Click here: discord.gift/fake")
    assert result["is_spam"] is True
    assert result["spam_score"] >= 0.8
    assert result["raid_detected"] is True
    assert result["exact_matches"] >= 49


@pytest.mark.asyncio
async def test_varied_spam_campaign():
    """10 bots post similar but slightly different spam."""
    detector = FuzzySpamDetector()
    messages = [
        "Join my server its really cool",
        "Join my server its really cool!",
        "join my server its really cool",
        "Join my Server its really cool",
        "Join my server its really cool plz",
    ]

    for i in range(10):
        msg = messages[i % len(messages)]
        detector.record_message(f"spammer_{i}", "general", msg)

    result = detector.analyze("new_spammer", "general", "Join my server its really cool")
    assert result["is_spam"] is True
    assert result["raid_detected"] is True


@pytest.mark.asyncio
async def test_cross_channel_spam():
    """Spam in multiple channels from same users."""
    detector = FuzzySpamDetector()
    for i in range(5):
        for ch in ["general", "memes", "off-topic"]:
            detector.record_message(f"user_{i}", ch, "BUY CHEAP FOLLOWERS NOW")

    # Check each channel independently
    for ch in ["general", "memes", "off-topic"]:
        result = detector.analyze("new_user", ch, "BUY CHEAP FOLLOWERS NOW")
        assert result["is_spam"] is True, f"Channel {ch} should detect spam"


@pytest.mark.asyncio
async def test_legitimate_similar_messages():
    """Normal users discussing similar topics - NOT spam."""
    detector = FuzzySpamDetector()
    detector.record_message("user1", "general", "I think Python is better than JavaScript")
    detector.record_message("user2", "general", "I think Python is better than Java")
    detector.record_message("user3", "general", "I prefer Python over JavaScript")

    result = detector.analyze("user4", "general", "I like Python more than JavaScript")
    # Should not be flagged as raid (different users, slightly different content)
    assert result["raid_detected"] is False


@pytest.mark.asyncio
async def test_single_user_spam():
    """One user posting same message repeatedly."""
    detector = FuzzySpamDetector()
    for _ in range(20):
        detector.record_message("spammer", "general", "BUY NOW CLICK HERE")

    result = detector.analyze("spammer", "general", "BUY NOW CLICK HERE")
    assert result["is_spam"] is True
    assert result["exact_matches"] >= 19


@pytest.mark.asyncio
async def test_spam_levenshtein_edge_cases():
    """Test Levenshtein with edge cases."""
    detector = FuzzySpamDetector()

    # Identical
    assert detector._levenshtein_similarity("test", "test") == 1.0

    # One char different
    sim = detector._levenshtein_similarity("hello", "helo")
    assert sim >= 0.8

    # Completely different
    sim = detector._levenshtein_similarity("abc", "xyz")
    assert sim < 0.5

    # Empty strings
    assert detector._levenshtein_similarity("", "") == 1.0
    assert detector._levenshtein_similarity("test", "") == 0.0

    # One char each
    assert detector._levenshtein_similarity("a", "a") == 1.0
    sim = detector._levenshtein_similarity("a", "b")
    assert sim == 0.0


@pytest.mark.asyncio
async def test_spam_score_thresholds():
    """Verify spam score thresholds."""
    detector = FuzzySpamDetector()

    # No spam
    result = detector.analyze("u1", "ch1", "hello world")
    assert result["spam_score"] == 0
    assert result["is_spam"] is False

    # 2 exact duplicates -> score 0.5 (below is_spam threshold of 0.6)
    detector.record_message("u1", "ch1", "buy now buy now")
    detector.record_message("u2", "ch1", "buy now buy now")
    result = detector.analyze("u3", "ch1", "buy now buy now")
    assert result["spam_score"] == 0.5
    assert result["is_spam"] is False

    # 3 exact duplicates -> score 0.8 (above is_spam threshold)
    detector.record_message("u4", "ch1", "buy now buy now")
    result = detector.analyze("u5", "ch1", "buy now buy now")
    assert result["spam_score"] >= 0.8
    assert result["is_spam"] is True


@pytest.mark.asyncio
async def test_spam_suggested_actions():
    """Verify suggested actions for different spam levels."""
    detector = FuzzySpamDetector()

    # Raid pattern
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "spam message here")
    result = detector.analyze("u5", "ch1", "spam message here")
    actions = [a["action"] for a in result["suggested_actions"]]
    assert "mute_spammers" in actions
    assert "lock_channel" in actions


@pytest.mark.asyncio
async def test_campaign_summary():
    """Campaign summary tracks detected raids."""
    detector = FuzzySpamDetector()
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "raid campaign msg")
    detector.analyze("u5", "ch1", "raid campaign msg")

    summary = detector.get_campaign_summary()
    assert summary["total_campaigns"] >= 1
    assert len(summary["affected_users"]) >= 1
    assert "ch1" in summary["affected_channels"]


@pytest.mark.asyncio
async def test_spam_intelligence():
    """get_spam_intelligence returns campaign data."""
    detector = FuzzySpamDetector()
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "repeat content here")

    intel = detector.get_spam_intelligence("g1")
    assert "campaigns" in intel
    assert "total_campaigns" in intel
    assert "affected_channels" in intel


@pytest.mark.asyncio
async def test_spam_heavy_flood_1000():
    """1000 messages from 100 users."""
    detector = FuzzySpamDetector()
    for i in range(100):
        for j in range(10):
            detector.record_message(f"u{i}", "ch1", f"spam variant {j}")

    result = detector.analyze("u100", "ch1", "spam variant 0")
    assert result["spam_score"] > 0


@pytest.mark.asyncio
async def test_spam_50_channels_isolated():
    """50 channels with independent spam."""
    detector = FuzzySpamDetector()
    for ch in range(50):
        for i in range(5):
            detector.record_message(f"u{i}", f"ch{ch}", f"spam in ch{ch}")

    for ch in range(50):
        result = detector.analyze("u10", f"ch{ch}", f"spam in ch{ch}")
        assert result["is_spam"] is True


@pytest.mark.asyncio
async def test_spam_rate_limit():
    """1000 messages processed quickly."""
    detector = FuzzySpamDetector()

    start = time.perf_counter()
    for i in range(1000):
        detector.record_message(f"u{i % 100}", "ch1", f"message {i}")
    for i in range(100):
        detector.analyze(f"u{i}", "ch1", f"message {i}")
    elapsed = time.perf_counter() - start

    print(f"\n  [PERF] 1000 messages + 100 analyses in {elapsed*1000:.1f}ms")
    assert elapsed < 5.0  # Should complete in under 5 seconds


@pytest.mark.asyncio
async def test_spam_empty_channel():
    """Empty channel - no spam."""
    detector = FuzzySpamDetector()
    result = detector.analyze("u1", "empty_ch", "hello")
    assert result["is_spam"] is False
    assert result["spam_score"] == 0


@pytest.mark.asyncio
async def test_spam_case_insensitive():
    """Spam detection is case-insensitive."""
    detector = FuzzySpamDetector()
    detector.record_message("u1", "ch1", "BUY NOW BUY NOW")
    detector.record_message("u2", "ch1", "buy now buy now")
    detector.record_message("u3", "ch1", "Buy Now Buy Now")

    result = detector.analyze("u4", "ch1", "buy now buy now")
    assert result["exact_matches"] >= 3
    assert result["is_spam"] is True


@pytest.mark.asyncio
async def test_spam_no_false_positives_normal_chat():
    """Normal chat should not trigger spam detection."""
    detector = FuzzySpamDetector()
    messages = [
        "Hey how are you?",
        "I'm good, thanks!",
        "What are you working on?",
        "Building a Discord bot",
        "That sounds cool!",
        "Yeah it's fun",
        "Have you used Python?",
        "Yes, I love Python",
        "Me too, it's great",
        "What framework?",
        "I use discord.py",
        "Nice choice!",
    ]

    for i, msg in enumerate(messages):
        detector.record_message(f"user_{i}", "general", msg)

    for i, msg in enumerate(messages):
        result = detector.analyze(f"user_{i}", "general", msg)
        # None of these should be flagged as high spam
        assert result["spam_score"] < 0.5, f"False positive on: {msg}"


@pytest.mark.asyncio
async def test_spam_long_message():
    """Very long spam message."""
    detector = FuzzySpamDetector()
    long_msg = "A" * 1000
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", long_msg)

    result = detector.analyze("u5", "ch1", long_msg)
    assert result["is_spam"] is True
    assert result["exact_matches"] >= 4


@pytest.mark.asyncio
async def test_spam_unicode_messages():
    """Spam with unicode characters."""
    detector = FuzzySpamDetector()
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "Join our server! \u2764\ufe0f \u2764\ufe0f \u2764\ufe0f")

    result = detector.analyze("u5", "ch1", "Join our server! \u2764\ufe0f \u2764\ufe0f \u2764\ufe0f")
    assert result["is_spam"] is True


@pytest.mark.asyncio
async def test_spam_emoji_only():
    """Spam with only emojis."""
    detector = FuzzySpamDetector()
    for i in range(5):
        detector.record_message(f"u{i}", "ch1", "\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00")

    result = detector.analyze("u5", "ch1", "\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00\ud83d\ude00")
    assert result["is_spam"] is True
    assert result["exact_matches"] >= 4
