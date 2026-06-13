import asyncio
import socket
import logging
import uvicorn
from typing import Optional

logger = logging.getLogger("aegis.web.server")

def resolve_port(start_port: int = 8000, end_port: int = 8010) -> Optional[int]:
    """Tries to bind to ports in the range start_port to end_port.
    Returns the first free port, or None if all are occupied.
    """
    for port in range(start_port, end_port + 1):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            logger.debug(f"Port {port} is occupied, trying next.")
            continue
    return None

async def serve(core, app) -> None:
    """Coroutine that acts as the ASGI_Server_Task body. Runs Uvicorn programmatically."""
    port = resolve_port(8000, 8010)
    if port is None:
        logger.error("FATAL-to-app: Web server failed to bind. Ports 8000-8010 are occupied.")
        core.health.record_check("web", "FATAL-to-app")
        # Initiate graceful shutdown through AppCore
        await core.request_shutdown()
        return

    # Store selected port and update health web status
    core.web_port = port
    core.health.web = "up"
    core.health.record_check("web", "OK")
    
    # Persist the running instance's dashboard URL to single-instance guard (Req 1.5, Fix C6)
    if hasattr(core, "guard") and core.guard:
        core.guard.write_dashboard_url(f"http://127.0.0.1:{port}")

    # Configure uvicorn to use standard asyncio loop
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_config=None,
        loop="asyncio"
    )
    server = uvicorn.Server(config)
    core._uvicorn_server = server

    try:
        await server.serve()
    except asyncio.CancelledError:
        logger.info("ASGI server task cancelled.")
        raise
    except Exception as exc:
        logger.exception("Uvicorn server encountered an exception")
        core.health.record_fatal(exc)
        core.health.web = "down"
        await core.request_shutdown()
    finally:
        core.health.web = "down"
