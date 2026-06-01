import os
from pathlib import Path

class UnwritableDataDirError(Exception):
    """Raised when the resolved data directory is not writable."""
    def __init__(self, message: str, path: Path) -> None:
        super().__init__(message)
        self.path = path


class Paths:
    """Single source of truth for Aegis Suite file and directory paths."""
    
    def __init__(self, root: Path | None = None) -> None:
        if root is not None:
            self.root = Path(root)
        else:
            appdata = os.environ.get("APPDATA")
            if appdata:
                self.root = Path(appdata) / "Aegis"
            else:
                self.root = Path.home() / "Aegis"
        
        # Subpaths resolution
        self.db_file = self.root / "aegis.db"
        self.config_file = self.root / "config" / "config.json"
        self.backups_db = self.root / "backups" / "db"
        self.backups_config = self.root / "backups" / "config"
        self.templates_builtin = self.root / "templates" / "builtin"
        self.templates_user = self.root / "templates" / "user"
        self.diagnostics = self.root / "diagnostics"
        self.log_file = self.root / "logs" / "aegis.log"
        self.err_log_file = self.root / "logs" / "aegis.err.log"

    def ensure(self) -> None:
        """Create missing directories under root and verify that root is writable."""
        # 1. Create root directory first
        self.root.mkdir(parents=True, exist_ok=True)
        
        # 2. Perform write probe on the root directory
        probe_file = self.root / ".write_probe"
        try:
            # We attempt to write to a temp file and remove it to verify permissions
            with open(probe_file, "w", encoding="utf-8") as f:
                f.write("probe")
            probe_file.unlink(missing_ok=True)
        except OSError as e:
            raise UnwritableDataDirError(
                f"Data directory is unwritable: {self.root}. Error: {e}",
                self.root
            ) from e

        # 3. Create all required subdirectories
        subdirs = [
            self.root / "config",
            self.backups_db,
            self.backups_config,
            self.templates_builtin,
            self.templates_user,
            self.diagnostics,
            self.root / "logs"
        ]
        
        for sdir in subdirs:
            sdir.mkdir(parents=True, exist_ok=True)

        # 4. Migrate legacy config file automatically if needed
        legacy_config = self.root / "config.json"
        if legacy_config.exists() and not self.config_file.exists():
            try:
                import shutil
                shutil.copy2(legacy_config, self.config_file)
            except Exception:
                pass

