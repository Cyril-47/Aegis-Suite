import socket
import pytest
import asyncio
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from aegis.core.app_core import AppCore
from aegis.core.state import LifecycleState, ReasonCode
from aegis.web.server import resolve_port
from aegis.web.app import build_app

def test_port_resolution_all_cases():
    """Verify resolve_port binds to first free port, skips occupied, and returns None if all occupied."""
    # 1. First free port (8000)
    port = resolve_port(8000, 8010)
    assert port is not None
    
    # 2. Occupy the port, verify next port is selected
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", port))
    s.listen(1)
    
    port2 = resolve_port(port, port + 1)
    assert port2 == port + 1
    
    # 3. Occupy the next port too, verify None is returned
    s2 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s2.bind(("127.0.0.1", port + 1))
    s2.listen(1)
    
    port3 = resolve_port(port, port + 1)
    assert port3 is None
    
    s.close()
    s2.close()

def test_fastapi_assembly(tmp_path, monkeypatch):
    """Verify FastAPI build_app attaches core state, mounts static folder, and creates it if missing."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    core = AppCore()
    app = build_app(core)
    assert app.state.core == core
    
    # Check static directory exists
    from aegis.core.utils import get_resource_path
    from pathlib import Path
    static_path = Path(get_resource_path("static"))
    assert static_path.exists()
    assert static_path.is_dir()
    
    # Verify static route mount
    static_mount = None
    for route in app.routes:
        if route.path == "/static":
            static_mount = route
            break
    assert static_mount is not None

def test_health_api(tmp_path, monkeypatch):
    """Verify /health and /api/health return cached health registry payload."""
    monkeypatch.setenv("APPDATA", str(tmp_path))
    core = AppCore()
    core.health.web = "up"
    core.health.database = {"reachable": True, "integrity_ok": True, "at_head": True}
    
    app = build_app(core)
    client = TestClient(app)
    
    # GET /health
    r1 = client.get("/health")
    assert r1.status_code == 200
    payload1 = r1.json()
    assert payload1["web"] == "up"
    assert payload1["database"]["reachable"] is True
    
    # GET /api/health
    r2 = client.get("/api/health")
    assert r2.status_code == 200
    payload2 = r2.json()
    assert payload2["web"] == "up"
    assert payload2["database"]["reachable"] is True

@pytest.mark.asyncio
async def test_lifecycle_behavior(paths_tmp, temp_appdata):
    """Verify server runs in RUNNING/SAFE_MODE, and bot only in RUNNING; bot cancelled on transition to SAFE_MODE."""
    core = AppCore(paths=paths_tmp)
    
    # 1. Transitions to SAFE_MODE (ASGI server task must start, bot task must not exist)
    await core.enter_safe_mode(ReasonCode.NEEDS_SETUP)
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core._asgi_task is not None
    assert not core._asgi_task.done()
    assert core._bot_task is None
    
    # 2. Transition to RUNNING (ASGI server task keeps running, bot placeholder task starts)
    await core.promote_to_running()
    assert core.state.current_state == LifecycleState.RUNNING
    assert core._asgi_task is not None
    assert not core._asgi_task.done()
    assert core._bot_task is not None
    assert not core._bot_task.done()
    assert core.health.bot == "connected_ready"
    
    # 3. Transition back to SAFE_MODE (Bot task must be cleanly cancelled and disabled)
    await core.enter_safe_mode(ReasonCode.TOKEN_RECOVERY)
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core._bot_task is None
    assert core.health.bot == "disabled"

@pytest.mark.asyncio
async def test_shutdown_centralized(paths_tmp, temp_appdata):
    """Verify AppCore request_shutdown cleanly cancels and stops bot and web server tasks."""
    core = AppCore(paths=paths_tmp)
    await core.promote_to_running()
    assert core._asgi_task is not None
    assert core._bot_task is not None
    
    await core.request_shutdown()
    assert core.state.current_state == LifecycleState.SHUTTING_DOWN
    assert core._asgi_task is None or core._asgi_task.done()
    assert core._bot_task is None or core._bot_task.done()

@pytest.mark.asyncio
async def test_port_conflict_fatal(paths_tmp, temp_appdata):
    """Verify that when all ports 8000-8010 are occupied, a fatal verdict is recorded and shutdown is triggered."""
    sockets = []
    for port in range(8000, 8011):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.bind(("127.0.0.1", port))
            s.listen(1)
            sockets.append(s)
        except OSError:
            # Port is already occupied/reserved by the OS/Hyper-V, which counts as occupied
            pass
        
    core = AppCore(paths=paths_tmp)
    await core.enter_safe_mode(ReasonCode.NEEDS_SETUP)
    
    # Allow the task a tiny slice to resolve port and trigger conflict code path
    await asyncio.sleep(0.1)
    
    # Check that fatal verdict was recorded and app transition to shutdown was requested
    assert core.health.checks.get("web") == "FATAL-to-app"
    assert core.state.current_state == LifecycleState.SHUTTING_DOWN
    
    # Cleanup dummy listener sockets
    for s in sockets:
        s.close()

@pytest.mark.asyncio
async def test_bot_crash_safe_mode_transition(paths_tmp, temp_appdata):
    """Verify that an unexpected bot task termination triggers safe mode recovery transition."""
    core = AppCore(paths=paths_tmp)
    await core.promote_to_running()
    assert core.state.current_state == LifecycleState.RUNNING
    assert core._bot_task is not None
    
    # Simulate bot crash by cancelling or replacing the task with a crashed coroutine
    async def crashed_bot():
        await asyncio.sleep(0.01)
        raise RuntimeError("Discord websocket disconnected abnormally")
        
    core._bot_task.remove_done_callback(core._on_bot_task_done)
    core._bot_task.cancel()
    try:
        await core._bot_task
    except asyncio.CancelledError:
        pass
        
    core._bot_task = asyncio.create_task(crashed_bot())
    core._bot_task.add_done_callback(core._on_bot_task_done)
    
    # Wait for crashed bot to complete and trigger callback
    await asyncio.sleep(0.05)
    
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core.state.reason == ReasonCode.TOKEN_RECOVERY
    assert "fatal_error" in core.health.checks
    assert core.health.checks["fatal_error"]["type"] == "RuntimeError"

@pytest.mark.asyncio
async def test_uvicorn_startup_failure(paths_tmp, temp_appdata):
    """Verify that a programmatic uvicorn server startup failure initiates graceful shutdown."""
    core = AppCore(paths=paths_tmp)
    
    # Mock serve to raise an error
    from aegis.web.app import build_app
    app = build_app(core)
    
    # Setup mock uvicorn server that crashes
    mock_server = MagicMock()
    async def crash_serve():
        raise RuntimeError("Address family not supported by protocol")
    mock_server.serve = crash_serve
    
    # Trigger serve which will use mock server
    import uvicorn
    orig_Server = uvicorn.Server
    
    def mock_server_init(*args, **kwargs):
        return mock_server
    uvicorn.Server = mock_server_init
    
    try:
        await core.enter_safe_mode(ReasonCode.NEEDS_SETUP)
        await asyncio.sleep(0.05)
        
        assert core.state.current_state == LifecycleState.SHUTTING_DOWN
        assert "fatal_error" in core.health.checks
        assert core.health.checks["fatal_error"]["type"] == "RuntimeError"
    finally:
        uvicorn.Server = orig_Server

@pytest.mark.asyncio
async def test_repeated_state_transitions(paths_tmp, temp_appdata):
    """Verify that transitioning between RUNNING and SAFE_MODE multiple times updates tasks correctly."""
    core = AppCore(paths=paths_tmp)
    
    # 1. BOOTING -> SAFE_MODE
    await core.enter_safe_mode(ReasonCode.NEEDS_SETUP)
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert core._asgi_task is not None
    assert core._bot_task is None
    
    # 2. SAFE_MODE -> RUNNING
    await core.promote_to_running()
    assert core.state.current_state == LifecycleState.RUNNING
    assert not core._asgi_task.done()
    assert core._bot_task is not None
    assert not core._bot_task.done()
    
    # 3. RUNNING -> SAFE_MODE
    await core.enter_safe_mode(ReasonCode.TOKEN_RECOVERY)
    assert core.state.current_state == LifecycleState.SAFE_MODE
    assert not core._asgi_task.done()
    assert core._bot_task is None

@pytest.mark.asyncio
async def test_multiple_sequential_shutdown_requests(paths_tmp, temp_appdata, monkeypatch):
    """Verify first shutdown is graceful and subsequent request triggers hard exit (os._exit)."""
    core = AppCore(paths=paths_tmp)
    await core.promote_to_running()
    
    exited = False
    def mock_exit(code):
        nonlocal exited
        exited = True
        
    monkeypatch.setattr("os._exit", mock_exit)
    
    await core.request_shutdown()
    assert core.state.current_state == LifecycleState.SHUTTING_DOWN
    
    # Second shutdown request
    await core.request_shutdown()
    assert exited
