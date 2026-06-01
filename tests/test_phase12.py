import os
import json
import pytest
from pathlib import Path
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from aegis.core.paths import Paths
from aegis.db.models import Base, SchemaMeta
from aegis.db.maintenance import run_migrations, is_db_ahead, get_current_revision
from aegis.core.state import LifecycleState, ReasonCode
from aegis.core.app_core import AppCore

def test_installer_upgrade_path(paths_tmp):
    """Verify that starting AppCore on a pre-existing database runs migrations."""
    # 1. Initialize a database file under paths_tmp
    engine = create_engine(f"sqlite:///{paths_tmp.db_file}")
    with engine.connect() as conn:
        pass
    
    # Write a dummy config
    config_data = {
        "setup_complete": True,
        "client_id": "11112222",
        "hosting_mode": "cloud",
        "welcome_settings": {
            "enabled": True,
            "channel_id": None,
            "channel_name": "welcome",
            "message_title": "Welcome",
            "message_description": "Hello",
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
        "ticket_settings": {
            "enabled": False,
            "category_name": "SUPPORT",
            "staff_role_name": "Moderator",
            "ticket_channel_id": None,
            "panel_message_id": None
        }
    }
    with open(paths_tmp.config_file, "w", encoding="utf-8") as f:
        json.dump(config_data, f)
        
    # Simulate an upgrade by booting AppCore on this database
    core = AppCore(paths=paths_tmp)
    
    # Mock uvicorn/browser calls to avoid blocking loop execution
    core.web_port = 8000
    
    # Run startup check path (Migrations Check)
    from aegis.core.lifecycle import run_startup_checks
    # We run the first 4 checks
    async def run():
        verdict, reason = await run_startup_checks(core, start_at=1, end_at=4)
        return verdict, reason
        
    import asyncio
    verdict, reason = asyncio.run(run())
    
    # Should complete without errors
    assert verdict != "FATAL-to-bot"
    assert core.health.database["reachable"] is True
    assert core.health.database["at_head"] is True

def test_installer_downgrade_refusal(paths_tmp):
    """Verify that starting AppCore against a newer database schema is refused."""
    engine = create_engine(f"sqlite:///{paths_tmp.db_file}")
    Base.metadata.create_all(engine)
    
    # Seed alembic_version with a dummy "ahead" revision (e.g., 'future_rev')
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) PRIMARY KEY)"))
        conn.execute(text("INSERT INTO alembic_version (version_num) VALUES ('future_rev')"))
        
    # Verify is_db_ahead detects it
    from alembic.config import Config
    alembic_cfg = Config("alembic.ini")
    assert is_db_ahead(engine, "baseline_rev", alembic_cfg) is True
    
    # Build AppCore and run checks
    core = AppCore(paths=paths_tmp)
    
    from aegis.core.lifecycle import run_startup_checks
    async def run():
        verdict, reason = await run_startup_checks(core, start_at=4, end_at=4)
        return verdict, reason
        
    import asyncio
    verdict, reason = asyncio.run(run())
    
    # Must refuse downgrade and enter SAFE_MODE
    assert verdict == "FATAL-to-bot"
    assert reason == ReasonCode.DB_RECOVERY
