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
    # Run dependency checks asynchronously in a background thread so app boots instantly
    import threading
    threading.Thread(target=_check_critical_deps, daemon=True, name="DepsCheckThread").start()

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
        import time
        import webview

        logger.info("Starting Aegis Suite Desktop GUI Application...")

        SPLASH_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Aegis Suite</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      background: #0b0f19;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
      height: 100vh;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      user-select: none;
      overflow: hidden;
    }
    .splash-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
      animation: fadeIn 0.4s ease-out;
    }
    .logo-wrapper {
      position: relative;
      width: 88px;
      height: 88px;
      margin-bottom: 24px;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .logo-glow {
      position: absolute;
      width: 100%;
      height: 100%;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(99, 102, 241, 0.45) 0%, rgba(99, 102, 241, 0) 70%);
      animation: pulseGlow 2.5s infinite ease-in-out;
    }
    .shield-svg {
      position: relative;
      width: 64px;
      height: 64px;
      fill: none;
      filter: drop-shadow(0 0 16px rgba(99, 102, 241, 0.6));
    }
    .brand-title {
      font-size: 1.65rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      margin-bottom: 6px;
      background: linear-gradient(135deg, #ffffff 40%, #a5b4fc 100%);
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
    }
    .brand-subtitle {
      font-size: 0.85rem;
      color: #94a3b8;
      font-weight: 500;
      letter-spacing: 0.05em;
      text-transform: uppercase;
      margin-bottom: 28px;
    }
    .status-bar-container {
      width: 220px;
      height: 4px;
      background: rgba(255, 255, 255, 0.08);
      border-radius: 999px;
      overflow: hidden;
      position: relative;
      margin-bottom: 12px;
    }
    .status-bar-fill {
      position: absolute;
      top: 0;
      left: 0;
      height: 100%;
      width: 40%;
      background: linear-gradient(90deg, #6366f1, #818cf8, #a5b4fc);
      border-radius: 999px;
      animation: shimmerBar 1.6s infinite ease-in-out;
    }
    .status-text {
      font-size: 0.78rem;
      color: #64748b;
      letter-spacing: 0.02em;
      font-weight: 500;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: scale(0.97); }
      to { opacity: 1; transform: scale(1); }
    }
    @keyframes pulseGlow {
      0%, 100% { transform: scale(0.9); opacity: 0.5; }
      50% { transform: scale(1.25); opacity: 0.9; }
    }
    @keyframes shimmerBar {
      0% { left: -40%; width: 30%; }
      50% { left: 35%; width: 50%; }
      100% { left: 100%; width: 30%; }
    }
  </style>
</head>
<body>
  <div class="splash-container">
    <div class="logo-wrapper">
      <div class="logo-glow"></div>
      <svg class="shield-svg" viewBox="0 0 24 24" stroke="url(#shieldGrad)" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
        <defs>
          <linearGradient id="shieldGrad" x1="0%" y1="0%" x2="100%" y2="100%">
            <stop offset="0%" stop-color="#818cf8" />
            <stop offset="100%" stop-color="#4f46e5" />
          </linearGradient>
        </defs>
        <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" fill="rgba(99, 102, 241, 0.15)"/>
        <path d="M12 22V2" />
      </svg>
    </div>
    <div class="brand-title">Aegis Suite</div>
    <div class="brand-subtitle">Enterprise Protection</div>
    <div class="status-bar-container">
      <div class="status-bar-fill"></div>
    </div>
    <div class="status-text" id="splash-status">Starting core engine...</div>
  </div>
</body>
</html>"""

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

        class DesktopBridge:
            """Exposes native window capabilities to the dashboard web interface."""
            def __init__(self):
                self._window = None

            def set_window(self, win):
                self._window = win

            def toggle_fullscreen(self):
                if self._window:
                    try:
                        self._window.toggle_fullscreen()
                        return bool(getattr(self._window, "fullscreen", False))
                    except Exception as err:
                        logger.warning(f"Error toggling fullscreen: {err}")
                return False

            def is_fullscreen(self):
                if self._window:
                    return bool(getattr(self._window, "fullscreen", False))
                return False

        desktop_bridge = DesktopBridge()

        # Application assets directory (distinct from writable AppData paths.root)
        app_base_dir = getattr(sys, "_MEIPASS", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

        # Initialize System Tray Manager
        tray_mgr = None
        try:
            from aegis.core.tray import SystemTrayManager
            tray_mgr = SystemTrayManager(
                root_dir=app_base_dir,
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

        def start_server_and_load():
            """Background worker executed by PyWebView as soon as the native GUI window and message pump are active."""
            logger.info("GUI message pump active; spinning up AppCore in background...")
            bg_thread = threading.Thread(target=lambda: loop.run_until_complete(core.run()), daemon=True)
            bg_thread.start()

            # Poll for web server health probe
            start_wait = time.time()
            max_wait = 30.0
            server_ready = False
            while time.time() - start_wait < max_wait:
                if core.web_port is not None:
                    try:
                        import urllib.request
                        probe_url = f"http://127.0.0.1:{core.web_port}/api/health"
                        req = urllib.request.Request(probe_url)
                        with urllib.request.urlopen(req, timeout=0.5) as resp:
                            if resp.status == 200:
                                server_ready = True
                                break
                    except Exception:
                        pass
                time.sleep(0.1)

            if server_ready and core.web_port is not None:
                dash_url = f"http://127.0.0.1:{core.web_port}"
                logger.info(f"Navigating native window to dashboard: {dash_url}")
                # Brief aesthetic pause for splash screen elegance
                time.sleep(0.25)
                if window_ref:
                    try:
                        window_ref.load_url(dash_url)
                    except Exception as load_err:
                        logger.warning(f"Could not load dashboard in native window: {load_err}")
                        webbrowser.open(dash_url)
            else:
                logger.error("Web server startup timed out after 30 seconds.")
                if window_ref:
                    try:
                        window_ref.evaluate_js(
                            "document.getElementById('splash-status').textContent = 'Startup timed out. Please restart Aegis Suite.';"
                        )
                    except Exception:
                        pass

        try:
            window_ref = webview.create_window(
                title="Aegis Suite",
                html=SPLASH_HTML,
                js_api=desktop_bridge,
                width=1280,
                height=850,
                min_size=(960, 640),
                resizable=True,
                background_color="#0b0f19"
            )
            desktop_bridge.set_window(window_ref)
            window_ref.events.closing += on_closing

            def set_window_native_icon():
                try:
                    base_dir = os.path.dirname(os.path.abspath(__file__))
                    ico_candidates = []
                    meipass = getattr(sys, "_MEIPASS", None)
                    if meipass:
                        ico_candidates.extend([
                            os.path.join(meipass, "logo.ico"),
                        ])
                    ico_candidates.extend([
                        os.path.join(base_dir, "..", "logo.ico"),
                        os.path.join(base_dir, "logo.ico"),
                        os.path.join(os.getcwd(), "logo.ico"),
                        os.path.join(os.path.dirname(sys.executable), "logo.ico"),
                    ])
                    target_ico = next((p for p in ico_candidates if p.lower().endswith(".ico") and os.path.exists(p)), None)
                    if target_ico and hasattr(window_ref, "native") and window_ref.native:
                        import clr
                        clr.AddReference("System.Drawing")
                        from System.Drawing import Icon
                        window_ref.native.Icon = Icon(target_ico)
                        logger.info(f"Set PyWebView native window icon: {target_ico}")
                except Exception as ex:
                    logger.debug(f"Could not set native window icon: {ex}")

            window_ref.events.shown += set_window_native_icon
            webview.start(start_server_and_load, gui='edgechromium', debug=False)
        except Exception as e:
            logger.warning(f"PyWebView launch error: {e}. Opening browser...")
            bg_thread = threading.Thread(target=lambda: loop.run_until_complete(core.run()), daemon=True)
            bg_thread.start()
            start_wait = time.time()
            while time.time() - start_wait < 30.0:
                if core.web_port is not None:
                    webbrowser.open(f"http://127.0.0.1:{core.web_port}")
                    break
                time.sleep(0.2)
            bg_thread.join()
        finally:
            if tray_mgr:
                tray_mgr.stop()
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
