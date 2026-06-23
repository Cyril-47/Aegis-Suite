"""Aggressive real-world scenario tests for Moderation Commands.

Simulates actual Discord server conditions:
- Small server (50 members), medium (500), large (5000), massive (50000)
- Raids, spam floods, permission edge cases, automod bypass
"""
import pytest
import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

from aegis.bot.cogs.moderation import ModerationCog


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
        self.guild.get_channel = MagicMock(return_value=AsyncMock())
        self.channel = AsyncMock()
        self.channel.id = channel_id
        self.channel.name = "general"
        self.mentions = mentions or []
        self.role_mentions = []
        self.delete = AsyncMock()
        self.send = AsyncMock()


def make_config(overrides=None):
    base = {
        "guild_configs": {
            "999": {
                "automod": {
                    "enabled": True,
                    "profanity_filter": True,
                    "spam_filter": True,
                    "link_filter": True,
                    "mention_spam": True,
                    "link_whitelist": ["github.com", "youtube.com"],
                    "profanity_words": ["badword1", "badword2", "spam"],
                }
            }
        }
    }
    if overrides:
        base["guild_configs"]["999"]["automod"].update(overrides)
    return base


@pytest.mark.asyncio
async def test_raid_50_bots_spam_links():
    """50 bots flood #general with phishing links."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    blocked = 0
    for i in range(50):
        msg = FakeMessage(f"Free nitro at https://phish{ i}.com/steal", author_id=10000 + i)
        if await cog._check_links(msg):
            blocked += 1

    assert blocked == 50, f"Expected 50 blocked, got {blocked}"


@pytest.mark.asyncio
async def test_raid_100_bots_mention_everyone():
    """100 bots ping @everyone with 50 mentions each."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    blocked = 0
    for i in range(100):
        mentions = [MagicMock() for _ in range(50)]
        msg = FakeMessage("@everyone @here " * 25, author_id=20000 + i, mentions=mentions)
        if await cog._check_mention_spam(msg):
            blocked += 1

    assert blocked == 100


@pytest.mark.asyncio
async def test_legitimate_user_not_blocked():
    """Normal user sending messages with allowed content."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    for i in range(20):
        msg = FakeMessage(f"Hey everyone, check out https://github.com/myproject", author_id=30000)
        assert await cog._check_links(msg) is False
        assert await cog._check_mention_spam(msg) is False


@pytest.mark.asyncio
async def test_staff_bypass_link_filter():
    """Staff member posting links should not be blocked (if configured)."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("https://suspicious-link.com/steal", author_id=40000)
    msg.author.bot = False
    result = await cog._check_links(msg)
    # Without staff bypass config, it should block
    assert result is True


@pytest.mark.asyncio
async def test_mention_spam_exactly_at_limit():
    """5 mentions = exactly at limit, should pass."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    mentions = [MagicMock() for _ in range(5)]
    msg = FakeMessage("Hey @user1 @user2 @user3 @user4 @user5", mentions=mentions)
    assert await cog._check_mention_spam(msg) is False


@pytest.mark.asyncio
async def test_mention_spam_one_over():
    """6 mentions = one over limit, should block."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    mentions = [MagicMock() for _ in range(6)]
    msg = FakeMessage("Spam mentions", mentions=mentions)
    assert await cog._check_mention_spam(msg) is True


@pytest.mark.asyncio
async def test_link_filter_various_protocols():
    """Links with http, https, different TLDs."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    malicious_urls = [
        "http://phishing.ru/steal",
        "https://scam.cn/fake",
        "http://hack.to/malware",
        "https://steal.cc/credentials",
    ]

    for url in malicious_urls:
        msg = FakeMessage(f"Click this {url}")
        assert await cog._check_links(msg) is True, f"Should block {url}"


@pytest.mark.asyncio
async def test_link_filter_whitelisted_multiple():
    """Multiple whitelisted domains pass."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    safe_urls = [
        "https://github.com/user/repo",
        "https://youtube.com/watch?v=123",
        "https://github.com/other/repo",
    ]

    for url in safe_urls:
        msg = FakeMessage(f"Check out {url}")
        assert await cog._check_links(msg) is False, f"Should allow {url}"


@pytest.mark.asyncio
async def test_automod_disabled_guild():
    """Guild with automod disabled - no checks run."""
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": False}}}}
    cog = ModerationCog(bot)

    msg = FakeMessage("https://phishing.com/steal")
    await cog._run_automod(msg)
    msg.delete.assert_not_called()


@pytest.mark.asyncio
async def test_automod_no_config():
    """Guild with no automod config."""
    bot = MagicMock()
    bot.config = {"guild_configs": {}}
    cog = ModerationCog(bot)

    msg = FakeMessage("https://phishing.com/steal")
    await cog._run_automod(msg)
    msg.delete.assert_not_called()


@pytest.mark.asyncio
async def test_permission_denied_graceful():
    """Bot lacks delete permission - should not crash."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    import discord
    msg = FakeMessage("https://phishing.com/steal")
    msg.delete.side_effect = discord.Forbidden(MagicMock(), "no permission")

    result = await cog._check_links(msg)
    assert result is False


@pytest.mark.asyncio
async def test_profanity_empty_list():
    """No blocked words configured."""
    bot = MagicMock()
    bot.config = {"guild_configs": {"999": {"automod": {"enabled": True, "profanity_filter": True}}}}
    cog = ModerationCog(bot)

    msg = FakeMessage("This has badword1 in it")
    result = await cog._check_profanity(msg)
    assert result is False


@pytest.mark.asyncio
async def test_multiple_automod_rules_simultaneous():
    """Message triggers multiple rules at once."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("https://phishing.com/steal", mentions=[MagicMock() for _ in range(6)])
    link_blocked = await cog._check_links(msg)
    mention_blocked = await cog._check_mention_spam(msg)
    assert link_blocked is True
    assert mention_blocked is True


@pytest.mark.asyncio
async def test_large_guild_500_channels_automod():
    """500 channels, each with a message going through automod."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    blocked = 0
    for ch_id in range(500):
        msg = FakeMessage(f"Normal message in channel {ch_id}", channel_id=ch_id)
        if await cog._check_links(msg):
            blocked += 1

    assert blocked == 0


@pytest.mark.asyncio
async def test_link_filter_url_in_long_message():
    """URL hidden in a long legitimate-looking message."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage(
        "Hey everyone! I just wanted to share this amazing resource I found. "
        "It's really helpful for learning. Check it out: https://phishing.ru/steal "
        "Let me know what you think!"
    )
    assert await cog._check_links(msg) is True


@pytest.mark.asyncio
async def test_mention_spam_with_role_mentions():
    """Message with role mentions (not counted in len(mentions))."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("Spam mentions")
    msg.role_mentions = [MagicMock() for _ in range(10)]
    msg.mentions = []
    assert await cog._check_mention_spam(msg) is False


@pytest.mark.asyncio
async def test_concurrent_messages_same_channel():
    """Multiple messages in same channel processed concurrently."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    tasks = []
    for i in range(10):
        msg = FakeMessage(f"Message {i}", author_id=50000 + i)
        tasks.append(cog._check_links(msg))

    results = await asyncio.gather(*tasks)
    assert all(r is False for r in results)


@pytest.mark.asyncio
async def test_link_filter_subdomain_trick():
    """Phishing link with whitelisted domain as subdomain should be blocked."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("https://github.com.phishing.ru/steal")
    assert await cog._check_links(msg) is True, "Subdomain trick should be blocked"


@pytest.mark.asyncio
async def test_link_filter_subdomain_trick_v2():
    """Same trick with youtube.com subdomain."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("https://youtube.com.phishing.ru/steal")
    assert await cog._check_links(msg) is True, "Subdomain trick should be blocked"


@pytest.mark.asyncio
async def test_link_filter_legitimate_subdomain_passes():
    """Legitimate subdomain (docs.github.com) should pass whitelist."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("https://docs.github.com/user/repo")
    assert await cog._check_links(msg) is False, "Legitimate subdomain should pass"


@pytest.mark.asyncio
async def test_link_filter_exact_domain_passes():
    """Exact whitelisted domain should pass."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("https://github.com/user/repo")
    assert await cog._check_links(msg) is False, "Exact domain should pass"


@pytest.mark.asyncio
async def test_link_filter_no_http_prefix():
    """Link without http prefix."""
    bot = MagicMock()
    bot.config = make_config()
    cog = ModerationCog(bot)

    msg = FakeMessage("Check out phishing.ru/steal")
    result = await cog._check_links(msg)
    assert result is False  # No http prefix, regex won't match
