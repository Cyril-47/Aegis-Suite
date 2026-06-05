import sys
import os
from pathlib import Path
import logging

logger = logging.getLogger("aegis.core.single_instance")

class SingleInstanceGuard:
    """Named mutex single-instance guard for Windows, with lock-file fallback on other platforms."""
    def __init__(self, data_dir: Path, name: str = "AegisSuiteMutex"):
        self.data_dir = data_dir
        # Avoid mutex collision during tests by appending a unique test suffix
        if os.getenv("PYTEST_CURRENT_TEST"):
            name = f"{name}_test_{os.getpid()}"
        self.mutex_name = name
        self.lock_file_path = data_dir / "aegis.lock"
        self.url_file_path = data_dir / "aegis.url"
        self.is_primary = False
        self._mutex = None

    def acquire(self) -> bool:
        if sys.platform == "win32":
            try:
                import ctypes
                # Create a named mutex (owned by current process)
                self._mutex = ctypes.windll.kernel32.CreateMutexW(None, True, self.mutex_name)
                err = ctypes.windll.kernel32.GetLastError()
                if err == 183:  # ERROR_ALREADY_EXISTS
                    self.is_primary = False
                    ctypes.windll.kernel32.CloseHandle(self._mutex)
                    self._mutex = None
                else:
                    self.is_primary = True
            except Exception as e:
                logger.error(f"Win32 CreateMutex failed: {e}. Falling back to lock file.")
                self._acquire_file_lock()
        else:
            self._acquire_file_lock()

        return self.is_primary

    def _acquire_file_lock(self):
        try:
            if self.lock_file_path.exists():
                try:
                    with open(self.lock_file_path, "r") as f:
                        pid = int(f.read().strip())
                    if self._is_pid_running(pid):
                        self.is_primary = False
                        return
                except (ValueError, OSError):
                    pass

            with open(self.lock_file_path, "w") as f:
                f.write(str(os.getpid()))
            self.is_primary = True
        except Exception as e:
            logger.error(f"File-based lock acquisition failed: {e}")
            self.is_primary = False

    def _is_pid_running(self, pid: int) -> bool:
        if pid <= 0:
            return False
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if handle:
                exit_code = ctypes.c_ulong()
                ctypes.windll.kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
                ctypes.windll.kernel32.CloseHandle(handle)
                return exit_code.value == STILL_ACTIVE
            return False
        else:
            try:
                os.kill(pid, 0)
                return True
            except OSError:
                return False

    def write_dashboard_url(self, url: str) -> None:
        try:
            self.url_file_path.write_text(url, encoding="utf-8")
        except Exception as e:
            logger.error(f"Failed to write dashboard URL: {e}")

    def read_dashboard_url(self) -> str:
        try:
            if self.url_file_path.exists():
                return self.url_file_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            logger.error(f"Failed to read dashboard URL: {e}")
        return ""

    def release(self) -> None:
        if sys.platform == "win32" and self._mutex:
            try:
                import ctypes
                ctypes.windll.kernel32.ReleaseMutex(self._mutex)
                ctypes.windll.kernel32.CloseHandle(self._mutex)
            except Exception as e:
                logger.error(f"Error releasing Win32 mutex: {e}")
            finally:
                self._mutex = None
        
        if self.is_primary:
            try:
                self.lock_file_path.unlink(missing_ok=True)
                self.url_file_path.unlink(missing_ok=True)
            except Exception as e:
                logger.error(f"Error deleting lock files on release: {e}")
        self.is_primary = False
