#!/usr/bin/env python3
"""
Script para construir el ejecutable del TikTok Live Bot.
Usa --onedir que es más confiable que --onefile en macOS.
"""

import os
import sys
import platform
import subprocess
import shutil

def clean_build():
    """Limpia directorios de builds anteriores."""
    folders_to_clean = ['build', 'dist', '__pycache__']
    for folder in folders_to_clean:
        if os.path.exists(folder):
            try:
                shutil.rmtree(folder)
                print(f"✓ Limpiado: {folder}")
            except Exception as e:
                print(f"⚠ No se pudo limpiar {folder}: {e}")
    
    # Limpiar archivos .spec
    for file in os.listdir('.'):
        if file.endswith('.spec'):
            try:
                os.remove(file)
                print(f"✓ Eliminado: {file}")
            except Exception as e:
                print(f"⚠ No se pudo eliminar {file}: {e}")

def detect_icon():
    """Busca un icono .ico o .icns en la raíz del proyecto."""
    for ext in ('.ico', '.icns'):
        for fname in os.listdir('.'):
            if fname.lower().endswith(ext):
                return fname
    return None

def build():
    """Construye el ejecutable usando PyInstaller."""
    
    # Limpiar builds anteriores
    print("🧹 Limpiando builds anteriores...")
    clean_build()
    
    system = platform.system()
    
    if system == "Windows":
        separator = ";"
    elif system == "Darwin":  # macOS
        separator = ":"
    else:
        print("❌ Sistema operativo no soportado.")
        sys.exit(1)

    # Detectar icono
    icon = detect_icon()
    icon_arg = []
    if icon:
        icon_arg = ["--icon", icon]
        print(f"🎨 Icono detectado: {icon}")
    else:
        print("ℹ️  No se detectó icono")

    # Verificar carpeta assets
    if not os.path.isdir("assets"):
        print("❌ Error: No se encontró la carpeta 'assets'")
        sys.exit(1)
    
    print(f"📦 Assets detectados: assets/")

    # Required asset subfolders. fonts and images (e.g. flags) must exist for visuals.
    # backgrounds is optional (fallback to procedural star field).
    asset_subfolders = ['audio', 'gifts', 'sounds', 'fonts', 'images', 'icons', 'backgrounds']
    assets_to_include = []
    for subfolder in asset_subfolders:
        subfolder_path = os.path.join('assets', subfolder)
        if os.path.isdir(subfolder_path):
            assets_to_include.extend([
                "--add-data", f"{subfolder_path}{separator}assets/{subfolder}"
            ])
            print(f"  ✓ Incluyendo: {subfolder_path} -> assets/{subfolder}")
        elif subfolder in ('fonts', 'images'):
            print(f"  ⚠ No encontrada: {subfolder_path} (crea la carpeta si el juego la usa)")

    # Build PyInstaller command. --onedir keeps Windows/macOS runs smooth and output clear.
    cmd = [
        "pyinstaller",
        "--name", "TikTokRacingGoLive",
        "--windowed",  # No console window
        "--onedir",    # Output as folder (more reliable than --onefile on Windows/macOS)
        "--clean",
        "--noconfirm",

        *assets_to_include,

        # Exclude only what we don't need (tkinter is required for login dialog)
        "--exclude-module", "matplotlib",
        "--exclude-module", "PIL",

        # Hidden imports so PyInstaller bundles them
        "--hidden-import", "pygame",
        "--hidden-import", "pymunk",
        "--hidden-import", "aiosqlite",
        "--hidden-import", "TikTokLive",
        "--hidden-import", "TikTokLive.events",
        "--hidden-import", "pyttsx3.drivers",
        "--hidden-import", "pyttsx3.drivers.sapi5",   # Windows TTS
        "--hidden-import", "pyttsx3.drivers.nsss",    # macOS TTS

        # Supabase + HTTP stack (dynamic imports not detected by PyInstaller)
        "--hidden-import", "supabase",
        "--hidden-import", "postgrest",
        "--hidden-import", "gotrue",
        "--hidden-import", "storage3",
        "--hidden-import", "realtime",
        "--hidden-import", "httpx",
        "--hidden-import", "httpcore",
        "--hidden-import", "httpcore._backends.sync",
        "--hidden-import", "httpcore._backends.asyncio",
        "--hidden-import", "certifi",                  # SSL certificates on Windows
        "--collect-all", "certifi",                    # Bundle CA certs bundle

        *icon_arg,

        "main.py"
    ]

    print("\n🚀 Ejecutando PyInstaller...")
    print("Comando:", " ".join(cmd))
    print()
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        
        print("\n✅ Build completado exitosamente!")
        
        dist_dir = os.path.join("dist", "TikTokRacingGoLive")
        if system == "Darwin":
            app_path = os.path.join("dist", "TikTokRacingGoLive.app")
            print(f"📍 Salida (--onedir): {app_path}")
            print("\n💡 Ejecutar:")
            print("   open dist/TikTokRacingGoLive.app")
            print("   o: dist/TikTokRacingGoLive.app/Contents/MacOS/TikTokRacingGoLive")
        else:
            exe_path = os.path.join(dist_dir, "TikTokRacingGoLive.exe")
            print(f"📍 Salida (--onedir): {os.path.normpath(dist_dir)}")
            print(f"   Ejecutable: {os.path.normpath(exe_path)}")
            
    except subprocess.CalledProcessError as e:
        print(f"\n❌ Error durante el build:")
        if e.stdout:
            print("STDOUT:", e.stdout)
        if e.stderr:
            print("STDERR:", e.stderr)
        sys.exit(1)

if __name__ == "__main__":
    print("=" * 60)
    print("  TikTok Racing Go Live - Builder")
    print("=" * 60)
    print()
    build()