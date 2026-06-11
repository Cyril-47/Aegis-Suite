from sqlalchemy import create_engine
import leveling
import aegis.bot.leveling
from aegis.db.models import Base

def test_leveling_system_object_identity():
    # Verify that the two imports point to the identical LevelingSystem object
    assert leveling.leveling_system is aegis.bot.leveling.leveling_system
    assert leveling.LevelingSystem is aegis.bot.leveling.LevelingSystem

def test_leveling_database_round_trip():
    # Use SQLite in-memory engine
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    
    # Set the engine on leveling_system
    # Since leveling_system is a singleton, keep a backup of its initial state
    # to avoid state bleed into other tests.
    old_engine = leveling.leveling_system.engine
    old_xp_data = leveling.leveling_system.xp_data.copy()
    
    try:
        leveling.leveling_system.set_engine(engine)
        
        # Write some XP using the bot-facing module
        guild_id = "111222"
        user_id = "333444"
        # Add XP (cooldown_seconds=0 to bypass cooldown checks during test)
        new_lvl, leveled_up, current_xp, msgs = aegis.bot.leveling.leveling_system.add_xp(guild_id, user_id, 150, cooldown_seconds=0)
        
        # Save explicitly to DB config_kv table
        aegis.bot.leveling.leveling_system.save()
        
        # Read the XP data back from the DB via the database-facing module
        # Clear local state cache first to force reload from DB
        aegis.bot.leveling.leveling_system.xp_data = {}
        aegis.bot.leveling.leveling_system.load()
        
        # Verify the saved data is reloaded successfully
        user_rank = leveling.leveling_system.get_user_rank(guild_id, user_id)
        assert user_rank["xp"] == 150
        assert user_rank["level"] == 1  # floor(sqrt(150 / 100)) = 1
        
    finally:
        # Restore original state
        leveling.leveling_system.engine = old_engine
        leveling.leveling_system.xp_data = old_xp_data


def test_guild_specific_leveling_config(monkeypatch, tmp_path):
    import utils
    # Override CONFIG_PATH for isolated testing
    monkeypatch.setattr(utils, "CONFIG_PATH", str(tmp_path / "config.json"))
    
    # 1. Reset configuration
    config = utils.load_config()
    config["leveling_settings"] = {
        "enabled": False,
        "xp_per_message": 15,
        "xp_cooldown_seconds": 60,
        "level_up_channel": None,
        "level_roles": {},
        "ignored_channels": [],
        "ignored_roles": []
    }
    config["guild_configs"] = {}
    utils.save_config(config)

    # 2. Verify fallback is used initially
    settings_1 = utils.get_guild_leveling_settings(config, "guild_1")
    assert settings_1["enabled"] is False
    assert settings_1["xp_per_message"] == 15

    # 3. Modify and save leveling configuration for guild_1
    guild_conf_1 = utils.get_guild_config("guild_1")
    guild_conf_1["leveling_settings"] = {
        "enabled": True,
        "xp_per_message": 50,
        "xp_cooldown_seconds": 30,
        "level_up_channel": "123456",
        "level_roles": {},
        "ignored_channels": [],
        "ignored_roles": []
    }
    utils.save_guild_config("guild_1", guild_conf_1)

    # 4. Reload and assert guild-specific settings are retrieved correctly
    reloaded_config = utils.load_config()
    
    # guild_1 should have the custom settings
    settings_1_reloaded = utils.get_guild_leveling_settings(reloaded_config, "guild_1")
    assert settings_1_reloaded["enabled"] is True
    assert settings_1_reloaded["xp_per_message"] == 50
    assert settings_1_reloaded["xp_cooldown_seconds"] == 30
    assert settings_1_reloaded["level_up_channel"] == "123456"

    # guild_2 should still fall back to the global config (which is enabled=False)
    settings_2_reloaded = utils.get_guild_leveling_settings(reloaded_config, "guild_2")
    assert settings_2_reloaded["enabled"] is False
    assert settings_2_reloaded["xp_per_message"] == 15

