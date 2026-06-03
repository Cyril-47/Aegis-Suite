import json
import logging
import os
import shutil
import tempfile
import datetime
from pathlib import Path
from typing import Any, Dict
from aegis.core.paths import Paths
from aegis.config.schema import validate_config, ConfigModel

logger = logging.getLogger("aegis.config.loader")

class ConfigInvalidError(Exception):
    """Raised when config schema validation fails."""
    pass

class ConfigStore:
    """Manages loading, validation, and safe atomic saving of the application configuration."""
    
    def __init__(self, paths: Paths, model: ConfigModel) -> None:
        self.paths = paths
        self._model = model

    @classmethod
    def load(cls, paths: Paths) -> "ConfigStore":
        """Loads configuration from Paths.config_file and validates it."""
        config_file = paths.config_file
        if not config_file.exists():
            raise FileNotFoundError(f"Configuration file not found: {config_file}")
            
        try:
            with open(config_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ConfigInvalidError(f"Failed to load config JSON: {e}") from e
            
        # Decrypt sensitive keys if DPAPI encrypted
        from aegis.core.encryption import DPAPIEncryption
        for key in ["discord_token", "bot_token"]:
            if key in data and isinstance(data[key], str) and data[key].startswith(DPAPIEncryption._PREFIX):
                try:
                    data[key] = DPAPIEncryption.decrypt(data[key])
                except Exception as e:
                    logger.error(f"Failed to decrypt config key {key}: {e}")

        try:
            model = validate_config(data)
            return cls(paths, model)
        except Exception as e:
            raise ConfigInvalidError(f"Config schema validation failed: {e}") from e

    def is_setup_complete(self) -> bool:
        return self._model.setup_complete

    @property
    def ui_mode(self) -> str:
        return self._model.ui_mode

    @property
    def client_id(self) -> str:
        return self._model.client_id

    def as_dict(self) -> Dict[str, Any]:
        """Returns the configuration data as a dictionary."""
        return self._model.model_dump()

    def save(self) -> None:
        """Atomic write configuration file and drop a backups/config snapshot."""
        import utils
        
        config_file = self.paths.config_file
        # Ensure directories exist
        config_file.parent.mkdir(parents=True, exist_ok=True)
        self.paths.backups_config.mkdir(parents=True, exist_ok=True)
        
        with utils.config_lock:
            # 1. Read existing config from disk
            on_disk_data = {}
            if config_file.exists():
                try:
                    with open(config_file, "r", encoding="utf-8") as f:
                        on_disk_data = json.load(f)
                        if not isinstance(on_disk_data, dict):
                            on_disk_data = {}
                except Exception as e:
                    logger.warning(f"Could not parse existing config JSON: {e}. Starting from empty.")
                    on_disk_data = {}
            
            # 2. Merge model fields over the on-disk data using a shallow top-level overlay.
            # Preserve unmodeled top-level keys from the on-disk config.
            # Modeled top-level keys are authoritative and replace their on-disk counterparts completely.
            model_data = self.as_dict()
            merged_data = on_disk_data.copy()
            merged_data.update(model_data)

            # Encrypt sensitive keys on write via DPAPI if available
            from aegis.core.encryption import DPAPIEncryption
            for key in ["discord_token", "bot_token"]:
                if key in merged_data and isinstance(merged_data[key], str) and merged_data[key]:
                    if not merged_data[key].startswith(DPAPIEncryption._PREFIX):
                        try:
                            merged_data[key] = DPAPIEncryption.encrypt(merged_data[key])
                        except Exception as e:
                            logger.error(f"Failed to encrypt config key {key}: {e}")

            # Write to a temp file first in the same directory to allow atomic rename
            fd, temp_path_str = tempfile.mkstemp(dir=str(config_file.parent), prefix="config_", suffix=".tmp")
            temp_path = Path(temp_path_str)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    json.dump(merged_data, f, indent=4)
                    
                # Perform atomic replacement
                os.replace(temp_path, config_file)
            except Exception as e:
                temp_path.unlink(missing_ok=True)
                logger.error(f"Failed to save configuration file: {e}")
                raise e
                
            # Copy to backups/config/ with timestamp
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"config_{ts}.json"
            backup_path = self.paths.backups_config / backup_filename
            try:
                shutil.copy2(config_file, backup_path)
                self._rotate_config_backups()
            except Exception as e:
                logger.error(f"Failed to create config backup snapshot: {e}")

    def _rotate_config_backups(self, keep: int = 10) -> None:
        if not self.paths.backups_config.exists():
            return
        backups = list(self.paths.backups_config.glob("config_*.json"))
        backups.sort(key=lambda p: p.name)
        if len(backups) > keep:
            to_delete = backups[:-keep]
            for p in to_delete:
                p.unlink(missing_ok=True)
