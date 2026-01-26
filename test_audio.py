#!/usr/bin/env python3
"""
Audio test script for TikTok Live Racing Game.

Tests all audio functionality including:
- Background music (BGM)
- Sound effects (SFX)
- Event-specific sounds (vote, combo, final stretch, victory)
- TTS preparation
"""

import sys
import os
sys.path.insert(0, 'src')

import pygame
import time


def test_audio():
    """Test all audio functionality."""
    print("=" * 60)
    print("  Audio Test Suite - TikTok Live Racing")
    print("=" * 60)
    print()
    
    # Initialize pygame
    print("🎮 Initializing pygame...")
    pygame.init()
    pygame.display.set_mode((200, 100))  # Small window for audio test
    print("  ✓ Pygame initialized")
    
    # Import AudioManager from new module
    print("\n🔊 Loading AudioManager...")
    from src.audio_manager import AudioManager, SoundType
    audio_manager = AudioManager()
    
    print(f"  ✓ AudioManager loaded")
    print(f"  ✓ Sounds loaded: {audio_manager.loaded_count}")
    print(f"  ✓ Initialized: {audio_manager.is_initialized}")
    
    if audio_manager.missing_sounds:
        print(f"  ⚠ Missing sounds: {[s.name for s in audio_manager.missing_sounds]}")
    
    # Test BGM
    print("\n" + "=" * 40)
    print("🎵 Testing Background Music (BGM)")
    print("=" * 40)
    
    audio_manager.play_bgm(fade_in_ms=500)
    if audio_manager.is_bgm_playing():
        print("  ✓ BGM playing")
        print("  ⏳ Playing for 3 seconds...")
        time.sleep(3)
    else:
        print("  ✗ BGM failed to play")
    
    # Test BGM ducking
    print("\n  Testing BGM ducking (volume reduction)...")
    audio_manager.duck_bgm(duration=2.0, duck_volume=0.3)
    print("  ✓ BGM ducked to 30%")
    time.sleep(2.5)
    print("  ✓ BGM restored")
    
    # Test Gift Sounds
    print("\n" + "=" * 40)
    print("🎁 Testing Gift Sounds")
    print("=" * 40)
    
    test_gifts = [
        ("Rosa", 1, "small"),
        ("Perfume", 10, "big"),
        ("TikTok", 50, "big"),
        ("Universe", 1000, "big"),
    ]
    
    for gift_name, diamonds, expected in test_gifts:
        print(f"\n  🎁 {gift_name} ({diamonds}💎) - Expected: {expected}")
        audio_manager.play_gift_sound(gift_name=gift_name, diamond_value=diamonds)
        time.sleep(1.0)
    
    # Test Vote Sound
    print("\n" + "=" * 40)
    print("🗳️ Testing Vote Sound")
    print("=" * 40)
    
    print("  Playing vote click sound...")
    audio_manager.play_vote_sound()
    time.sleep(1.0)
    
    # Test Combo Fire Sounds
    print("\n" + "=" * 40)
    print("🔥 Testing Combo Fire Sounds (Pitch Escalation)")
    print("=" * 40)
    
    for level in range(1, 6):
        print(f"\n  🔥 Combo Level {level}")
        audio_manager.play_combo_fire_sound(combo_level=level)
        time.sleep(0.8)
    
    # Test Final Stretch Sound
    print("\n" + "=" * 40)
    print("🏁 Testing Final Stretch Sound")
    print("=" * 40)
    
    print("  Playing final stretch siren...")
    audio_manager.play_final_stretch_sound()
    time.sleep(3.0)
    
    # Test Victory Sound
    print("\n" + "=" * 40)
    print("🏆 Testing Victory Sound")
    print("=" * 40)
    
    print("  Playing victory fanfare for Argentina...")
    audio_manager.play_victory_sound(winner_country="Argentina")
    time.sleep(4.0)
    
    # Test Freeze Sound
    print("\n" + "=" * 40)
    print("❄️ Testing Freeze Sound")
    print("=" * 40)
    
    print("  Playing freeze effect...")
    audio_manager.play_freeze_sound()
    time.sleep(1.5)
    
    # Test Direct SFX Play
    print("\n" + "=" * 40)
    print("🔊 Testing Direct SFX Play")
    print("=" * 40)
    
    available_sounds = [
        SoundType.SMALL_GIFT,
        SoundType.BIG_GIFT,
        SoundType.VICTORY,
        SoundType.FREEZE,
    ]
    
    for sound_type in available_sounds:
        if sound_type not in audio_manager.missing_sounds:
            print(f"  ▶ Playing {sound_type.name}...")
            audio_manager.play_sfx(sound_type)
            time.sleep(1.0)
    
    # Summary
    print("\n" + "=" * 60)
    print("✅ Audio Test Complete")
    print("=" * 60)
    print("\nIf you didn't hear some sounds, check:")
    print("  1. System volume level")
    print("  2. Audio files in assets/audio/")
    print("  3. Audio permissions (especially on macOS)")
    print("\nMissing sound files (optional):")
    for sound in audio_manager.missing_sounds:
        config = AudioManager.SOUND_PATHS.get(sound)
        if config:
            print(f"  - {config.file_path}")
    print("=" * 60)
    
    # Cleanup
    audio_manager.stop_bgm()
    audio_manager.stop_all_sfx()
    pygame.quit()


def test_tts():
    """Test TTS functionality."""
    print("\n" + "=" * 60)
    print("🎤 Testing Text-to-Speech (TTS)")
    print("=" * 60)
    
    from src.audio_manager import create_tts_provider, AudioManager
    
    # Try to create a TTS provider
    provider = create_tts_provider("auto")
    
    if provider and provider.is_available():
        print(f"  ✓ TTS Provider: {type(provider).__name__}")
        
        # Test TTS
        pygame.init()
        pygame.mixer.init()
        
        audio_manager = AudioManager()
        audio_manager.set_tts_callback(provider.speak)
        
        print("  🎤 Announcing winner...")
        audio_manager.announce_custom("¡Argentina cruza la meta!")
        time.sleep(3)
        
        pygame.quit()
    else:
        print("  ⚠ No TTS provider available")
        print("  Install pyttsx3 or gTTS for TTS support:")
        print("    pip install pyttsx3")
        print("    pip install gTTS")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--tts":
        test_tts()
    else:
        test_audio()
        
        # Ask about TTS test
        print("\n¿Probar TTS (Text-to-Speech)? [y/N]: ", end="")
        try:
            response = input().strip().lower()
            if response == 'y':
                test_tts()
        except EOFError:
            pass
