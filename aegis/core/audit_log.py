import json
import os
import datetime
import threading
import aegis.core.utils as utils

AUDIT_LOG_PATH = utils.get_writeable_path("audit_log.json")
MAX_LOG_ENTRIES = 1000
log_lock = threading.Lock()

def log_action(actor: str, category: str, action: str, target: str = None, details: str = None):
    """Logs a dashboard action to audit_log.json with rotation."""
    entry = {
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
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
            print(f"Failed to save audit log: {e}")

def get_logs(category: str = None, limit: int = 100, offset: int = 0, guild_id: str = None) -> dict:
    """Retrieves audit logs filtered by category with pagination."""
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
    paginated_logs = filtered_logs[offset:offset+limit]
    
    return {
        "total": total,
        "logs": paginated_logs
    }
