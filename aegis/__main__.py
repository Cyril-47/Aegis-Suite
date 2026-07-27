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


def _check_critical_deps():
    """Logs the availability of critical optional dependencies at startup."""
    import importlib
    checks = [
        ("discord", "discord.py (bot framework)"),
        ("nacl", "PyNaCl (voice support)"),
        ("yt_dlp", "yt-dlp (music streaming)"),
        ("fastapi", "FastAPI (web dashboard)"),
        ("uvicorn", "Uvicorn (web server)"),
        ("sqlalchemy", "SQLAlchemy (database)"),
        ("alembic", "Alembic (migrations)"),
    ]
    import shutil
    ffmpeg_ok = shutil.which("ffmpeg") is not None

    for mod_name, label in checks:
        try:
            importlib.import_module(mod_name)
            logger.info(f"  [OK] {label}")
        except ImportError:
            logger.warning(f"  [MISSING] {label} — some features will be unavailable")

    if ffmpeg_ok:
        logger.info("  [OK] FFmpeg (media processing)")
    else:
        logger.warning("  [MISSING] FFmpeg — music playback and voice features will be unavailable")

def main() -> int:
    # 0. Load environment variables
    from aegis.core.utils import load_env_file
    load_env_file()

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

    # Onboarding Wizard - Bypass console/terminal wizard, boot straight into Web GUI Setup
    # import first_run_wizard
    # if not first_run_wizard.credentials_already_exist(paths.root):
    #     print("\n[+] Credentials not found. Starting first-run configuration wizard...")
    #     success = first_run_wizard.run_first_run_wizard(paths.root)
    #     if not success:
    #         print("[-] Configuration wizard aborted or failed. Exiting.")
    #         guard.release()
    #         return 1

    # 3. Setup logging (Redacts secrets automatically - C4)
    setup_logging(paths)
    logger.info("Initializing Aegis Suite...")
    logger.info("Checking dependencies:")
    _check_critical_deps()

    # 4. Build AppCore and run
    core = AppCore(paths)
    core.guard = guard # Keep reference for release on shutdown

    # 5. Define signal handlers for graceful shutdown (Req 25.2, Req 1.4)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

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
    use_gui = False
    import os
    if not os.environ.get("HEADLESS") and not os.environ.get("RENDER"):
        try:
            import webview
            use_gui = True
        except ImportError:
            use_gui = False

    if use_gui:
        import threading
        import time
        import webview

        logger.info("Starting Aegis Suite Desktop GUI Application...")
        bg_thread = threading.Thread(target=lambda: loop.run_until_complete(core.run()), daemon=True)
        bg_thread.start()

        # Wait for web_port to be assigned
        for _ in range(50):
            if core.web_port is not None:
                break
            time.sleep(0.1)

        if core.web_port is not None:
            dash_url = f"http://127.0.0.1:{core.web_port}"
            logger.info(f"Opening Standalone Desktop App Window at: {dash_url}")
            
            is_full_exit = False
            window_ref = None

            def on_restore():
                if window_ref:
                    try:
                        window_ref.show()
                        window_ref.restore()
                    except Exception as e:
                        logger.warning(f"Could not restore desktop window: {e}")

            def on_full_exit():
                nonlocal is_full_exit
                is_full_exit = True
                if window_ref:
                    try:
                        window_ref.destroy()
                    except Exception:
                        pass

            # Initialize System Tray Manager
            tray_mgr = None
            try:
                from aegis.core.tray import SystemTrayManager
                tray_mgr = SystemTrayManager(
                    root_dir=paths.root,
                    on_open_callback=on_restore,
                    on_exit_callback=on_full_exit
                )
                tray_mgr.run_detached()
            except Exception as tray_err:
                logger.warning(f"Could not initialize system tray icon: {tray_err}")

            def on_closing():
                if is_full_exit:
                    return True # Allow window destruction on full exit
                
                # Minimize to system tray and notify user
                if tray_mgr:
                    tray_mgr.notify_background_running()
                if window_ref:
                    window_ref.hide()
                return False # Cancel default close to keep background bot running

            try:
                window_ref = webview.create_window(
                    title="Aegis Suite",
                    url=dash_url,
                    width=1280,
                    height=850,
                    min_size=(960, 640),
                    resizable=True
                )
                window_ref.events.closing += on_closing

                def set_window_native_icon():
                    try:
                        base_dir = os.path.dirname(os.path.abspath(__file__))
                        ico_candidates = [
                            os.path.join(base_dir, "..", "logo.ico"),
                            os.path.join(base_dir, "logo.ico"),
                            os.path.join(os.getcwd(), "logo.ico")
                        ]
                        target_ico = next((p for p in ico_candidates if os.path.exists(p)), None)
                        if target_ico and hasattr(window_ref, "native") and window_ref.native:
                            import clr
                            clr.AddReference("System.Drawing")
                            from System.Drawing import Icon
                            window_ref.native.Icon = Icon(target_ico)
                            logger.info(f"Set PyWebView native window icon: {target_ico}")
                    except Exception as ex:
                        logger.debug(f"Could not set native window icon: {ex}")

                window_ref.events.shown += set_window_native_icon
                webview.start(gui='edgechromium', debug=False)
            except Exception as e:
                logger.warning(f"PyWebView launch error: {e}. Opening browser...")
                webbrowser.open(dash_url)
                bg_thread.join()
            finally:
                if tray_mgr:
                    tray_mgr.stop()
                asyncio.run_coroutine_threadsafe(core.request_shutdown(), loop)
        else:
            logger.error("Web server startup timed out.")
            asyncio.run_coroutine_threadsafe(core.request_shutdown(), loop)
        
        guard.release()
        logger.info("Aegis Suite stopped.")
        return 0
    else:
        try:
            # Run AppCore event loop directly on main thread
            exit_code = loop.run_until_complete(core.run())
        except KeyboardInterrupt:
            logger.info("KeyboardInterrupt caught, shutting down...")
            loop.run_until_complete(core.request_shutdown())
        except Exception:
            logger.exception("Unhandled exception in main loop")
            exit_code = 1
        finally:
            guard.release()
            logger.info("Aegis Suite stopped.")
            
        return exit_code

if __name__ == "__main__":
    sys.exit(main())
