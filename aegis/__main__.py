import sys
import asyncio
import logging
import signal
import webbrowser
from aegis.core.paths import Paths
from aegis.core.single_instance import SingleInstanceGuard
from aegis.core.logging_setup import setup_logging
from aegis.core.app_core import AppCore

logger = logging.getLogger("aegis.main")

def main() -> int:
    # 1. Resolve paths
    paths = Paths()
    paths.ensure()

    # 2. Acquire single-instance mutex (Fix C6)
    guard = SingleInstanceGuard(paths.root)
    if not guard.acquire():
        print("[!] Another instance of Aegis Suite is already running.")
        url = guard.read_dashboard_url()
        if url:
            print(f"Opening dashboard in browser: {url}")
            webbrowser.open(url)
        else:
            print("Dashboard URL not found for running instance.")
        return 0

    # Onboarding Wizard - Launch if credentials are missing (Phase 4 requirement)
    import first_run_wizard
    if not first_run_wizard.credentials_already_exist(paths.root):
        print("\n[+] Credentials not found. Starting first-run configuration wizard...")
        success = first_run_wizard.run_first_run_wizard(paths.root)
        if not success:
            print("[-] Configuration wizard aborted or failed. Exiting.")
            guard.release()
            return 1

    # 3. Setup logging (Redacts secrets automatically - C4)
    setup_logging(paths)
    logger.info("Initializing Aegis Suite...")

    # 4. Build AppCore and run
    core = AppCore(paths)
    core.guard = guard # Keep reference for release on shutdown

    # 5. Define signal handlers for graceful shutdown (Req 25.2, Req 1.4)
    loop = asyncio.get_event_loop()

    async def shutdown_handler(sig_name):
        logger.info(f"Received signal {sig_name}, initiating graceful shutdown...")
        await core.request_shutdown()

    # Hook signal handlers
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown_handler(s.name)))
        except (NotImplementedError, RuntimeError):
            # add_signal_handler is not implemented in Windows asyncio ProactorEventLoop
            pass

    # Windows Console Control Handler fallback
    if sys.platform == "win32":
        try:
            import win32api
            def win32_ctrl_handler(dwCtrlType):
                logger.info(f"Received Win32 console control event: {dwCtrlType}")
                asyncio.run_coroutine_threadsafe(core.request_shutdown(), loop)
                return True
            win32api.SetConsoleCtrlHandler(win32_ctrl_handler, True)
        except Exception as e:
            logger.warning(f"Could not install Windows console control handler: {e}")

    exit_code = 0
    try:
        # Run AppCore event loop
        exit_code = loop.run_until_complete(core.run())
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt caught, shutting down...")
        loop.run_until_complete(core.request_shutdown())
    except Exception:
        logger.exception("Unhandled exception in main loop")
        exit_code = 1
    finally:
        # 6. Release mutex guard
        guard.release()
        logger.info("Aegis Suite stopped.")
        
    return exit_code

if __name__ == "__main__":
    sys.exit(main())
