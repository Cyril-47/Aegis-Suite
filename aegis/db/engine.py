import logging
from sqlalchemy import create_engine, event, Engine
from sqlalchemy.orm import sessionmaker
from aegis.core.paths import Paths

logger = logging.getLogger("aegis.db.engine")

def make_engine(paths: Paths) -> Engine:
    """Creates a SQLAlchemy engine for SQLite at Paths.db_file with WAL and FK pragmas."""
    db_url = f"sqlite:///{paths.db_file.resolve()}"
    logger.info(f"Creating database engine at {paths.db_file.name}")
    
    import sys
    import os
    kwargs = {}
    if "pytest" in sys.modules or "PYTEST_CURRENT_TEST" in os.environ:
        from sqlalchemy.pool import StaticPool
        kwargs["poolclass"] = StaticPool
        
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        **kwargs
    )
    
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
        finally:
            cursor.close()
            
    return engine

def make_sessionmaker(engine: Engine) -> sessionmaker:
    """Creates a sessionmaker bound to the given engine."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)
