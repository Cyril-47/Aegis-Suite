import json
import pytest
from unittest import mock
from sqlalchemy import text, inspect
from alembic.config import Config
from alembic.script import ScriptDirectory

from aegis.core.paths import Paths
from aegis.core.state import LifecycleState, ReasonCode
from aegis.core.app_core import AppCore
from aegis.db.engine import make_engine
from aegis.db.models import Base
from aegis.db.maintenance import (
    backup_db,
    restore_db,
    rotate_backups,
    run_migrations
)
from aegis.config.loader import ConfigStore
from aegis.config.sanitizer import sanitize

# -----------------------------------------------------------------------------
# Helper: Setup valid configuration file dictionary
# -----------------------------------------------------------------------------
def get_valid_config_data() -> dict:
    return {
        "client_id": "123456789012345678",
        "setup_complete": True,
        "ui_mode": "beginner",
        "welcome_settings": {
            "enabled": True,
            "channel_name": "welcome",
            "message_title": "Welcome",
            "message_description": "Welcome to our server!",
            "embed_color": "#00FF00",
            "auto_assign_roles": []
        },
        "automod_settings": {
            "enabled": False,
            "block_profanity": True,
            "block_links": False,
            "max_mentions": 3,
            "log_channel_name": "automod-logs",
            "profanity_words": []
        }
    }

# -----------------------------------------------------------------------------
# Database Engine & Models (Requirement 9)
# -----------------------------------------------------------------------------

def test_req9_database_model(tmp_path):
    """Req 9 AC 1, AC 2, AC 3: Validate database path, WAL, single connection, and tables."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    # AC 1: Validate SQLite database location
    assert paths.db_file == paths.root / "aegis.db"
    
    engine = make_engine(paths)
    
    # AC 2: Validate WAL journaling mode and foreign keys enabled
    with engine.connect() as conn:
        journal_mode = conn.execute(text("PRAGMA journal_mode")).scalar()
        foreign_keys = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert journal_mode.lower() == "wal"
        assert foreign_keys == 1
        
    # AC 3: Validate database single-connection model pool (StaticPool)
    from sqlalchemy.pool import StaticPool
    assert engine.pool.__class__ == StaticPool
    
    # Create all tables manually to verify structure mapping
    Base.metadata.create_all(engine)
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    
    # AC 3, AC 4-8: Verify V1 schema tables exist
    expected_tables = ["schema_meta", "config_kv", "templates", "servers", "apply_history", "migration_log"]
    for table in expected_tables:
        assert table in tables

# -----------------------------------------------------------------------------
# Database Maintenance & Backups (Requirement 24)
# -----------------------------------------------------------------------------

def test_req24_backup_restore_rotation(tmp_path):
    """Req 24 AC 1, AC 2, AC 3: Verify database online backup creation, restore, and rotation."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    engine = make_engine(paths)
    Base.metadata.create_all(engine)
    
    # Populate database with some dummy data to verify rollback integrity
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO schema_meta (key, value) VALUES (:key, :value)"),
            {"key": "test_key", "value": "original_val"}
        )
        
    # AC 1 & Req 10 AC 5: Generate online database backup via SQLite online backup API
    backup_path = backup_db(paths, engine, current_rev="baseline_v1")
    assert backup_path.exists()
    assert backup_path.name.startswith("aegis_baseline_v1_")
    
    # Modify original database
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE schema_meta SET value = 'modified_val' WHERE key = 'test_key'")
        )
        
    # AC 2 & Req 10 AC 8: Verify rollback by restoring backup over live database
    restore_db(paths, backup_path, engine)
    
    # Re-verify original data was restored successfully
    engine_new = make_engine(paths)
    with engine_new.connect() as conn:
        val = conn.execute(text("SELECT value FROM schema_meta WHERE key = 'test_key'")).scalar()
        assert val == "original_val"
        
    # AC 3 & Req 10 AC 9: Verify rotation of backups (retaining at most 10 newest backups)
    # Create 12 backup files manually to simulate multiple migration runs
    for i in range(12):
        # Stagger names lexicographically by numbering timestamp part
        backup_filename = f"aegis_baseline_v1_20260531_2000{i:02d}.db"
        p = paths.backups_db / backup_filename
        with open(p, "w") as f:
            f.write("dummy db content")
            
    rotate_backups(paths, keep=10)
    retained_backups = list(paths.backups_db.glob("aegis_*.db"))
    # Should keep exactly 10 total backups
    assert len(retained_backups) == 10
    
    # Clean up dummy backup rotation files and recheck
    for f in paths.backups_db.glob("aegis_*.db"):
        f.unlink(missing_ok=True)
        
    for i in range(15):
        p = paths.backups_db / f"aegis_baseline_v1_20260531_2000{i:02d}.db"
        p.touch()
        
    rotate_backups(paths, keep=10)
    retained = sorted([f.name for f in paths.backups_db.glob("aegis_*.db")])
    assert len(retained) == 10
    # Retained backups must be the 10 newest (timestamp indices 5 to 14)
    assert "aegis_baseline_v1_20260531_200004.db" not in retained
    assert "aegis_baseline_v1_20260531_200005.db" in retained
    assert "aegis_baseline_v1_20260531_200014.db" in retained

# -----------------------------------------------------------------------------
# Migrations & Rollback (Requirement 10)
# -----------------------------------------------------------------------------

def test_req10_migrations_boot_flow(tmp_path):
    """Req 10 AC 3, AC 4, AC 10: Verify migration runner boot-flow logic."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    engine = make_engine(paths)
    
    # AC 3: ScriptDirectory comparison logic
    alembic_cfg = Config("alembic.ini")
    script = ScriptDirectory.from_config(alembic_cfg)
    head_rev = script.get_current_head()
    assert head_rev == "add_revoked_tokens"
    
    # AC 4: Current revision equals head revision -> silent boot, no backups, no migrations
    Base.metadata.create_all(engine)
    # Manual stamp version
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE alembic_version (version_num VARCHAR(32) NOT NULL PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('add_revoked_tokens')"))
        
    success, reason = run_migrations(paths, engine)
    assert success is True
    assert reason is None
    # No backups should be created since it was already at head
    assert len(list(paths.backups_db.glob("aegis_*.db"))) == 0
    
    # AC 10: Database is ahead of application head -> Refuses downgrade and enters safe mode
    with engine.begin() as conn:
        conn.execute(text("UPDATE alembic_version SET version_num = 'future_v2'"))
        
    success, reason = run_migrations(paths, engine)
    assert success is False
    assert reason == ReasonCode.DB_RECOVERY

def test_req10_migration_failure_rollback(tmp_path):
    """Req 10 AC 8: Verify that migration upgrade failures trigger rollback and database restore."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    engine = make_engine(paths)
    # Database starts uninitialized (empty/no version table)
    # Inject a failing schema upgrade command to simulate migration failure
    # We do this by pointing to a mock configuration or letting command.upgrade raise exception
    import unittest.mock as mock
    
    # Run migrations once to head successfully
    success, reason = run_migrations(paths, engine)
    assert success is True
    assert reason is None
    
    # Database is now at 'baseline_v1'
    # Clear the DB and simulate upgrade failure by mocking command.upgrade
    with mock.patch("aegis.db.maintenance.command.upgrade", side_effect=RuntimeError("Alembic crashed!")):
        # Manually drop the version table so it tries to migrate
        with engine.begin() as conn:
            conn.execute(text("DROP TABLE alembic_version"))
            
        success, reason = run_migrations(paths, engine)
        assert success is False
        assert reason == ReasonCode.DB_RECOVERY
        
        # Verify migration_log contains status 'rolled_back'
        with engine.connect() as conn:
            status = conn.execute(text("SELECT status FROM migration_log ORDER BY id DESC LIMIT 1")).scalar()
            assert status == "rolled_back"

def test_req10_interrupted_migration_recovery(tmp_path):
    """Req 10 (Interrupted Boot Critical Fix C2): Verify interrupted boot recovery on startup."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    engine = make_engine(paths)
    Base.metadata.create_all(engine)
    
    # Create a backup file representing the pre-migration database state
    pre_mig_backup = paths.backups_db / "pre_mig_state.db"
    pre_mig_backup.touch()
    
    # Write a dangling 'started' status row into migration_log representing an interrupted run
    with engine.begin() as conn:
        conn.execute(
            text("INSERT INTO migration_log (from_rev, to_rev, backup_path, status) VALUES (:from_rev, :to_rev, :backup_path, :status)"),
            {"from_rev": "empty", "to_rev": "baseline_v1", "backup_path": str(pre_mig_backup), "status": "started"}
        )
        
    # The runner should scan the log, detect the dangling started row, restore the DB, and return db-recovery
    with mock.patch("aegis.db.maintenance.restore_db") as mock_restore:
        success, reason = run_migrations(paths, engine)
        assert success is False
        assert reason == ReasonCode.DB_RECOVERY
        mock_restore.assert_called_once()
        
        # The status should be updated to rolled_back
        with engine.connect() as conn:
            status = conn.execute(text("SELECT status FROM migration_log ORDER BY id DESC LIMIT 1")).scalar()
            assert status == "rolled_back"

# -----------------------------------------------------------------------------
# Configuration Sanitizer (Requirement 22)
# -----------------------------------------------------------------------------

def test_req22_configuration_sanitization():
    """Req 22 AC 1, AC 2, AC 3: Validate secret sanitization preserves structure and redacts credentials."""
    token = "MTIzNDU2NzE4OTAxMjM0NTY3.GD3a9B.abcdefghijklmnopqrstuvwxyz12345"
    jwt_secret = "super_secret_jwt_sign_key_123"
    
    raw_config = {
        "client_id": "1234567890",
        "ui_mode": "beginner",
        "bot_token": token,
        "welcome_settings": {
            "enabled": True,
            "channel_name": "welcome",
            "message_title": f"Welcome! Token inside text: {token}",
            "message_description": "Welcome to our server!",
            "embed_color": "#00FF00"
        },
        "automod_settings": {
            "enabled": False,
            "profanity_words": ["word1", "word2"]
        },
        "jwt_secret": jwt_secret,
        "admin_password_hash": "some_password_hash",
        "nested_tokens": [token, "not_a_token"]
    }
    
    sanitized = sanitize(raw_config)
    
    # AC 2: Redact secret values
    assert sanitized["bot_token"] == "***REDACTED***"
    assert sanitized["jwt_secret"] == "***REDACTED***"
    assert sanitized["admin_password_hash"] == "***REDACTED***"
    
    # AC 2: Redact heuristic patterns (Discord token pattern inside string and lists)
    assert token not in sanitized["welcome_settings"]["message_title"]
    assert "***REDACTED***" in sanitized["welcome_settings"]["message_title"]
    assert sanitized["nested_tokens"][0] == "***REDACTED***"
    assert sanitized["nested_tokens"][1] == "not_a_token"
    
    # AC 2: Preserve structure and non-secret keys
    assert sanitized["client_id"] == "1234567890"
    assert sanitized["ui_mode"] == "beginner"
    assert sanitized["welcome_settings"]["enabled"] is True
    assert sanitized["automod_settings"]["profanity_words"] == ["word1", "word2"]

# -----------------------------------------------------------------------------
# Configuration Loader & Saving (Requirement 5 & Requirement 8)
# -----------------------------------------------------------------------------

def test_req5_loader_atomic_saving(tmp_path):
    """Req 5 AC 5 & Req 8 AC 11: Validate configuration loading, atomic save, and rotation."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    # Configuration is initially missing -> FileNotFoundError
    with pytest.raises(FileNotFoundError):
        ConfigStore.load(paths)
        
    # Write a valid config file manually
    valid_data = get_valid_config_data()
    with open(paths.config_file, "w", encoding="utf-8") as f:
        json.dump(valid_data, f)
        
    store = ConfigStore.load(paths)
    assert store.is_setup_complete() is True
    assert store.ui_mode == "beginner"
    
    # Trigger atomic save and confirm backups
    store.save()
    assert paths.config_file.exists()
    
    backups = list(paths.backups_config.glob("config_*.json"))
    assert len(backups) == 1
    
    # Generate 12 dummy configuration backups to test rotation limits
    for i in range(12):
        p = paths.backups_config / f"config_20260531_2000{i:02d}.json"
        p.touch()
        
    store.save()
    retained_config_backups = list(paths.backups_config.glob("config_*.json"))
    # Should keep exactly 10 total backups
    assert len(retained_config_backups) == 10

# -----------------------------------------------------------------------------
# AppCore Integration & Exception Boundary (Requirement 1 & Requirement 5)
# -----------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_appcore_integration_config_failure(tmp_path):
    """Req 5 AC 5: AppCore transitions to SAFE_MODE(needs-setup) when config load fails."""
    paths = Paths(root=tmp_path / "aegis")
    # Do not write any config file (triggering FileNotFoundError)
    
    core = AppCore(paths=paths)
    core._shutdown_event.set()  # Prevent wait hanging
    
    exit_code = await core.run()
    assert exit_code == 0
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core.state.reason == ReasonCode.NEEDS_SETUP
    assert core.health.safe_mode["active"] is True
    assert core.health.safe_mode["reason"] == "needs-setup"

@pytest.mark.asyncio
async def test_appcore_integration_db_failure(tmp_path):
    """Req 5 AC 6: AppCore transitions to SAFE_MODE(db-recovery) when database setup fails."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    # Save a valid config file to pass setup check
    valid_data = get_valid_config_data()
    with open(paths.config_file, "w", encoding="utf-8") as f:
        json.dump(valid_data, f)
        
    # Simulate DB corruption by writing bad bytes
    with open(paths.db_file, "w") as f:
        f.write("corrupted db file content here")
        
    core = AppCore(paths=paths)
    core._shutdown_event.set()
    
    exit_code = await core.run()
    assert exit_code == 0
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core.state.reason == ReasonCode.DB_RECOVERY
    assert core.health.safe_mode["active"] is True
    assert core.health.safe_mode["reason"] == "db-recovery"

@pytest.mark.asyncio
async def test_appcore_integration_happy_path(tmp_path):
    """Req 2 AC 3: AppCore transitions successfully to RUNNING state on clean startup checks."""
    paths = Paths(root=tmp_path / "aegis")
    paths.ensure()
    
    # Save a valid config file
    valid_data = get_valid_config_data()
    with open(paths.config_file, "w", encoding="utf-8") as f:
        json.dump(valid_data, f)
        
    core = AppCore(paths=paths)
    core._shutdown_event.set()
    
    # Override run_migrations programmatically in tests so it doesn't try to lock files during multiple test runs
    from unittest.mock import patch
    from aegis.bot.runner import TokenVerdict
    
    with patch("aegis.bot.runner.validate_token", return_value=TokenVerdict.OK):
        exit_code = await core.run()
        
    assert exit_code == 0
    assert core.state.current_state == LifecycleState.RUNNING
