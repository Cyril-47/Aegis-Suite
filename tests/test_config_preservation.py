import json
import pytest
from unittest.mock import patch
from aegis.config.loader import ConfigStore
from aegis.config.schema import ConfigModel, WelcomeSettingsModel, AutomodSettingsModel

def test_config_store_save_preserves_unmodeled_keys(paths_tmp):
    # 1. Create a config.json file with both modeled and unmodeled keys
    config_file = paths_tmp.config_file
    initial_data = {
        "client_id": "999888777",
        "setup_complete": False,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_id": "123",
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
            "log_channel_id": None,
            "log_channel_name": "mod-logs",
            "profanity_words": []
        },
        # Unmodeled keys at top-level
        "giveaways": {"active_giveaway_id": "abc"},
        "scheduled_messages": [{"id": 1, "msg": "test"}],
        "guild_configs": {"12345": {"prefix": "!"}}
    }
    
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)
        
    # 2. Load the configuration
    store = ConfigStore.load(paths_tmp)
    
    # Verify it loaded correctly
    assert store.client_id == "999888777"
    
    # 3. Update modeled values in the store model
    store._model.client_id = "111222333"
    store._model.ui_mode = "expert"
    
    # 4. Save the configuration
    store.save()
    
    # 5. Reload raw JSON and verify everything is preserved
    with open(config_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
        
    assert saved_data["client_id"] == "111222333"
    assert saved_data["ui_mode"] == "expert"
    assert saved_data["setup_complete"] is False
    
    # Verify unmodeled keys at top level are preserved verbatim
    assert saved_data["giveaways"] == {"active_giveaway_id": "abc"}
    assert saved_data["scheduled_messages"] == [{"id": 1, "msg": "test"}]
    assert saved_data["guild_configs"] == {"12345": {"prefix": "!"}}


def test_config_store_save_recursive_merge_on_nested_modeled_sections(paths_tmp):
    # 1. Create a config.json file with a modeled nested section containing extra/unmodeled fields
    config_file = paths_tmp.config_file
    initial_data = {
        "client_id": "999888777",
        "setup_complete": False,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_id": "123",
            "channel_name": "welcome",
            "message_title": "Hello",
            "message_description": "Welcome!",
            "embed_color": "#6366F1",
            "auto_assign_roles": [],
            # Unmodeled nested extra keys inside a modeled section
            "some_extra_nested_field": "keep_me",
            "another_nested_dict": {"extra": "value"}
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": False,
            "block_links": False,
            "max_mentions": 5,
            "log_channel_id": None,
            "log_channel_name": "mod-logs",
            "profanity_words": []
        }
    }
    
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)
        
    # We must ensure model_config = ConfigDict(extra="allow") is implemented for the nested models
    # for the extra fields to survive load validation or to be handled correctly.
    # If the model does not have extra="allow" yet, the fields might be dropped during load.
    # Let's see. This test will verify the recursive merge is working.
    # Note: If Pydantic loads it, and it allows extra fields, they survive in the model.
    # If we merge them, they should be retained.
    store = ConfigStore.load(paths_tmp)
    
    # Change welcome settings enabled state in the model
    store._model.welcome_settings.enabled = False
    
    # Save the store
    store.save()
    
    # Read raw JSON
    with open(config_file, "r", encoding="utf-8") as f:
        saved_data = json.load(f)
        
    assert saved_data["welcome_settings"]["enabled"] is False
    # Ensure extra nested keys inside welcome_settings are preserved
    assert saved_data["welcome_settings"]["some_extra_nested_field"] == "keep_me"
    assert saved_data["welcome_settings"]["another_nested_dict"] == {"extra": "value"}


def test_config_store_save_failure_leaves_file_intact(paths_tmp):
    config_file = paths_tmp.config_file
    initial_data = {
        "client_id": "123",
        "setup_complete": False,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_id": None,
            "channel_name": "welcome",
            "message_title": "Welcome",
            "message_description": "Welcome!",
            "embed_color": "#6366F1",
            "auto_assign_roles": []
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": False,
            "block_links": False,
            "max_mentions": 5,
            "log_channel_id": None,
            "log_channel_name": "mod-logs",
            "profanity_words": []
        }
    }
    
    with open(config_file, "w", encoding="utf-8") as f:
        json.dump(initial_data, f)
        
    store = ConfigStore.load(paths_tmp)
    store._model.client_id = "456"
    
    # Inject failure into json.dump by mocking it
    with patch("json.dump", side_effect=IOError("Simulated disk error")):
        with pytest.raises(IOError, match="Simulated disk error"):
            store.save()
            
    # Check that the original file is unchanged (contains "123")
    with open(config_file, "r", encoding="utf-8") as f:
        current_data = json.load(f)
    assert current_data["client_id"] == "123"
    
    # Check that no temp files remain in config directory
    temp_files = list(config_file.parent.glob("config_*.tmp"))
    assert len(temp_files) == 0
