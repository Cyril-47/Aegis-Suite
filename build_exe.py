import os
import sys
import shutil
import secrets
import subprocess
import discord
from PIL import Image

# Path helper functions are located in utils.py

def convert_png_to_ico(png_path, ico_path):
    if not os.path.exists(png_path):
        print(f"[-] Image {png_path} not found. Skipping icon generation.")
        return False
    try:
        img = Image.open(png_path)
        # Generate standard icon sizes
        img.save(ico_path, format='ICO', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
        print(f"[+] Successfully converted {png_path} to {ico_path}")
        return True
    except Exception as e:
        print(f"[-] Failed to convert image to icon: {e}")
        return False


def create_desktop_shortcut(exe_path: str, ico_path: str) -> bool:
    """Create a Windows Desktop shortcut for the built executable.

    Returns True on success, False when the shortcut step is skipped (missing
    optional dependencies, missing Desktop folder). Either skip path is
    non-fatal: the caller treats False as "build still succeeded, just no
    shortcut".
    """
    try:
        import winshell
        from win32com.client import Dispatch
    except ImportError:
        print(
            "[!] winshell and pywin32 are required for desktop shortcut creation. "
            "Install them with: pip install winshell pywin32. "
            "Skipping shortcut step; the executable is still available at "
            f"{exe_path}."
        )
        return False

    # winshell.desktop() resolves CSIDL_DESKTOPDIRECTORY, which honors
    # OneDrive-redirected profiles (e.g. C:\Users\<name>\OneDrive\Desktop).
    desktop = winshell.desktop()
    if not os.path.isdir(desktop):
        print(f"[-] Resolved Desktop folder does not exist: {desktop}. Skipping shortcut.")
        return False

    shortcut_path = os.path.join(desktop, "Aegis Optimizer.lnk")
    shell = Dispatch("WScript.Shell")
    shortcut = shell.CreateShortCut(shortcut_path)
    shortcut.Targetpath = exe_path
    shortcut.WorkingDirectory = os.path.dirname(exe_path)
    shortcut.IconLocation = ico_path
    shortcut.save()
    print(f"[+] Created Desktop shortcut: {shortcut_path}")
    return True


def main():
    print("="*60)
    print("  AEGIS DISCORD BOT & OPTIMIZER - EXECUTABLE BUILD UTILITY")
    print("="*60)

    # 1. Generate Icon
    logo_png = "bot_logo.png"
    logo_ico = "logo.ico"
    convert_png_to_ico(logo_png, logo_ico)

    # 2. Key generation for encryption (to prevent decompiling pyc)
    enc_key = secrets.token_hex(8)  # 16-char hex key for AES-256 bytecode encryption
    print(f"[+] Generated unique bytecode encryption key: {enc_key}")

    # 3. Clean previous build folders
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"[+] Cleaning previous '{folder}' folder...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"[-] Warning: Failed to clean {folder}: {e}")

    discord_bin = os.path.join(os.path.dirname(discord.__file__), "bin")

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--noconsole",
        "--name=AegisOptimizer",
        "--add-data", "static;static",
        "--add-data", f"{discord_bin};discord/bin",
        "--add-data", "templates;templates",
        "--add-data", "alembic.ini;.",
        "--add-data", "aegis/db/migrations;aegis/db/migrations",
        # Hidden imports: uvicorn.run("web_server:app") does a dynamic import
        # that PyInstaller cannot trace statically. List every project module
        # and key third-party module that the app needs at runtime.
        "--hidden-import", "aegis.core.app_core",
        "--hidden-import", "aegis.core.health",
        "--hidden-import", "aegis.core.lifecycle",
        "--hidden-import", "aegis.core.logging_setup",
        "--hidden-import", "aegis.core.paths",
        "--hidden-import", "aegis.core.state",
        "--hidden-import", "aegis.core.single_instance",
        "--hidden-import", "aegis.config.loader",
        "--hidden-import", "aegis.config.sanitizer",
        "--hidden-import", "aegis.config.schema",
        "--hidden-import", "aegis.db.engine",
        "--hidden-import", "aegis.db.maintenance",
        "--hidden-import", "aegis.db.models",
        "--hidden-import", "aegis.db.legacy_import",
        "--hidden-import", "aegis.bot.runner",
        "--hidden-import", "aegis.bot.commands",
        "--hidden-import", "aegis.bot.leveling",
        "--hidden-import", "aegis.bot.music",
        "--hidden-import", "aegis.web.app",
        "--hidden-import", "aegis.web.server",
        "--hidden-import", "aegis.web.wizard_ui",
        "--hidden-import", "aegis.web.recovery_ui",
        "--hidden-import", "aegis.web.routes.health",
        "--hidden-import", "aegis.web.routes.dashboard",
        "--hidden-import", "aegis.web.routes.wizard",
        "--hidden-import", "aegis.web.routes.diagnostics",
        "--hidden-import", "aegis.templates_engine.model",
        "--hidden-import", "aegis.templates_engine.registry",
        "--hidden-import", "aegis.templates_engine.io",
        "--hidden-import", "aegis.templates_engine.apply",
        "--hidden-import", "aegis.diagnostics.packager",
        "--hidden-import", "aegis.bot.bot_manager",
        "--hidden-import", "aegis.bot.anti_raid",
        "--hidden-import", "aegis.core.auth",
        "--hidden-import", "aegis.core.utils",
        "--hidden-import", "aegis.core.audit_log",
        "--hidden-import", "aegis.core.secret_store",
        "--hidden-import", "aegis.analytics.__init__",
        "--hidden-import", "aegis.analytics.engine",
        "--hidden-import", "aegis.analytics.aggregator",
        "--hidden-import", "aegis.db.analytics_models",
        "--hidden-import", "aegis.web.routes.analytics",
        "--hidden-import", "first_run_wizard",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols",
        "--hidden-import", "uvicorn.protocols.http",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--hidden-import", "uvicorn.lifespan",
        "--hidden-import", "uvicorn.lifespan.on",
        "--hidden-import", "discord",
        "--hidden-import", "fastapi",
        "--hidden-import", "pydantic",
        "--hidden-import", "websockets",
        "--hidden-import", "_cffi_backend",
        "--hidden-import", "nacl",
        "--hidden-import", "nacl.secret",
        "--hidden-import", "nacl.signing",
        "--hidden-import", "nacl.utils",
        "--collect-submodules", "nacl",
        "--hidden-import", "alembic",
        "--hidden-import", "sqlalchemy",
    ]

    # Secrets (.env or .env.enc) are intentionally NOT bundled with the executable.
    # At runtime, secrets are read from the writeable path in the data directory
    # (e.g. %APPDATA%\Aegis\.env or %APPDATA%\Aegis\.env.enc).
    print("[+] Secrets (.env/.env.enc) are excluded from the bundle. At runtime, they are read from %APPDATA%\\Aegis.")

    cmd.append(os.path.join("aegis", "__main__.py"))

    print("\n[+] Starting PyInstaller compilation process (this may take 1-2 minutes)...")
    print(f"[Command] {' '.join(cmd)}")

    # 5. Run PyInstaller and gate the rest of the build on its return code.
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("\n" + "="*60)
        print("[ERROR] Build failed! PyInstaller Output:")
        print("="*60)
        print(result.stdout)
        print(result.stderr)
        sys.exit(result.returncode)

    print("\n" + "="*60)
    print("[SUCCESS] AegisOptimizer.exe built successfully!")
    print("="*60)

    # 6. Resolve absolute paths to the EXE and the icon for the shortcut step.
    exe_path = os.path.abspath(os.path.join("dist", "AegisOptimizer.exe"))
    ico_path = os.path.abspath(logo_ico)
    print(f"[Executable Path] {exe_path}")

    # 7. Best-effort Desktop shortcut. Missing optional deps, a missing Desktop
    # folder, or an unexpected COM error must NOT fail the build: the EXE is
    # the primary artifact and is already on disk at this point.
    try:
        create_desktop_shortcut(exe_path, ico_path)
    except Exception as e:
        print(f"[!] Desktop shortcut creation raised an unexpected error: {e}. "
              "The executable is still available; continuing.")

    sys.exit(0)


if __name__ == "__main__":
    main()
