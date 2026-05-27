import os
import sys
import shutil
import secrets
import subprocess
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

def main():
    print("="*60)
    print("  AEGIS DISCORD BOT & OPTIMIZER - EXECUTABLE BUILD UTILITY")
    print("="*60)
    
    # 1. Generate Icon
    logo_png = "bot_logo.png"
    logo_ico = "logo.ico"
    convert_png_to_ico(logo_png, logo_ico)
    
    # 2. Key generation for encryption (to prevent decompiling pyc)
    enc_key = secrets.token_hex(8) # 16-char hex key for AES-256 bytecode encryption
    print(f"[+] Generated unique bytecode encryption key: {enc_key}")
    
    # 3. Clean previous build folders
    for folder in ["build", "dist"]:
        if os.path.exists(folder):
            print(f"[+] Cleaning previous '{folder}' folder...")
            try:
                shutil.rmtree(folder)
            except Exception as e:
                print(f"[-] Warning: Failed to clean {folder}: {e}")
                
    # 4. Formulate PyInstaller command
    cmd = [
        "pyinstaller",
        "--onedir",
        "--name=AegisOptimizer",
        "--add-data", "static;static",
        "--add-data", "templates;templates"
    ]
    
    if os.path.exists(logo_ico):
        cmd.extend(["--icon", logo_ico])
        
    cmd.append("run.py")
    
    print("\n[+] Starting PyInstaller compilation process (this may take 1-2 minutes)...")
    print(f"[Command] {' '.join(cmd)}")
    
    try:
        # Run PyInstaller
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print("\n" + "="*60)
            print("[SUCCESS] AegisOptimizer directory built successfully!")
            print("="*60)
            
            # Resolve executable path
            exe_path = os.path.abspath(os.path.join("dist", "AegisOptimizer", "AegisOptimizer.exe"))
            print(f"[Executable Path] {exe_path}")
            print(f"[Onedir Folder]   {os.path.dirname(exe_path)}")
            print("\n[Info] Note: Shortcut creation is deferred to your installer generator (e.g., Inno Setup).")
        else:
            print("\n" + "="*60)
            print("[ERROR] Build failed! PyInstaller Output:")
            print("="*60)
            print(result.stdout)
            print(result.stderr)
            
    except Exception as e:
        print(f"[-] Build crashed with exception: {e}")

if __name__ == "__main__":
    main()
