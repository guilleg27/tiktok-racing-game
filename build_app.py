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

    # IMPORTANTE: Copiar solo las subcarpetas necesarias de assets
    # Excluir venv y otras carpetas innecesarias
    assets_to_include = []
    for subfolder in ['audio', 'gifts', 'sounds']:
        subfolder_path = os.path.join('assets', subfolder)
        if os.path.isdir(subfolder_path):
            assets_to_include.extend([
                "--add-data", f"{subfolder_path}{separator}assets/{subfolder}"
            ])
            print(f"  ✓ Incluyendo: {subfolder_path}")

    # Construir comando PyInstaller
    cmd = [
        "pyinstaller",
        "--name", "TikTokRacingGoLive",
        "--windowed",  # No mostrar consola
        "--onedir",    # Carpeta en lugar de archivo único (más confiable)
        "--clean",     # Limpiar caché
        "--noconfirm", # No pedir confirmación
        
        # Agregar subcarpetas específicas de assets (excluyendo venv)
        *assets_to_include,
        
        # Excluir explícitamente cosas que no queremos
        "--exclude-module", "matplotlib",
        "--exclude-module", "tkinter",
        "--exclude-module", "PIL",
        
        # Hidden imports (módulos que PyInstaller podría no detectar)
        "--hidden-import", "pygame",
        "--hidden-import", "pymunk",
        "--hidden-import", "aiosqlite",
        "--hidden-import", "TikTokLive",
        "--hidden-import", "TikTokLive.events",
        
        # Icono si existe
        *icon_arg,
        
        # Archivo principal
        "main.py"
    ]

    print("\n🚀 Ejecutando PyInstaller...")
    print("Comando:", " ".join(cmd))
    print()
    
    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print(result.stdout)
        
        print("\n✅ Build completado exitosamente!")
        
        if system == "Darwin":
            print(f"📍 Ejecutable en: dist/TikTokRacingGoLive.app")
            print("\n💡 Para ejecutar desde terminal:")
            print("   open dist/TikTokRacingGoLive.app")
            print("\n💡 O directamente:")
            print("   dist/TikTokRacingGoLive.app/Contents/MacOS/TikTokRacingGoLive")
        else:
            print(f"📍 Ejecutable en: dist\\TikTokRacingGoLive\\TikTokRacingGoLive.exe")
            
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