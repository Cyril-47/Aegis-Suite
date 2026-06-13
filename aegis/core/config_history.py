import json
import logging
from typing import Optional, List
from aegis.db.models import ConfigSnapshot

logger = logging.getLogger("aegis.core.config_history")


def get_db_session():
    from aegis.core.app_core import _active_cores
    if _active_cores:
        from sqlalchemy.orm import sessionmaker
        core = _active_cores[-1]
        if core.db:
            return sessionmaker(bind=core.db)()
    return None


def create_snapshot(guild_id: str, config_data: dict, changed_keys: List[str] = None, created_by: str = None):
    """Create a config snapshot before saving."""
    session = get_db_session()
    if not session:
        return
    try:
        snapshot = ConfigSnapshot(
            guild_id=guild_id,
            config_json=json.dumps(config_data, default=str),
            changed_keys=json.dumps(changed_keys) if changed_keys else None,
            created_by=created_by,
        )
        session.add(snapshot)
        session.commit()

        # Prune old snapshots (keep last 50 per guild)
        from sqlalchemy import func
        count = session.query(func.count(ConfigSnapshot.id)).filter(
            ConfigSnapshot.guild_id == guild_id
        ).scalar()
        if count > 50:
            oldest = session.query(ConfigSnapshot).filter(
                ConfigSnapshot.guild_id == guild_id
            ).order_by(ConfigSnapshot.created_at.asc()).limit(count - 50).all()
            for s in oldest:
                session.delete(s)
            session.commit()
    except Exception:
        session.rollback()
        logger.exception("Failed to create config snapshot")
    finally:
        session.close()


def get_history(guild_id: str, limit: int = 20, offset: int = 0) -> dict:
    """Get config history for a guild."""
    session = get_db_session()
    if not session:
        return {"snapshots": [], "total": 0}
    try:
        from sqlalchemy import func
        total = session.query(func.count(ConfigSnapshot.id)).filter(
            ConfigSnapshot.guild_id == guild_id
        ).scalar()
        snapshots = session.query(ConfigSnapshot).filter(
            ConfigSnapshot.guild_id == guild_id
        ).order_by(ConfigSnapshot.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "snapshots": [
                {
                    "id": s.id,
                    "created_at": s.created_at.isoformat() if s.created_at else None,
                    "change_summary": s.change_summary,
                    "changed_keys": json.loads(s.changed_keys) if s.changed_keys else [],
                    "created_by": s.created_by,
                }
                for s in snapshots
            ],
            "total": total,
        }
    finally:
        session.close()


def get_snapshot(snapshot_id: int) -> Optional[dict]:
    """Get a specific snapshot with full config."""
    session = get_db_session()
    if not session:
        return None
    try:
        s = session.query(ConfigSnapshot).filter(ConfigSnapshot.id == snapshot_id).first()
        if not s:
            return None
        return {
            "id": s.id,
            "guild_id": s.guild_id,
            "config": json.loads(s.config_json),
            "change_summary": s.change_summary,
            "changed_keys": json.loads(s.changed_keys) if s.changed_keys else [],
            "created_by": s.created_by,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
    finally:
        session.close()


def compute_diff(old_config: dict, new_config: dict) -> List[str]:
    """Compute list of changed keys between two configs."""
    changed = []
    all_keys = set(list(old_config.keys()) + list(new_config.keys()))
    for key in all_keys:
        old_val = old_config.get(key)
        new_val = new_config.get(key)
        if old_val != new_val:
            changed.append(key)
    return changed
