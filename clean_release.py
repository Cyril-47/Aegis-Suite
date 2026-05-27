"""
🛠️ Aegis Server Optimizer - Developer Release Cleanup Utility
⚠️ DEVELOPER USE ONLY. Do NOT bundle or ship this script inside end-user installer packages.
"""

import os
import sys
import shutil

def main():
    print("="*60)
    print("  AEGIS DISCORD BOT & OPTIMIZER - RELEASE CLEANUP UTILITY")
    print("="*60)
    
    # Check for confirm flag
    confirmed = "--confirm" in sys.argv
    
    if not confirmed:
        prompt = (
            "⚠️  WARNING: This script will permanently delete all local secrets, active configurations, "
            "moderation databases, and build caches (.env, config.json, audit_log.json, leveling data, "
            "giveaways, and dist/build folders).\n\n"
            "Are you sure you want to proceed with cleanup? (y/N): "
        )
        try:
            choice = input(prompt).strip().lower()
            if choice not in ["y", "yes"]:
                print("[-] Cleanup cancelled. No files were deleted.")
                return
        except KeyboardInterrupt:
            print("\n[-] Cleanup cancelled. No files were deleted.")
            return

    print("[*] Preparing project directory for public GitHub upload...")
    
    # 1. Files to delete (sensitive databases and credentials)
    files_to_delete = [
        ".env",
        "config.json",
        "audit_log.json",
        "leveling_data.json",
        "giveaways.json",
        "logo.ico"
    ]
    
    for filename in files_to_delete:
        if os.path.exists(filename):
            try:
                os.remove(filename)
                print(f"[+] Removed local file: {filename}")
            except Exception as e:
                print(f"[-] Failed to remove {filename}: {e}")
                
    # 2. Folders to delete (compiler build caches and custom templates)
    folders_to_delete = [
        "build",
        "dist",
        "__pycache__",
        "templates" # User-saved templates; default ones are auto-recreated on start
    ]
    
    for folder in folders_to_delete:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"[+] Removed local folder: {folder}")
            except Exception as e:
                print(f"[-] Failed to remove {folder}: {e}")
                
    # 3. Clean python cache files in subfolders
    for root, dirs, files in os.walk("."):
        if "__pycache__" in dirs:
            pycache_path = os.path.join(root, "__pycache__")
            try:
                shutil.rmtree(pycache_path)
                print(f"[+] Cleaned python cache in: {root}")
            except Exception:
                pass
                
    print("\n" + "="*60)
    print("[SUCCESS] Project directory is now clean and ready for Git / GitHub upload!")
    print("ℹ️ Note: Compiled binaries should be uploaded as a 'GitHub Release'")
    print("   rather than committed directly into the source code repository.")
    print("="*60)

if __name__ == "__main__":
    main()
