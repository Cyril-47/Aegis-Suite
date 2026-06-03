import os
import shutil
import logging
import sqlite3
import datetime
import asyncio
from pathlib import Path
from typing import Optional, Tuple
from sqlalchemy import Engine, text
from alembic.config import Config
from alembic import command
from alembic.script import ScriptDirectory
from aegis.core.paths import Paths
from aegis.core.state import ReasonCode

logger = logging.getLogger("aegis.db.maintenance")

def integrity_check(engine: Engine) -> bool:
    """Executes PRAGMA integrity_check and returns True if successful."""
    logger.info("Executing database integrity check")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("PRAGMA integrity_check")).scalar()
            logger.info(f"Integrity check result: {result}")
            return result == "ok"
    except Exception as e:
        logger.error(f"Database integrity check failed: {e}")
        return False

def backup_db(paths: Paths, engine: Engine, current_rev: str) -> Path:
    """Performs a transactionally consistent online backup of the SQLite database."""
    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_filename = f"aegis_{current_rev}_{ts}.db"
    backup_file = paths.backups_db / backup_filename
    
    logger.info(f"Initiating online database backup to {backup_file}")
    paths.backups_db.mkdir(parents=True, exist_ok=True)
    
    # Use SQLite Online Backup API by extracting raw DBAPI connection
    raw_conn = engine.raw_connection()
    try:
        dbapi_conn = getattr(raw_conn, "driver_connection", getattr(raw_conn, "connection", None))
        if dbapi_conn is None:
            raise RuntimeError("Could not extract raw DBAPI connection from engine")
            
        dest_conn = sqlite3.connect(backup_file)
        try:
            dbapi_conn.backup(dest_conn)
        finally:
            dest_conn.close()
    finally:
        raw_conn.close()
        
    logger.info("Online database backup completed successfully")
    return backup_file

async def backup_db_async(paths: Paths, engine: Engine, current_rev: str) -> Path:
    """Awaitable wrapper to run the blocking backup on a background thread."""
    return await asyncio.to_thread(backup_db, paths, engine, current_rev)

def restore_db(paths: Paths, backup_path: Path, engine: Optional[Engine] = None) -> None:
    """Restores database from backup, disposing connections and removing sidecars."""
    logger.warning(f"Restoring database from backup: {backup_path}")
    if engine is not None:
        engine.dispose()
        
    db_file = paths.db_file
    wal_file = Path(str(db_file) + "-wal")
    shm_file = Path(str(db_file) + "-shm")
    
    # Remove database file and sidecars to prevent corruption
    db_file.unlink(missing_ok=True)
    wal_file.unlink(missing_ok=True)
    shm_file.unlink(missing_ok=True)
    
    shutil.copy2(backup_path, db_file)
    logger.info("Database restore complete")

def rotate_backups(paths: Paths, keep: int = 10) -> None:
    """Retains only the 10 most recent backups, deleting older ones."""
    if not paths.backups_db.exists():
        return
        
    backups = list(paths.backups_db.glob("aegis_*.db"))
    # Sort by filesystem modification time, using filename as tie-breaker (oldest first)
    backups.sort(key=lambda p: (p.stat().st_mtime, p.name))
    
    if len(backups) > keep:
        to_delete = backups[:-keep]
        for p in to_delete:
            logger.info(f"Removing rotated backup: {p}")
            p.unlink(missing_ok=True)

def get_current_revision(engine: Engine) -> Optional[str]:
    """Retrieves the current schema revision from the database."""
    try:
        with engine.connect() as conn:
            # Query alembic_version table
            res = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
            return res
    except Exception:
        # Table alembic_version doesn't exist yet or query failed
        return None

def is_db_ahead(engine: Engine, head_rev: str, alembic_cfg: Config) -> bool:
    """Determines if the database schema is ahead of the current codebase head."""
    current = get_current_revision(engine)
    if not current:
        return False
        
    script = ScriptDirectory.from_config(alembic_cfg)
    try:
        script.get_revision(current)
        # If the revision is recognized and is not the head, check if it's behind or head
        heads = script.get_heads()
        if current in heads:
            return False
        # If it parses and isn't head, it is an ancestor of head (behind)
        return False
    except Exception:
        # ScriptDirectory cannot parse it, meaning current rev is not known to this codebase build
        logger.error(f"Database revision '{current}' is unknown to this build (head revision: '{head_rev}')")
        return True

def table_exists(engine: Engine, table_name: str) -> bool:
    """Checks if a table exists in the database schema."""
    try:
        with engine.connect() as conn:
            res = conn.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": table_name}
            ).fetchone()
            return res is not None
    except Exception:
        return False

def run_migrations(paths: Paths, engine: Engine, alembic_ini_path: str = "alembic.ini") -> Tuple[bool, Optional[ReasonCode]]:
    """Programmatic migration runner with backups, rollback safety, and interrupted run recovery."""
    import sys
    if getattr(sys, 'frozen', False):
        bundle_dir = sys._MEIPASS
        ini_path = os.path.join(bundle_dir, "alembic.ini")
        alembic_cfg = Config(ini_path)
        alembic_cfg.set_main_option("script_location", os.path.join(bundle_dir, "aegis", "db", "migrations"))
    else:
        alembic_cfg = Config(alembic_ini_path)
        
    script = ScriptDirectory.from_config(alembic_cfg)
    head_rev = script.get_current_head()
    
    # 1. Check for interrupted/dangling migration runs first
    interrupted = False
    dangling_row_id = None
    dangling_backup_path = None
    
    if table_exists(engine, "migration_log"):
        try:
            with engine.connect() as conn:
                res = conn.execute(
                    text("SELECT id, backup_path, status FROM migration_log ORDER BY id DESC LIMIT 1")
                ).fetchone()
                if res and res[2] == "started":
                    interrupted = True
                    dangling_row_id = res[0]
                    dangling_backup_path = res[1]
        except Exception as e:
            logger.error(f"Error checking migration_log for interrupted runs: {e}")
        
    if interrupted:
        logger.warning(f"Interrupted migration detected (migration_log id: {dangling_row_id})")
        if dangling_backup_path and os.path.exists(dangling_backup_path):
            try:
                restore_db(paths, Path(dangling_backup_path), engine)
                # Mark dangling log entry as rolled_back
                with engine.begin() as conn:
                    conn.execute(
                        text("UPDATE migration_log SET status = 'rolled_back' WHERE id = :id"),
                        {"id": dangling_row_id}
                    )
            except Exception as e:
                logger.error(f"Failed to restore DB from {dangling_backup_path} during interrupted recovery: {e}")
        else:
            logger.error("No usable backup path found for the interrupted migration")
            
        return False, ReasonCode.DB_RECOVERY

    # 2. Check current database revision and run comparison
    current_rev = get_current_revision(engine)
    logger.info(f"Database status - Current Revision: {current_rev}, Head Revision: {head_rev}")
    
    if current_rev == head_rev:
        logger.info("Database is at head revision. No migrations required.")
        return True, None
    
    if is_db_ahead(engine, head_rev, alembic_cfg):
        logger.error("Database schema version is ahead of this build. Refusing to downgrade.")
        return False, ReasonCode.DB_RECOVERY
        
    # 3. Database is behind head, perform migration
    backup_path = None
    
    # Generate timestamped backup first
    try:
        backup_path = backup_db(paths, engine, current_rev or "empty")
    except Exception as e:
        logger.error(f"Failed to create database backup before migration: {e}")
        # Capture failure in migration_log if the table exists
        if table_exists(engine, "migration_log"):
            try:
                with engine.begin() as conn:
                    conn.execute(
                        text("INSERT INTO migration_log (from_rev, to_rev, backup_path, status) VALUES (:from_rev, :to_rev, :backup_path, :status)"),
                        {"from_rev": current_rev, "to_rev": head_rev, "backup_path": None, "status": "rolled_back"}
                    )
            except Exception:
                pass
        return False, ReasonCode.DB_RECOVERY

    # Insert 'started' log entry
    log_id = None
    if table_exists(engine, "migration_log"):
        try:
            with engine.begin() as conn:
                cursor = conn.execute(
                    text("INSERT INTO migration_log (from_rev, to_rev, backup_path, status) VALUES (:from_rev, :to_rev, :backup_path, :status)"),
                    {"from_rev": current_rev, "to_rev": head_rev, "backup_path": str(backup_path), "status": "started"}
                )
                log_id = cursor.lastrowid
                if log_id is None:
                    log_id = conn.execute(text("SELECT max(id) FROM migration_log")).scalar()
        except Exception as e:
            logger.error(f"Failed to log migration start: {e}")

    # Run upgrade
    migration_success = False
    try:
        with engine.connect() as connection:
            alembic_cfg.attributes["connection"] = connection
            command.upgrade(alembic_cfg, "head")
        migration_success = True
    except Exception as e:
        logger.error(f"Alembic database upgrade failed: {e}")

    if migration_success:
        logger.info(f"Database upgrade to {head_rev} succeeded")
        # Update log row to success if it was inserted, or create a success entry if the table now exists
        if table_exists(engine, "migration_log"):
            try:
                with engine.begin() as conn:
                    if log_id:
                        conn.execute(
                            text("UPDATE migration_log SET status = 'success' WHERE id = :id"),
                            {"id": log_id}
                        )
                    else:
                        conn.execute(
                            text("INSERT INTO migration_log (from_rev, to_rev, backup_path, status) VALUES (:from_rev, :to_rev, :backup_path, :status)"),
                            {"from_rev": current_rev, "to_rev": head_rev, "backup_path": str(backup_path) if backup_path else None, "status": "success"}
                        )
            except Exception as e:
                logger.error(f"Failed to record migration success in migration_log: {e}")
        
        rotate_backups(paths, keep=10)
        return True, None
    else:
        # Migration failed, execute WAL-safe rollback restore
        logger.warning("Rolling back database migration changes")
        try:
            restore_db(paths, backup_path, engine)
            # Record rolled_back entry. Note: the restored DB might have the table if we rolled back an update of a V1 schema DB.
            if table_exists(engine, "migration_log"):
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("INSERT INTO migration_log (from_rev, to_rev, backup_path, status) VALUES (:from_rev, :to_rev, :backup_path, :status)"),
                            {"from_rev": current_rev, "to_rev": head_rev, "backup_path": str(backup_path) if backup_path else None, "status": "rolled_back"}
                        )
                except Exception as e:
                    logger.error(f"Failed to record rolled_back entry in restored database: {e}")
        except Exception as e:
            logger.error(f"Failed to restore database during migration rollback: {e}")
            if log_id and table_exists(engine, "migration_log"):
                try:
                    with engine.begin() as conn:
                        conn.execute(
                            text("UPDATE migration_log SET status = 'rolled_back' WHERE id = :id"),
                            {"id": log_id}
                        )
                except Exception:
                    pass
        return False, ReasonCode.DB_RECOVERY
