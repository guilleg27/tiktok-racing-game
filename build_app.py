#!/usr/bin/env python3
"""
Script para construir el ejecutable del TikTok Live Bot.
Usa --onedir que es más confiable que --onefile en macOS.

Usage:
    python build_app.py                    # countries variant (default)
    python build_app.py --variant countries
    python build_app.py --variant motos
"""

import argparse
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

VARIANT_CONFIG = {
    "countries": {
        "entry_point": "variants/countries/main.py",
        "app_name": "TikTokRacingGoLive",
    },
    "motos": {
        "entry_point": "variants/motos/main.py",
        "app_name": "MotoRace",
    },
}


def build(variant: str = "countries"):
    """Construye el ejecutable usando PyInstaller."""

    if variant not in VARIANT_CONFIG:
        print(f"❌ Variant desconocida: {variant}. Opciones: {list(VARIANT_CONFIG)}")
        sys.exit(1)

    cfg = VARIANT_CONFIG[variant]
    entry_point = cfg["entry_point"]
    app_name = cfg["app_name"]

    print(f"🎮 Variant: {variant}  →  entry: {entry_point}  →  name: {app_name}")

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
    asset_subfolders = ['audio', 'gifts', 'sounds', 'fonts', 'images', 'backgrounds', 'flags', 'motos']
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
        "--name", app_name,
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

        entry_point,
    ]

    print("\n🚀 Ejecutando PyInstaller...")
    print("Comando:", " ".join(cmd))
    print()

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)

        print("\n✅ Build completado exitosamente!")

        dist_dir = os.path.join("dist", app_name)
        if system == "Darwin":
            app_path = os.path.join("dist", f"{app_name}.app")
            print(f"📍 Salida (--onedir): {app_path}")
            print("\n💡 Ejecutar:")
            print(f"   open dist/{app_name}.app")
            print(f"   o: dist/{app_name}.app/Contents/MacOS/{app_name}")
        else:
            exe_path = os.path.join(dist_dir, f"{app_name}.exe")
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
    parser = argparse.ArgumentParser(description="Build TikTok Racing Go executable")
    parser.add_argument(
        "--variant",
        choices=list(VARIANT_CONFIG),
        default="countries",
        help="Which variant to build (default: countries)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"  TikTok Racing Go Live - Builder ({args.variant})")
    print("=" * 60)
    print()
    build(args.variant)