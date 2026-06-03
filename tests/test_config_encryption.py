import json
import pytest
from aegis.config.loader import ConfigStore
from aegis.core.encryption import DPAPIEncryption

pytestmark = pytest.mark.skipif(
    not DPAPIEncryption.is_available(),
    reason="Windows DPAPI is unavailable on this host",
)

def test_config_store_token_encryption_roundtrip(paths_tmp):
    # 1. Create a config.json file with discord_token and bot_token
    config_file = paths_tmp.config_file
    initial_data = {
        "client_id": "999888777",
        "setup_complete": False,
        "welcome_settings": {
            "enabled": True,
            "channel_name": "welcome",
            "message_title": "Hello",
            "message_description": "Welcome!",
            "embed_color": "#6366F1",
            "auto_assign_roles": []
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": False,
            "block_links": False,
            "max_mentions": 5,
            "log_channel_name": "mod-logs",
            "profanity_words": []
        },
        "discord_token": "valid_token_value_xyz",
        "bot_token": "bot_token_value_abc"
    }
    
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)
        
    # Load configuration
    store = ConfigStore.load(paths_tmp)
    
    # Assert values are decrypted on load
    assert store.as_dict().get("discord_token") == "valid_token_value_xyz"
    assert store.as_dict().get("bot_token") == "bot_token_value_abc"
    
    # Save the configuration (should encrypt on disk)
    store.save()
    
    # Inspect raw JSON file to verify it is encrypted
    with open(config_file, "r", encoding="utf-8") as f:
        raw_data = json.load(f)
        
    assert raw_data["discord_token"].startswith("dpapi:")
    assert raw_data["bot_token"].startswith("dpapi:")
    assert "valid_token_value_xyz" not in raw_data["discord_token"]
    assert "bot_token_value_abc" not in raw_data["bot_token"]
    
    # Reload from disk and verify it decrypts correctly
    store_reloaded = ConfigStore.load(paths_tmp)
    assert store_reloaded.as_dict().get("discord_token") == "valid_token_value_xyz"
    assert store_reloaded.as_dict().get("bot_token") == "bot_token_value_abc"
