#!/usr/bin/env python3
"""
Script de diagnóstico para verificar que todo funciona antes de buildear.
"""

import sys
import os

# Agregar src al path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_imports():
    """Verifica que todas las importaciones funcionen."""
    print("🧪 Probando importaciones...")
    
    try:
        from src.resources import resource_path
        print("  ✓ resource_path importado")
    except ImportError as e:
        print(f"  ✗ Error importando resource_path: {e}")
        return False
    
    try:
        from src.asset_manager import AssetManager, AudioManager
        print("  ✓ AssetManager y AudioManager importados")
    except ImportError as e:
        print(f"  ✗ Error importando managers: {e}")
        return False
    
    try:
        from src.config import (
            SOUND_BGM, SOUND_SMALL_GIFT, SOUND_BIG_GIFT, SOUND_VICTORY,
            VOL_BGM, VOL_SFX
        )
        print("  ✓ Configuración de audio importada")
    except ImportError as e:
        print(f"  ✗ Error importando config: {e}")
        return False
    
    return True

def test_resources():
    """Verifica que los recursos existan."""
    print("\n📂 Verificando recursos...")
    
    from src.resources import resource_path
    
    all_good = True
    
    # Verificar carpetas
    folders = ['assets', 'assets/audio', 'assets/gifts']
    for folder in folders:
        path = resource_path(folder)
        if os.path.exists(path):
            print(f"  ✓ {folder}")
        else:
            print(f"  ✗ {folder} - NO EXISTE")
            all_good = False
    
    # Verificar archivos de audio
    audio_files = [
        'assets/audio/bgm.wav',
        'assets/audio/small_gift.wav',
        'assets/audio/big_gift.wav',
        'assets/audio/victory.wav'
    ]
    
    for audio_file in audio_files:
        path = resource_path(audio_file)
        if os.path.exists(path):
            size = os.path.getsize(path) / 1024  # KB
            print(f"  ✓ {audio_file} ({size:.1f} KB)")
        else:
            print(f"  ✗ {audio_file} - NO EXISTE")
            all_good = False
    
    return all_good

def test_audio_manager():
    """Verifica que el AudioManager pueda inicializarse."""
    print("\n🔊 Probando AudioManager...")
    
    try:
        from src.asset_manager import AudioManager
        audio_manager = AudioManager()
        
        print(f"  ✓ AudioManager inicializado")
        print(f"  ✓ Sonidos cargados: {audio_manager.loaded_sounds_count}")
        
        if audio_manager.missing_sounds:
            print(f"  ⚠ Sonidos faltantes: {audio_manager.missing_sounds}")
            return False
        
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_asset_manager():
    """Verifica que el AssetManager pueda inicializarse."""
    print("\n🎨 Probando AssetManager...")
    
    try:
        from src.asset_manager import AssetManager
        asset_manager = AssetManager()
        
        print(f"  ✓ AssetManager inicializado")
        print(f"  ✓ Assets cargados: {asset_manager.loaded_count}")
        
        if asset_manager.available_gifts:
            print(f"  ✓ Sprites disponibles: {', '.join(asset_manager.available_gifts[:5])}...")
        
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """Ejecuta todos los tests."""
    print("=" * 60)
    print("  TikTok Live Bot - Diagnóstico")
    print("=" * 60)
    print()
    
    results = []
    
    results.append(test_imports())
    results.append(test_resources())
    results.append(test_audio_manager())
    results.append(test_asset_manager())
    
    all_passed = all(results)
    
    print()
    print("=" * 60)
    if all_passed:
        print("✅ Todos los tests pasaron - listo para buildear")
        print("\nEjecuta: python build_app_fixed.py")
    else:
        print("❌ Algunos tests fallaron - revisa los errores arriba")
        print(f"\nTests pasados: {sum(results)}/{len(results)}")
    print("=" * 60)
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())