import pytest
import os
from unittest.mock import patch, MagicMock
from aegis.bot.runner import validate_token, TokenVerdict

@pytest.mark.asyncio
async def test_validate_token_no_bypass_behavior():
    # A well-formed fake token (three dot components)
    fake_token = "fake.token.format"
    
    # Mock discord.Client.login to raise an exception, verifying it runs the real login probe
    with patch("discord.Client.login", side_effect=Exception("Connection refused")):
        verdict = await validate_token(fake_token)
        # Should fail authentication since login failed
        assert verdict == TokenVerdict.AUTH_FAILED

def test_no_bypass_literals_in_shipped_code():
    # Grep-like verification to ensure no bypass shims exist in production runner code
    runner_path = os.path.join("aegis", "bot", "runner.py")
    with open(runner_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    bypass_indicators = [
        "PYTEST_CURRENT_TEST",
        "ABC.DEF.GHI",
        "bad_token",
        "intent_failed"
    ]
    for indicator in bypass_indicators:
        assert indicator not in content, f"Discovered bypass shim indicator '{indicator}' in production runner code"
