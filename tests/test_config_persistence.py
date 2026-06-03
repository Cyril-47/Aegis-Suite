import utils

def test_guild_config_persistence_audit(paths_tmp, monkeypatch):
    """ST-2: Guild Config Persistence Audit.
    Loads active config, modifies fields, saves under lock, and verifies values are preserved.
    """
    # Override the CONFIG_PATH to use the temp directory
    monkeypatch.setattr(utils, "CONFIG_PATH", str(paths_tmp.config_file))
    
    # 1. Load active config.json via utils.load_config
    config = utils.load_config()
    
    # 2. Modify command_permissions, permission_roles, and music_settings fields for a guild
    guild_id = "9876543210"
    guild_conf = utils.get_guild_config(guild_id)
    
    custom_permissions = {
        "MUSIC_PLAY": {
            "mode": "role",
            "role_id": "role-123",
            "role_ids": []
        },
        "MUSIC_STOP": {
            "mode": "admin",
            "role_id": None,
            "role_ids": []
        }
    }
    
    custom_roles = {
        "admin_role_id": "role-admin",
        "moderator_role_id": "role-mod"
    }
    
    custom_music = {
        "default_volume": 75.0,
        "solo_bypass_enabled": True
    }
    
    guild_conf["command_permissions"] = custom_permissions
    guild_conf["permission_roles"] = custom_roles
    guild_conf["music_settings"] = custom_music
    
    # 3. Invoke utils.save_config() via save_guild_config under config_lock lock
    with utils.config_lock:
        utils.save_guild_config(guild_id, guild_conf)
        
    # 4. Clear/reload and assert values are preserved exactly
    reloaded_guild_conf = utils.get_guild_config(guild_id)
    
    assert reloaded_guild_conf["command_permissions"] == custom_permissions
    assert reloaded_guild_conf["permission_roles"] == custom_roles
    assert reloaded_guild_conf["music_settings"] == custom_music
