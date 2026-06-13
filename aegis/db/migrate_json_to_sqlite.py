"""One-time migration scripts to import JSON data into SQLite tables."""
import json
import logging

logger = logging.getLogger("aegis.db.migrate")


def migrate_giveaways(session_factory) -> int:
    """Import giveaways.json into the giveaways table. Returns count of migrated entries."""
    from aegis.db.models import Giveaway
    from aegis.core.paths import Paths
    
    paths = Paths()
    json_path = paths.root / "giveaways.json"
    if not json_path.exists():
        logger.info("No giveaways.json found, skipping migration")
        return 0
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            giveaways = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to read giveaways.json: {e}")
        return 0
    
    if not giveaways:
        logger.info("giveaways.json is empty, skipping migration")
        return 0
    
    session = session_factory()
    count = 0
    try:
        from datetime import datetime
        for g in giveaways:
            # Check if already migrated (by message_id)
            msg_id = g.get("message_id", "")
            if msg_id and session.query(Giveaway).filter(Giveaway.message_id == msg_id).first():
                continue
            
            end_time = None
            if g.get("end_time"):
                try:
                    end_time = datetime.fromisoformat(g["end_time"])
                except (ValueError, TypeError):
                    pass
            
            session.add(Giveaway(
                guild_id=g.get("guild_id", ""),
                message_id=msg_id,
                channel_id=g.get("channel_id", ""),
                prize=g.get("prize", ""),
                winner_count=g.get("winner_count", 1),
                end_time=end_time,
                host_user_id=g.get("host_user_id", ""),
                status=g.get("status", "active"),
                winners=json.dumps(g.get("winners", [])) if g.get("winners") else None,
            ))
            count += 1
        
        session.commit()
        
        # Rename old file
        backup_path = json_path.with_suffix(".json.migrated")
        backup_path.unlink(missing_ok=True)
        json_path.rename(backup_path)
        logger.info(f"Migrated {count} giveaways from {json_path.name} to {backup_path.name}")
        
    except Exception:
        session.rollback()
        logger.exception("Giveaway migration failed")
        count = 0
    finally:
        session.close()
    
    return count


def migrate_audit_log(session_factory) -> int:
    """Import audit_log.json into the audit_entries table. Returns count of migrated entries."""
    from aegis.db.models import AuditEntry
    from aegis.core.paths import Paths
    
    paths = Paths()
    json_path = paths.root / "audit_log.json"
    if not json_path.exists():
        logger.info("No audit_log.json found, skipping migration")
        return 0
    
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to read audit_log.json: {e}")
        return 0
    
    if not entries:
        logger.info("audit_log.json is empty, skipping migration")
        return 0
    
    session = session_factory()
    count = 0
    try:
        from datetime import datetime
        for entry in entries:
            ts = None
            if entry.get("timestamp"):
                try:
                    ts = datetime.fromisoformat(entry["timestamp"])
                except (ValueError, TypeError):
                    pass
            
            session.add(AuditEntry(
                guild_id=entry.get("guild_id", "global"),
                user_id=entry.get("user", ""),
                action=entry.get("action", ""),
                details=entry.get("details", ""),
                timestamp=ts,
            ))
            count += 1
        
        session.commit()
        
        backup_path = json_path.with_suffix(".json.migrated")
        backup_path.unlink(missing_ok=True)
        json_path.rename(backup_path)
        logger.info(f"Migrated {count} audit entries from {json_path.name} to {backup_path.name}")
        
    except Exception:
        session.rollback()
        logger.exception("Audit log migration failed")
        count = 0
    finally:
        session.close()
    
    return count


def run_all_migrations(session_factory) -> dict:
    """Run all JSON-to-SQLite migrations. Returns summary."""
    giveaways_migrated = migrate_giveaways(session_factory)
    audit_migrated = migrate_audit_log(session_factory)
    return {
        "giveaways_migrated": giveaways_migrated,
        "audit_entries_migrated": audit_migrated,
    }
