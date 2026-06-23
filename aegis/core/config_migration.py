"""
Configuration Migration Utility.

Helps migrate from the old config system to the new unified ConfigManager.
"""

import json
import logging
import os
import shutil
import time
from pathlib import Path
from typing import Dict, Any, Optional

logger = logging.getLogger("aegis.config.migration")


def migrate_config(config_path: str, backup: bool = True) -> bool:
    """
    Migrate configuration to the new unified format.
    
    Args:
        config_path: Path to the configuration file
        backup: Whether to create a backup before migration
    
    Returns:
        True if migration succeeded, False otherwise
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        logger.warning(f"Config file not found: {config_file}")
        return False
    
    # Create backup if requested
    if backup:
        backup_path = create_backup(config_file)
        if backup_path:
            logger.info(f"Backup created: {backup_path}")
    
    try:
        # Load current config
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Apply migration transformations
        migrated_config = apply_migrations(config)
        
        # Save migrated config
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(migrated_config, f, indent=2)
        
        logger.info("Configuration migration completed successfully")
        return True
        
    except Exception as e:
        logger.error(f"Configuration migration failed: {e}")
        return False


def apply_migrations(config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply migration transformations to config.
    
    This function handles:
    - Renaming deprecated keys
    - Restructuring nested objects
    - Adding missing default values
    - Removing obsolete keys
    """
    migrated = config.copy()
    
    # Migration 1: Rename admin_password to admin_password_hash
    if "admin_password" in migrated and "admin_password_hash" not in migrated:
        migrated["admin_password_hash"] = migrated.pop("admin_password")
        logger.info("Migrated admin_password to admin_password_hash")
    
    # Migration 2: Ensure guild_configs exists
    if "guild_configs" not in migrated:
        migrated["guild_configs"] = {}
        logger.info("Added missing guild_configs")
    
    # Migration 3: Ensure revoked_guilds exists
    if "revoked_guilds" not in migrated:
        migrated["revoked_guilds"] = []
        logger.info("Added missing revoked_guilds")
    
    # Migration 4: Ensure pending_pairings exists
    if "pending_pairings" not in migrated:
        migrated["pending_pairings"] = {}
        logger.info("Added missing pending_pairings")
    
    # Migration 5: Ensure sync_commands exists
    if "sync_commands" not in migrated:
        migrated["sync_commands"] = False
        logger.info("Added missing sync_commands")
    
    # Migration 6: Ensure scheduled_messages exists
    if "scheduled_messages" not in migrated:
        migrated["scheduled_messages"] = []
        logger.info("Added missing scheduled_messages")
    
    # Migration 7: Ensure auto_responders exists
    if "auto_responders" not in migrated:
        migrated["auto_responders"] = []
        logger.info("Added missing auto_responders")
    
    # Migration 8: Ensure custom_commands exists
    if "custom_commands" not in migrated:
        migrated["custom_commands"] = {}
        logger.info("Added missing custom_commands")
    
    # Migration 9: Ensure command_permissions exists
    if "command_permissions" not in migrated:
        migrated["command_permissions"] = {}
        logger.info("Added missing command_permissions")
    
    # Migration 10: Ensure permission_roles exists
    if "permission_roles" not in migrated:
        migrated["permission_roles"] = {
            "admin_role_id": None,
            "moderator_role_id": None
        }
        logger.info("Added missing permission_roles")
    
    return migrated


def create_backup(config_file: Path) -> Optional[str]:
    """Create a backup of the configuration file."""
    try:
        backup_dir = config_file.parent / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        backup_file = backup_dir / f"config_backup_{timestamp}.json"
        
        shutil.copy2(config_file, backup_file)
        
        logger.info(f"Backup created: {backup_file}")
        return str(backup_file)
    except Exception as e:
        logger.error(f"Failed to create backup: {e}")
        return None


def verify_migration(config_path: str) -> Dict[str, Any]:
    """
    Verify that migration was successful.
    
    Returns:
        Dict with verification results
    """
    config_file = Path(config_path)
    
    if not config_file.exists():
        return {"valid": False, "error": "Config file not found"}
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Check required keys
        required_keys = [
            "guild_configs",
            "revoked_guilds",
            "pending_pairings",
            "sync_commands",
            "scheduled_messages",
            "auto_responders",
            "custom_commands",
            "command_permissions",
            "permission_roles"
        ]
        
        missing_keys = [key for key in required_keys if key not in config]
        
        if missing_keys:
            return {
                "valid": False,
                "error": f"Missing required keys: {missing_keys}",
                "config_keys": list(config.keys())
            }
        
        return {
            "valid": True,
            "config_keys": list(config.keys()),
            "guild_count": len(config.get("guild_configs", {}))
        }
        
    except Exception as e:
        return {"valid": False, "error": str(e)}


def get_migration_status(config_path: str) -> Dict[str, Any]:
    """Get the current migration status."""
    config_file = Path(config_path)
    
    if not config_file.exists():
        return {"status": "not_found", "message": "Config file not found"}
    
    try:
        with open(config_file, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        # Check if migration is needed
        migration_needed = False
        missing_keys = []
        
        required_keys = [
            "guild_configs",
            "revoked_guilds",
            "pending_pairings",
            "sync_commands",
            "scheduled_messages",
            "auto_responders",
            "custom_commands",
            "command_permissions",
            "permission_roles"
        ]
        
        for key in required_keys:
            if key not in config:
                migration_needed = True
                missing_keys.append(key)
        
        if migration_needed:
            return {
                "status": "needs_migration",
                "message": f"Missing keys: {missing_keys}",
                "missing_keys": missing_keys
            }
        else:
            return {
                "status": "up_to_date",
                "message": "Configuration is up to date"
            }
        
    except Exception as e:
        return {"status": "error", "message": str(e)}
