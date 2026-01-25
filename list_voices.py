#!/usr/bin/env python3
"""
List and test available TTS voices.

Shows all available voices on your system and allows testing them.
"""

import sys
from typing import List

sys.path.insert(0, 'src')

from src.audio_manager import create_tts_provider, Pyttsx3Provider


def list_voices():
    """List all available TTS voices."""
    print("=" * 60)
    print("  Available TTS Voices")
    print("=" * 60)
    print()
    
    # Try pyttsx3
    provider = create_tts_provider("pyttsx3")
    
    if provider and isinstance(provider, Pyttsx3Provider):
        voices = provider.list_voices()
        
        if voices:
            print(f"Found {len(voices)} voices:\n")
            for i, voice_id in enumerate(voices):
                # Extract voice name (usually after last dot or slash)
                voice_name = voice_id.split('.')[-1] if '.' in voice_id else voice_id
                voice_name = voice_name.split('/')[-1] if '/' in voice_name else voice_name
                
                print(f"  [{i}] {voice_name}")
                print(f"      ID: {voice_id}")
                print()
            
            # Test voices
            print("=" * 60)
            print("Test voices? [y/N]: ", end="")
            try:
                response = input().strip().lower()
                if response == 'y':
                    test_voices(provider, voices)
            except EOFError:
                pass
        else:
            print("No voices found")
    else:
        print("pyttsx3 not available")
        print("Install with: pip install pyttsx3")


def test_voices(provider: Pyttsx3Provider, voices: List[str]):
    """Test each voice with a sample text."""
    test_text = "¡Argentina cruza la meta!"
    
    print("\n" + "=" * 60)
    print("Testing voices...")
    print("=" * 60)
    print()
    
    for i, voice_id in enumerate(voices):
        voice_name = voice_id.split('.')[-1] if '.' in voice_id else voice_id
        voice_name = voice_name.split('/')[-1] if '/' in voice_name else voice_name
        
        print(f"[{i}] Testing: {voice_name}")
        
        if provider.set_voice(voice_id):
            try:
                provider.speak(test_text)
                print("  ✓ Voice works")
            except Exception as e:
                print(f"  ✗ Error: {e}")
        else:
            print("  ✗ Failed to set voice")
        
        print()
        
        # Ask if continue
        if i < len(voices) - 1:
            print("Continue? [Y/n]: ", end="")
            try:
                response = input().strip().lower()
                if response == 'n':
                    break
            except EOFError:
                break
            print()


def show_voice_info():
    """Show detailed information about the current voice setup."""
    print("=" * 60)
    print("  TTS Voice Information")
    print("=" * 60)
    print()
    
    provider = create_tts_provider("pyttsx3")
    
    if provider and isinstance(provider, Pyttsx3Provider):
        voices = provider.list_voices()
        print(f"Total voices available: {len(voices)}")
        print()
        
        if voices:
            print("To use a specific voice, modify game_engine.py:")
            print()
            print("  tts_provider = Pyttsx3Provider(voice_index=0)  # Use first voice")
            print("  # OR")
            print(f"  tts_provider = Pyttsx3Provider(voice_id='{voices[0]}')  # Use specific voice")
            print()
    else:
        print("pyttsx3 not available")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--info":
        show_voice_info()
    else:
        list_voices()
