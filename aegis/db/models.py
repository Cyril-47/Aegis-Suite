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
