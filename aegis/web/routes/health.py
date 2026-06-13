import os
import time
from fastapi import APIRouter, Request

router = APIRouter()

@router.get("/health")
@router.get("/api/health")
def get_health(request: Request):
    """Returns the cached health registry payload without triggering any live probes."""
    core = request.app.state.core
    return core.health.payload()

@router.get("/api/public/status")
def get_public_status(request: Request):
    """Public status endpoint — no auth required. For external monitoring."""
    core = request.app.state.core
    uptime = int(time.time() - core._start_time) if hasattr(core, "_start_time") else 0
    bot_status = "connected" if core.health.bot == "connected_ready" else "disconnected"
    return {
        "status": "online",
        "uptime_seconds": uptime,
        "bot_status": bot_status,
        "lifecycle_state": core.health.lifecycle_state,
    }

@router.get("/api/health/detailed")
def get_detailed_health(request: Request):
    """Detailed health metrics for the dashboard health card."""
    core = request.app.state.core
    uptime = int(time.time() - core._start_time) if hasattr(core, "_start_time") else 0

    bot_latency_ms = 0
    try:
        bot = core.bot if hasattr(core, "bot") and core.bot else None
        if not bot:
            from aegis.bot.bot_manager import get_bot
            bot = get_bot()
        if bot and bot.is_ready():
            bot_latency_ms = round(bot.latency * 1000, 1)
    except Exception:
        pass

    memory_mb = 0
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_mb = round(process.memory_info().rss / (1024 * 1024), 1)
    except Exception:
        # Fallback 1: Windows ctypes
        try:
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            PROCESS_QUERY_INFORMATION = 0x0400
            PROCESS_VM_READ = 0x0010

            GetProcessMemoryInfo = ctypes.windll.psapi.GetProcessMemoryInfo
            OpenProcess = ctypes.windll.kernel32.OpenProcess
            CloseHandle = ctypes.windll.kernel32.CloseHandle

            pid = os.getpid()
            handle = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid)
            if handle:
                try:
                    counters = PROCESS_MEMORY_COUNTERS()
                    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
                    if GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                        memory_mb = round(counters.WorkingSetSize / (1024 * 1024), 1)
                finally:
                    CloseHandle(handle)
        except Exception:
            # Fallback 2: POSIX resource
            try:
                import resource
                memory_mb = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
            except Exception:
                pass

    db_size_mb = 0
    try:
        db_file = core.paths.db_file if hasattr(core, "paths") and core.paths else None
        if not db_file:
            from aegis.core.paths import Paths
            db_file = Paths().db_file
        if db_file and db_file.exists():
            db_size_mb = round(db_file.stat().st_size / (1024 * 1024), 2)
    except Exception:
        pass

    return {
        "bot_latency_ms": bot_latency_ms,
        "memory_mb": memory_mb,
        "db_size_mb": db_size_mb,
        "uptime_seconds": uptime,
        "bot_status": core.health.bot,
        "lifecycle_state": core.health.lifecycle_state,
    }
