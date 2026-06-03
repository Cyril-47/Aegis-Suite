import os
import zipfile
import json
import logging
import datetime
import time
from pathlib import Path
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text

from aegis.core.paths import Paths
from aegis.config.sanitizer import sanitize
from aegis.db.maintenance import integrity_check, get_current_revision
from aegis.db.models import SchemaMeta

logger = logging.getLogger("aegis.diagnostics.packager")

def get_tail(file_path: Path, max_lines: int = 1000) -> str:
    """Returns the last max_lines of the specified file."""
    if not file_path.exists() or not file_path.is_file():
        return ""
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
            return "".join(lines[-max_lines:])
    except Exception as e:
        return f"<Error reading log file: {e}>"

def get_app_version(db_engine) -> str:
    """Retrieves the app version from the SchemaMeta table."""
    if not db_engine:
        return "1.0.0"
    Session = sessionmaker(bind=db_engine)
    try:
        with Session() as session:
            version_meta = session.query(SchemaMeta).filter(SchemaMeta.key == "version").first()
            if version_meta:
                return version_meta.value
    except Exception:
        pass
    return "1.0.0"

def generate_package(core) -> Path:
    """Assembles a timestamped ZIP package containing logs and system status under diagnostics.
    Reads only, never mutates state.
    """
    diagnostics_dir = core.paths.diagnostics
    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_filename = f"aegis_diag_{timestamp}.zip"
    zip_path = diagnostics_dir / zip_filename
    
    # 1. Gather database status
    db_size = 0
    if core.paths.db_file.exists():
        try:
            db_size = core.paths.db_file.stat().st_size
        except Exception:
            pass
            
    db_ok = False
    if core.db:
        try:
            db_ok = integrity_check(core.db)
        except Exception:
            pass
            
    schema_rev = None
    if core.db:
        try:
            schema_rev = get_current_revision(core.db)
        except Exception:
            pass
            
    app_version = get_app_version(core.db)
    
    # 2. Calculate uptime
    uptime_seconds = 0.0
    if hasattr(core, "_start_time"):
        uptime_seconds = time.time() - core._start_time
        
    # 3. Gather runtime info
    info = {
        "app_version": app_version,
        "database_status": {
            "integrity_ok": db_ok,
            "schema_revision": schema_rev,
            "file_size_bytes": db_size
        },
        "runtime_status": {
            "lifecycle_state": str(core.state.current_state),
            "uptime_seconds": uptime_seconds,
            "safe_mode_reason": str(core.state.reason) if core.state.reason else None
        },
        "config_snapshot": core.config.as_dict() if core.config else {}
    }
    
    # Sanitize config and other secret keys inside info
    sanitized_info = sanitize(info)
    
    # 4. Write zip archive
    # Packager must write ONLY under the diagnostics directory
    from aegis.config.sanitizer import redact_text
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Write sanitized info.json
        info_json_str = json.dumps(sanitized_info, indent=4)
        info_json_str = redact_text(info_json_str)
        zipf.writestr("info.json", info_json_str)
        
        # Write tails of log files
        log_tail = get_tail(core.paths.log_file)
        if log_tail:
            zipf.writestr("aegis.log", redact_text(log_tail))
            
        err_log_tail = get_tail(core.paths.err_log_file)
        if err_log_tail:
            zipf.writestr("aegis.err.log", redact_text(err_log_tail))
            
    return zip_path
