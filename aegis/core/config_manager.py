"""
Unified Configuration Manager for Aegis Suite.

Single source of truth for all configuration.
Handles loading, saving, validation, and caching.
"""

import json
import os
import logging
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional
from dataclasses import dataclass, field

logger = logging.getLogger("aegis.config.manager")


@dataclass
class ConfigCache:
    """In-memory config cache with TTL."""
    data: Dict[str, Any] = field(default_factory=dict)
    last_loaded: float = 0
    ttl_seconds: int = 30  # Cache for 30 seconds


class ConfigManager:
    """
    Unified configuration manager.
    
    Single source of truth for all configuration.
    Handles loading, saving, validation, and caching.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        """Singleton pattern."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._cache = ConfigCache()
        self._lock = threading.Lock()
        try:
            from aegis.core.paths import Paths
            self._config_path = str(Paths().config_file)
        except Exception:
            self._config_path = None
        self._defaults = self._load_defaults()
        
        logger.info(f"ConfigManager initialized with config path: {self._config_path}")
    
    def _load_defaults(self) -> Dict[str, Any]:
        """Load default configuration values."""
        return {
            "client_id": "",
            "setup_complete": False,
            "ui_mode": "beginner",
            "welcome_settings": {
                "enabled": False,
                "channel_id": None,
                "channel_name": "welcome",
                "message_title": "Welcome!",
                "message_description": "Welcome to the server!",
                "embed_color": "#10b981",
                "auto_assign_roles": []
            },
            "automod_settings": {
                "enabled": False,
                "block_profanity": False,
                "block_links": False,
                "max_mentions": 5,
                "log_channel_id": None,
                "log_channel_name": "mod-log",
                "profanity_words": [],
                "block_invites": False,
                "whitelisted_domains": [],
                "whitelisted_invites": []
            },
            "anti_raid_settings": {
                "enabled": False,
                "response_mode": "alert",
                "join_rate_threshold": 10,
                "join_rate_window_seconds": 300,
                "min_account_age_days": 7,
                "suspicious_score_threshold": 70,
                "auto_verify_channel": None,
                "raid_alert_channel": None,
                "dm_owner_on_raid": True,
                "lockdown_duration_seconds": 300
            },
            "ticket_settings": {
                "enabled": False,
                "category_name": "tickets",
                "staff_role_name": "Staff",
                "ticket_channel_id": None,
                "panel_message_id": None,
                "sla_hours": 24
            },
            "custom_commands": {},
            "admin_password_hash": "",
            "hosting_mode": "",
            "command_permissions": {},
            "permission_roles": {
                "admin_role_id": None,
                "moderator_role_id": None
            },
            "leveling_settings": {
                "enabled": False,
                "xp_per_message": 15,
                "xp_cooldown_seconds": 60,
                "level_up_channel": None,
                "level_roles": {},
                "ignored_channels": [],
                "ignored_roles": []
            },
            "scheduled_messages": [],
            "auto_responders": [],
            "slowmode_settings": {
                "enabled": False,
                "burst_window_seconds": 10,
                "min_trigger_rate": 3.0,
                "slowmode_duration": 3,
                "max_slowmode_duration": 10,
                "cooldown_seconds": 30,
                "whitelisted_channels": []
            },
            "backup_settings": {
                "enabled": True,
                "schedule_hour": 3,
                "schedule_minute": 0,
                "retention_days": 7,
                "use_safe_backup": True,
            },
            "maintenance_settings": {
                "role_cleanup_enabled": True,
                "role_cleanup_hour": 4,
                "channel_archive_enabled": False,
                "inactive_days": 30,
                "db_vacuum_enabled": True,
                "db_vacuum_hour": 5,
            },
            "guild_configs": {},
            "revoked_guilds": [],
            "pending_pairings": {},
            "sync_commands": False
        }
    
    def set_config_path(self, path: str):
        """Set the configuration file path."""
        self._config_path = path
        self._invalidate_cache()
    
    def _invalidate_cache(self):
        """Invalidate the config cache."""
        with self._lock:
            self._cache.last_loaded = 0
    
    def load(self, force_reload: bool = False) -> Dict[str, Any]:
        """
        Load configuration with caching.
        
        Returns cached config if available and not expired.
        Otherwise loads from disk and caches the result.
        """
        with self._lock:
            # Check cache
            if not force_reload and self._cache.data:
                if time.time() - self._cache.last_loaded < self._cache.ttl_seconds:
                    return self._cache.data.copy()
            
            # Load from disk
            config = self._load_from_disk()
            
            # Apply environment variable overrides
            config = self._apply_env_overrides(config)
            
            # Apply defaults for missing keys
            config = self._apply_defaults(config)
            
            # Cache the result
            self._cache.data = config
            self._cache.last_loaded = time.time()
            
            return config.copy()
    
    def _load_from_disk(self) -> Dict[str, Any]:
        """Load configuration from disk."""
        if not self._config_path:
            logger.warning("No config path set, using defaults")
            return self._defaults.copy()
        
        config_file = Path(self._config_path)
        if not config_file.exists():
            logger.warning(f"Config file not found: {config_file}")
            return self._defaults.copy()
        
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            # Decrypt sensitive keys if needed
            config = self._decrypt_sensitive_keys(config)
            
            return config
        except Exception as e:
            logger.error(f"Error loading config from {config_file}: {e}")
            return self._defaults.copy()
    
    def _decrypt_sensitive_keys(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Decrypt sensitive configuration keys."""
        try:
            from aegis.core.encryption import DPAPIEncryption
            for key in ["discord_token", "bot_token"]:
                if key in config and isinstance(config[key], str) and config[key].startswith(DPAPIEncryption._PREFIX):
                    try:
                        config[key] = DPAPIEncryption.decrypt(config[key])
                    except Exception as e:
                        logger.error(f"Failed to decrypt config key {key}: {e}")
        except ImportError:
            pass
        return config
    
    def _apply_env_overrides(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides."""
        # Environment variables take precedence over config file
        env_mappings = {
            "ADMIN_PASSWORD_HASH": ("admin_password_hash", str),
            "HOSTING_MODE": ("hosting_mode", str),
            "JWT_SECRET": ("jwt_secret", str),
        }
        
        for env_var, (config_key, config_type) in env_mappings.items():
            env_value = os.environ.get(env_var)
            if env_value:
                config[config_key] = config_type(env_value)
        
        return config
    
    def _apply_defaults(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Apply default values for missing configuration keys."""
        for key, default_value in self._defaults.items():
            if key not in config or config[key] is None:
                config[key] = default_value
            elif isinstance(default_value, dict):
                if not isinstance(config[key], dict):
                    config[key] = default_value
                else:
                    for sub_key, sub_value in default_value.items():
                        if sub_key not in config[key] or config[key][sub_key] is None:
                            config[key][sub_key] = sub_value
        
        return config
    
    def save(self, config: Dict[str, Any]) -> bool:
        """
        Save configuration to disk.
        
        Returns True on success, False on failure.
        """
        with self._lock:
            try:
                # Encrypt sensitive keys before saving
                config = self._encrypt_sensitive_keys(config)
                
                # Save to disk
                if self._config_path:
                    config_file = Path(self._config_path)
                    config_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    with open(config_file, "w", encoding="utf-8") as f:
                        json.dump(config, f, indent=2)
                
                # Update cache
                self._cache.data = config.copy()
                self._cache.last_loaded = time.time()
                
                logger.info("Configuration saved successfully")
                return True
            except Exception as e:
                logger.error(f"Error saving configuration: {e}")
                return False
    
    def _encrypt_sensitive_keys(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Encrypt sensitive configuration keys."""
        try:
            from aegis.core.encryption import DPAPIEncryption
            for key in ["discord_token", "bot_token"]:
                if key in config and isinstance(config[key], str) and config[key]:
                    try:
                        config[key] = DPAPIEncryption.encrypt(config[key])
                    except Exception as e:
                        logger.error(f"Failed to encrypt config key {key}: {e}")
        except ImportError:
            pass
        return config
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a configuration value by key path."""
        config = self.load()
        
        # Support dot notation for nested keys
        keys = key.split(".")
        value = config
        
        for k in keys:
            if isinstance(value, dict) and k in value:
                value = value[k]
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any) -> bool:
        """Set a configuration value by key path."""
        config = self.load()
        
        # Support dot notation for nested keys
        keys = key.split(".")
        target = config
        
        for k in keys[:-1]:
            if k not in target:
                target[k] = {}
            target = target[k]
        
        target[keys[-1]] = value
        
        return self.save(config)
    
    def get_guild_config(self, guild_id: str) -> Dict[str, Any]:
        """Get configuration for a specific guild."""
        config = self.load()
        return config.get("guild_configs", {}).get(str(guild_id), {})
    
    def set_guild_config(self, guild_id: str, guild_config: Dict[str, Any]) -> bool:
        """Set configuration for a specific guild."""
        config = self.load()
        
        if "guild_configs" not in config:
            config["guild_configs"] = {}
        
        config["guild_configs"][str(guild_id)] = guild_config
        
        return self.save(config)
    
    def validate(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration against schema."""
        try:
            from aegis.config.schema import validate_config
            validate_config(config)
            return {"valid": True, "errors": []}
        except Exception as e:
            return {"valid": False, "errors": [str(e)]}
    
    def get_all(self) -> Dict[str, Any]:
        """Get the entire configuration."""
        return self.load()
    
    def reset(self) -> bool:
        """Reset configuration to defaults."""
        return self.save(self._defaults.copy())
    
    def backup(self) -> Optional[str]:
        """Create a backup of the current configuration."""
        if not self._config_path:
            return None
        
        try:
            config_file = Path(self._config_path)
            backup_dir = config_file.parent / "backups"
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = time.strftime("%Y%m%d_%H%M%S")
            backup_file = backup_dir / f"config_backup_{timestamp}.json"
            
            with open(config_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            with open(backup_file, "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2)
            
            logger.info(f"Configuration backup created: {backup_file}")
            return str(backup_file)
        except Exception as e:
            logger.error(f"Failed to create backup: {e}")
            return None
    
    def restore(self, backup_path: str) -> bool:
        """Restore configuration from a backup."""
        try:
            backup_file = Path(backup_path)
            if not backup_file.exists():
                logger.error(f"Backup file not found: {backup_file}")
                return False
            
            with open(backup_file, "r", encoding="utf-8") as f:
                config = json.load(f)
            
            return self.save(config)
        except Exception as e:
            logger.error(f"Failed to restore from backup: {e}")
            return False


# Convenience functions for backward compatibility
def get_config_manager() -> ConfigManager:
    """Get the singleton ConfigManager instance."""
    return ConfigManager()


def load_config() -> Dict[str, Any]:
    """Load configuration (backward compatible)."""
    return get_config_manager().load()


def save_config(config: Dict[str, Any]) -> bool:
    """Save configuration (backward compatible)."""
    return get_config_manager().save(config)


def get_guild_config(guild_id: str) -> Dict[str, Any]:
    """Get guild configuration (backward compatible)."""
    return get_config_manager().get_guild_config(guild_id)


def set_guild_config(guild_id: str, guild_config: Dict[str, Any]) -> bool:
    """Set guild configuration (backward compatible)."""
    return get_config_manager().set_guild_config(guild_id, guild_config)
