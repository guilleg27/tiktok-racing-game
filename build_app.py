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

# Windows console may use CP1252 which can't encode emoji — force UTF-8.
if sys.stdout.encoding and sys.stdout.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stdout.reconfigure(encoding='utf-8')
if sys.stderr.encoding and sys.stderr.encoding.lower() not in ('utf-8', 'utf8'):
    sys.stderr.reconfigure(encoding='utf-8')

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


def generate_ico_from_png(png_path, ico_path):
    """Generate a multi-size Windows ``.ico`` from a PNG using pygame.

    Avoids a Pillow dependency by embedding PNG-compressed images inside the
    ICO container (supported by Windows Vista and newer). Generates the common
    icon sizes so Explorer, the taskbar and the title bar all look crisp.

    Args:
        png_path: Source PNG path.
        ico_path: Destination ``.ico`` path to write.

    Returns:
        The ``ico_path`` on success, otherwise ``None``.
    """
    try:
        import io
        import struct
        os.environ.setdefault('SDL_VIDEODRIVER', 'dummy')
        import pygame
        if not pygame.get_init():
            pygame.init()
        src = pygame.image.load(png_path)
        sizes = [16, 32, 48, 64, 128, 256]
        images = []
        for size in sizes:
            scaled = pygame.transform.smoothscale(src, (size, size))
            buf = io.BytesIO()
            pygame.image.save(scaled, buf, "icon.png")
            images.append((size, buf.getvalue()))

        count = len(images)
        header = struct.pack('<HHH', 0, 1, count)
        offset = 6 + count * 16
        entries = b''
        datas = b''
        for size, data in images:
            dim = 0 if size >= 256 else size  # 0 means 256 in the ICO spec
            entries += struct.pack('<BBBBHHII', dim, dim, 0, 0, 1, 32, len(data), offset)
            datas += data
            offset += len(data)

        with open(ico_path, 'wb') as f:
            f.write(header + entries + datas)
        return ico_path
    except Exception as e:
        print(f"⚠ No se pudo generar .ico desde {png_path}: {e}")
        return None


def generate_icns_from_png(png_path, icns_path):
    """Generate a macOS ``.icns`` from a PNG using built-in sips/iconutil.

    Best-effort: returns ``None`` if the macOS tooling is unavailable.

    Args:
        png_path: Source PNG path.
        icns_path: Destination ``.icns`` path to write.

    Returns:
        The ``icns_path`` on success, otherwise ``None``.
    """
    try:
        import tempfile
        iconset = os.path.join(tempfile.mkdtemp(), 'icon.iconset')
        os.makedirs(iconset, exist_ok=True)
        specs = [
            (16, 'icon_16x16.png'), (32, 'icon_16x16@2x.png'),
            (32, 'icon_32x32.png'), (64, 'icon_32x32@2x.png'),
            (128, 'icon_128x128.png'), (256, 'icon_128x128@2x.png'),
            (256, 'icon_256x256.png'), (512, 'icon_256x256@2x.png'),
            (512, 'icon_512x512.png'), (1024, 'icon_512x512@2x.png'),
        ]
        for size, name in specs:
            subprocess.run(
                ['sips', '-z', str(size), str(size), png_path, '--out',
                 os.path.join(iconset, name)],
                check=True, capture_output=True,
            )
        subprocess.run(
            ['iconutil', '-c', 'icns', iconset, '-o', icns_path],
            check=True, capture_output=True,
        )
        return icns_path
    except Exception as e:
        print(f"⚠ No se pudo generar .icns desde {png_path}: {e}")
        return None

VARIANT_CONFIG = {
    "countries": {
        "entry_point": "variants/countries/main.py",
        "app_name": "TikTokRacingGoLive",
        "extra_assets": [],
    },
    "motos": {
        "entry_point": "variants/motos/main.py",
        "app_name": "MotoRace",
        "extra_assets": [],
    },
    "motos_extended": {
        "entry_point": "variants/motos_extended/main.py",
        "app_name": "MotoRaceExtended",
        "extra_assets": [],
    },
    "versus": {
        "entry_point": "variants/versus/main.py",
        "app_name": "versus",
        "extra_assets": [],
    },
    "fulbito": {
        "entry_point": "variants/fulbito/main.py",
        "app_name": "Fulbito",
        "extra_assets": ["variants/fulbito/assets"],
        "icon_source": "variants/fulbito/assets/wc2026.png",
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

    # Detectar/generar icono. Si la variante define icon_source (un PNG), se
    # genera el formato nativo: .ico en Windows, .icns en macOS. Si falla o no
    # hay icon_source, se cae al autodetect de la raíz del proyecto.
    import tempfile
    icon = None
    icon_temp = None
    icon_source = cfg.get("icon_source")
    if icon_source and os.path.exists(icon_source):
        icon_dir = tempfile.mkdtemp(prefix="build_icon_")
        if system == "Windows":
            icon = generate_ico_from_png(icon_source, os.path.join(icon_dir, "app_icon.ico"))
        elif system == "Darwin":
            icon = generate_icns_from_png(icon_source, os.path.join(icon_dir, "app_icon.icns"))
        if icon:
            icon_temp = icon
            print(f"🎨 Icono generado desde {icon_source} -> {icon}")
    if not icon:
        icon = detect_icon()
        if icon:
            print(f"🎨 Icono detectado: {icon}")
    icon_arg = []
    if icon:
        icon_arg = ["--icon", icon]
    else:
        print("ℹ️  No se detectó icono")

    # Verificar carpeta assets
    if not os.path.isdir("assets"):
        print("❌ Error: No se encontró la carpeta 'assets'")
        sys.exit(1)
    
    print(f"📦 Assets detectados: assets/")

    # Required asset subfolders. fonts and images (e.g. flags) must exist for visuals.
    # backgrounds is optional (fallback to procedural star field).
    asset_subfolders = [
        'audio', 'gifts', 'sounds', 'fonts', 'images', 'backgrounds', 'flags', 'motos', 'versus',
    ]
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

    for extra in cfg.get("extra_assets", []):
        if os.path.isdir(extra):
            assets_to_include.extend([
                "--add-data", f"{extra}{separator}{extra}"
            ])
            print(f"  ✓ Incluyendo (variant): {extra} -> {extra}")
        else:
            print(f"  ⚠ No encontrada (variant): {extra}")

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

        # tkinter — required for the startup dialog on all platforms
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.simpledialog",

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

        # OpenCV + NumPy — required for motos victory video playback
        "--hidden-import", "cv2",
        "--collect-all", "cv2",
        "--hidden-import", "numpy",
        "--collect-all", "numpy",

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
    finally:
        # Limpiar el icono temporal generado desde el PNG de la variante.
        if icon_temp:
            try:
                shutil.rmtree(os.path.dirname(icon_temp), ignore_errors=True)
            except Exception:
                pass

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build TikTok Racing Go executable")
    parser.add_argument(
        "--variant",
        choices=list(VARIANT_CONFIG),
        default="countries",
        help=f"Which variant to build (default: countries). Options: {', '.join(VARIANT_CONFIG)}",
    )
    args = parser.parse_args()

    print("=" * 60)
    print(f"  TikTok Racing Go Live - Builder ({args.variant})")
    print("=" * 60)
    print()
    build(args.variant)