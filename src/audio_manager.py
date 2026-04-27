"""Shim: re-exports from core.audio_manager for backwards compatibility."""
from core.audio_manager import *  # noqa: F401, F403
from core.audio_manager import (  # noqa: F401
    AudioManager,
    SoundType,
    SoundConfig,
    TTSProvider,
    Pyttsx3Provider,
    GTTSProvider,
    create_tts_provider,
)
