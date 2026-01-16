#!/usr/bin/env python3
"""
Test de audio para diagnosticar problemas con sonidos en modo IDLE.
"""

import sys
import os
sys.path.insert(0, 'src')

import pygame
import time

def test_audio():
    print("=" * 60)
    print("  Test de Audio - TikTok Live Bot")
    print("=" * 60)
    print()
    
    # Inicializar pygame
    print("🎮 Inicializando pygame...")
    pygame.init()
    pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
    print("  ✓ Pygame inicializado")
    
    # Cargar AudioManager
    print("\n🔊 Cargando AudioManager...")
    from src.asset_manager import AudioManager
    audio_manager = AudioManager()
    print(f"  ✓ AudioManager cargado")
    print(f"  ✓ Sonidos cargados: {audio_manager.loaded_sounds_count}")
    print(f"  ✓ Sonidos en cache: {list(audio_manager._sound_cache.keys())}")
    
    if audio_manager.missing_sounds:
        print(f"  ⚠ Sonidos faltantes: {audio_manager.missing_sounds}")
    
    # Test BGM
    print("\n🎵 Probando BGM...")
    audio_manager.play_bgm()
    if audio_manager.is_bgm_playing():
        print("  ✓ BGM reproduciéndose")
        print("  ⏸  Esperando 2 segundos...")
        time.sleep(2)
    else:
        print("  ✗ BGM NO se está reproduciendo")
    
    # Test small gift
    print("\n🎁 Probando SMALL GIFT...")
    print("  ▶ Reproduciendo small_gift...")
    audio_manager.play_sfx('small')
    print("  ⏸  Esperando 2 segundos...")
    time.sleep(2)
    
    # Test big gift
    print("\n🎁 Probando BIG GIFT...")
    print("  ▶ Reproduciendo big_gift...")
    audio_manager.play_sfx('big')
    print("  ⏸  Esperando 2 segundos...")
    time.sleep(2)
    
    # Test victory
    print("\n🏆 Probando VICTORY...")
    print("  ▶ Reproduciendo victory...")
    audio_manager.play_sfx('victory')
    print("  ⏸  Esperando 2 segundos...")
    time.sleep(2)
    
    # Test con diamantes
    print("\n💎 Probando con valores de diamantes...")
    
    test_cases = [
        ("Rosa", 1, "small"),
        ("Perfume", 10, "big"),
        ("TikTok", 50, "big"),
        ("Universe", 1000, "big"),
    ]
    
    for gift_name, diamonds, expected in test_cases:
        print(f"\n  🎁 {gift_name} ({diamonds}💎) - Esperado: {expected}")
        audio_manager.play_sfx('auto', gift_name, diamonds)
        time.sleep(1.5)
    
    print("\n" + "=" * 60)
    print("✅ Test completado")
    print("\nSi no escuchaste algún sonido, verifica:")
    print("  1. Volumen del sistema")
    print("  2. Archivos en assets/audio/")
    print("  3. Permisos de audio en macOS")
    print("=" * 60)
    
    # Limpiar
    audio_manager.stop_bgm()
    pygame.quit()

if __name__ == "__main__":
    test_audio()