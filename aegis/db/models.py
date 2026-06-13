import datetime
from sqlalchemy import Column, String, Text, DateTime, Integer, ForeignKey
from sqlalchemy.orm import declarative_base

Base = declarative_base()

def get_utcnow() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)

class SchemaMeta(Base):
    """Schema metadata table for tracking database version and app metadata."""
    __tablename__ = "schema_meta"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=True)

class ConfigKV(Base):
    """Key-value config store for DB-backed settings."""
    __tablename__ = "config_kv"
    
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=get_utcnow, onupdate=get_utcnow)

class Template(Base):
    """Template structures storage (builtin, custom, imported, cloned)."""
    __tablename__ = "templates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    kind = Column(String, nullable=False)  # gaming, community, creator, custom
    json = Column(Text, nullable=False)    # validated JSON document
    source = Column(String, nullable=False)  # builtin, imported, cloned
    created_at = Column(DateTime, default=get_utcnow)

class Server(Base):
    """Discord servers (guilds) tracking table."""
    __tablename__ = "servers"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=True)
    mode = Column(String, nullable=True)
    last_synced = Column(DateTime, nullable=True)

class ApplyHistory(Base):
    """History of template application results to specific servers."""
    __tablename__ = "apply_history"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    server_id = Column(Integer, ForeignKey("servers.id", ondelete="CASCADE"), nullable=False)
    template_id = Column(Integer, ForeignKey("templates.id", ondelete="CASCADE"), nullable=False)
    applied_at = Column(DateTime, default=get_utcnow)
    result = Column(Text, nullable=True)

class MigrationLog(Base):
    """Log of database migration execution status."""
    __tablename__ = "migration_log"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    from_rev = Column(String, nullable=True)
    to_rev = Column(String, nullable=True)
    backup_path = Column(String, nullable=True)
    status = Column(String, nullable=False)  # started, success, rolled_back
    ts = Column(DateTime, default=get_utcnow)

class RevokedToken(Base):
    """Table for storing revoked session tokens."""
    __tablename__ = "revoked_tokens"
    
    token = Column(String, primary_key=True)
    revoked_at = Column(DateTime, default=get_utcnow)

class RaidEvent(Base):
    """Detected raid events for historical analysis and dashboard display."""
    __tablename__ = "raid_events"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, index=True, nullable=False)
    detected_at = Column(DateTime, default=get_utcnow)
    join_count = Column(Integer, nullable=False)
    window_seconds = Column(Integer, nullable=False)
    response_action = Column(String, nullable=False)
    members_affected = Column(Text, nullable=True)  # JSON list of user IDs
    resolved = Column(Integer, default=0, nullable=False)

class ConfigSnapshot(Base):
    """Config version history snapshots for rollback support."""
    __tablename__ = "config_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    config_json = Column(Text, nullable=False)
    change_summary = Column(String, nullable=True)
    changed_keys = Column(Text, nullable=True)
    created_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=get_utcnow)

class Giveaway(Base):
    """Giveaway entries migrated from giveaways.json."""
    __tablename__ = "giveaways"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    message_id = Column(String, unique=True)
    channel_id = Column(String)
    prize = Column(String)
    winner_count = Column(Integer, default=1)
    end_time = Column(DateTime, nullable=True)
    host_user_id = Column(String)
    host_name = Column(String, nullable=True)
    status = Column(String, default="active")  # active, ended
    entrants = Column(Text, nullable=True)  # JSON list of user IDs
    winners = Column(Text, nullable=True)  # JSON list of winner IDs
    created_at = Column(DateTime, default=get_utcnow)

class AuditEntry(Base):
    """Audit log entries migrated from audit_log.json."""
    __tablename__ = "audit_entries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    guild_id = Column(String, nullable=False, index=True)
    user_id = Column(String, index=True)
    action = Column(String, index=True)
    details = Column(Text)
    timestamp = Column(DateTime, default=get_utcnow)
