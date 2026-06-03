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
