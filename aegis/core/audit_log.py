import json
import os
import logging
import threading
from datetime import datetime, timezone

import aegis.core.utils as utils

AUDIT_LOG_PATH = utils.get_writeable_path("audit_log.json")
MAX_LOG_ENTRIES = 1000
log_lock = threading.Lock()
logger = logging.getLogger("aegis.core.audit_log")


def _get_db_session():
    """Get a database session if available."""
    try:
        from aegis.core.app_core import _active_cores
        if _active_cores:
            from sqlalchemy.orm import sessionmaker
            core = _active_cores[-1]
            if core.db:
                return sessionmaker(bind=core.db)()
    except Exception:
        pass
    return None


def log_action(actor: str, category: str, action: str, target: str = None, details: str = None):
    """Log an audit action. Writes to both DB and JSON file for backward compatibility."""
    session = _get_db_session()
    if session:
        try:
            from aegis.db.models import AuditEntry
            session.add(AuditEntry(
                guild_id=str(target) if target else "global",
                user_id=actor,
                action=category,
                details=action,
            ))
            session.commit()
        except Exception:
            session.rollback()
            logger.debug("DB audit log write failed")
        finally:
            session.close()

    # Always write to JSON for backward compatibility with tests and consumers
    _log_to_json(actor, category, action, target, details)


def _log_to_json(actor: str, category: str, action: str, target: str = None, details: str = None):
    """Fallback: write to audit_log.json."""
    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": actor,
        "category": category,
        "action": action,
        "target": target or "N/A",
        "details": details or ""
    }

    with log_lock:
        logs = []
        if os.path.exists(AUDIT_LOG_PATH):
            try:
                with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                logs = []

        logs.insert(0, entry)
        logs = logs[:MAX_LOG_ENTRIES]

        try:
            with open(AUDIT_LOG_PATH, "w", encoding="utf-8") as f:
                json.dump(logs, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save audit log: {e}")


def get_logs(category: str = None, limit: int = 100, offset: int = 0, guild_id: str = None) -> dict:
    """Retrieve audit logs with pagination. DB-backed when available."""
    session = _get_db_session()
    if session:
        try:
            from aegis.db.models import AuditEntry

            q = session.query(AuditEntry)
            if guild_id:
                q = q.filter(AuditEntry.guild_id == str(guild_id))
            if category and category != "ALL":
                q = q.filter(AuditEntry.action == category)

            total = q.count()
            entries = q.order_by(AuditEntry.timestamp.desc()).offset(offset).limit(limit).all()

            return {
                "total": total,
                "logs": [
                    {
                        "actor": e.user_id,
                        "category": e.action,
                        "action": e.details,
                        "target": e.guild_id,
                        "timestamp": e.timestamp.isoformat() if e.timestamp else None,
                    }
                    for e in entries
                ],
            }
        except Exception:
            logger.debug("DB audit log read failed, falling back to JSON")
        finally:
            session.close()

    return _get_from_json(category, limit, offset, guild_id)


def _get_from_json(category: str = None, limit: int = 100, offset: int = 0, guild_id: str = None) -> dict:
    """Fallback: read from audit_log.json."""
    with log_lock:
        logs = []
        if os.path.exists(AUDIT_LOG_PATH):
            try:
                with open(AUDIT_LOG_PATH, "r", encoding="utf-8") as f:
                    logs = json.load(f)
            except Exception:
                pass

    if guild_id:
        logs = [log for log in logs if log.get("target") == str(guild_id)]

    if category and category != "ALL":
        filtered_logs = [log for log in logs if log.get("category") == category]
    else:
        filtered_logs = logs

    total = len(filtered_logs)
    paginated_logs = filtered_logs[offset:offset + limit]

    return {
        "total": total,
        "logs": paginated_logs,
    }
