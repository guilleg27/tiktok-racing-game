"""
Audio Manager - Complete audio system for SFX and background music.

Handles sound effects, background music, and text-to-speech preparation
with platform compatibility (Windows/macOS/Linux) and efficient caching.
"""

import logging
import os
import platform
import threading
from dataclasses import dataclass
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Dict, List, Optional

import pygame

from .config import (
    GIFT_DIAMOND_VALUES,
    VOL_BGM,
    VOL_SFX,
)
from .resources import resource_path

logger = logging.getLogger(__name__)


class SoundType(Enum):
    """Types of sound effects available in the game."""
    # Background music
    BGM = auto()
    
    # Basic SFX
    SMALL_GIFT = auto()
    BIG_GIFT = auto()
    
    # Event-based SFX
    VOTE = auto()           # Click/coin sound for votes/gifts
    COMBO_FIRE = auto()     # Ignition/fire sound for combos
    FINAL_STRETCH = auto()  # Race siren or sonic boom
    VICTORY = auto()        # Trumpets, applause, confetti explosion
    
    # Utility SFX
    FREEZE = auto()         # Freeze effect sound
    COUNTDOWN = auto()      # Race countdown beeps
    
    # TTS placeholder
    TTS_WINNER = auto()     # Voice announcement for winners


@dataclass
class SoundConfig:
    """Configuration for a sound effect."""
    file_path: str
    volume: float = 0.5
    allow_overlap: bool = True
    max_instances: int = 3
    pitch_variation: float = 0.0  # Random pitch variation (0.0 = none)


class AudioManager:
    """
    Manages sound effects (SFX) and background music for the game.
    
    Features:
    - Pre-loads all sounds at initialization (caching)
    - Platform-specific audio driver configuration
    - Dynamic pitch control for combo effects
    - Prepared structure for TTS integration
    - Thread-safe operations
    
    Attributes:
        _initialized: Whether pygame.mixer was successfully initialized
        _sound_cache: Dictionary of loaded Sound objects
        _bgm_channel: Dedicated channel for background music
        _combo_level: Current combo level (affects pitch)
    """
    
    # Sound file paths (relative to project root)
    SOUND_PATHS: Dict[SoundType, SoundConfig] = {
        SoundType.BGM: SoundConfig(
            file_path=os.path.join("assets", "audio", "bgm.wav"),
            volume=VOL_BGM,
            allow_overlap=False,
            max_instances=1
        ),
        SoundType.SMALL_GIFT: SoundConfig(
            file_path=os.path.join("assets", "audio", "small_gift.wav"),
            volume=VOL_SFX,
            pitch_variation=0.1
        ),
        SoundType.BIG_GIFT: SoundConfig(
            file_path=os.path.join("assets", "audio", "big_gift.wav"),
            volume=VOL_SFX,
            pitch_variation=0.05
        ),
        SoundType.VOTE: SoundConfig(
            file_path=os.path.join("assets", "audio", "vote.wav"),
            volume=VOL_SFX * 0.8,
            max_instances=5,
            pitch_variation=0.15
        ),
        SoundType.COMBO_FIRE: SoundConfig(
            file_path=os.path.join("assets", "audio", "combo_fire.wav"),
            volume=VOL_SFX * 1.2,
            max_instances=2
        ),
        SoundType.FINAL_STRETCH: SoundConfig(
            file_path=os.path.join("assets", "audio", "final_stretch.wav"),
            volume=VOL_SFX * 1.3,
            allow_overlap=False,
            max_instances=1
        ),
        SoundType.VICTORY: SoundConfig(
            file_path=os.path.join("assets", "audio", "victory.wav"),
            volume=VOL_SFX * 1.2,
            allow_overlap=False,
            max_instances=1
        ),
        SoundType.FREEZE: SoundConfig(
            file_path=os.path.join("assets", "audio", "freeze_sfx.wav"),
            volume=VOL_SFX
        ),
        SoundType.COUNTDOWN: SoundConfig(
            file_path=os.path.join("assets", "audio", "countdown.wav"),
            volume=VOL_SFX * 0.9,
            max_instances=1
        ),
    }
    
    # Combo levels for pitch scaling (ON FIRE effect)
    COMBO_PITCH_LEVELS = {
        0: 1.0,    # Normal
        1: 1.05,   # Level 1: slightly higher
        2: 1.12,   # Level 2: noticeably higher
        3: 1.20,   # Level 3: ON FIRE - high pitch
        4: 1.30,   # Level 4: SUPER FIRE
        5: 1.40,   # Level 5: ULTRA FIRE (max)
    }
    
    def __init__(self, assets_path: str = "assets/audio"):
        """
        Initialize the Audio Manager.
        
        Configures pygame.mixer with platform-specific settings,
        pre-loads all sound files into cache for zero-latency playback.
        
        Args:
            assets_path: Relative path to audio assets directory
        """
        resolved_path = resource_path(assets_path)
        self.assets_path = Path(resolved_path)
        
        self._sound_cache: Dict[SoundType, pygame.mixer.Sound] = {}
        self._missing_sounds: set = set()
        self._bgm_channel: Optional[pygame.mixer.Channel] = None
        self._initialized = False
        
        # Combo tracking for pitch effects
        self._combo_level: int = 0
        self._last_combo_country: Optional[str] = None
        
        # TTS callback hook (to be set externally)
        self._tts_callback: Optional[Callable[[str], None]] = None
        
        # Thread lock for safe concurrent access
        self._lock = threading.Lock()
        
        # Active sound instances tracker (for max_instances limit)
        self._active_sounds: Dict[SoundType, List[pygame.mixer.Channel]] = {}
        
        # Initialize audio system
        self._init_mixer()
        self._preload_sounds()
        
        logger.info(
            f"🔊 AudioManager initialized: {len(self._sound_cache)} sounds cached, "
            f"{len(self._missing_sounds)} missing"
        )
    
    def _init_mixer(self) -> None:
        """
        Initialize pygame.mixer with platform-optimized settings.
        
        Uses DirectSound on Windows to avoid WASAPI exclusive mode conflicts.
        Uses CoreAudio on macOS with lower buffer for minimal latency.
        
        Raises:
            Logs error but doesn't raise - game continues without audio.
        """
        system = platform.system()
        
        try:
            # Platform-specific configuration
            if system == "Windows":
                # Windows: DirectSound driver (avoids WASAPI exclusivity issues)
                os.environ.setdefault('SDL_AUDIODRIVER', 'directsound')
                buffer_size = 1024  # Larger buffer for stability
                frequency = 44100
            elif system == "Darwin":  # macOS
                # macOS: CoreAudio with small buffer for low latency
                buffer_size = 512
                frequency = 44100
            else:  # Linux
                # Linux: ALSA or PulseAudio with medium buffer
                buffer_size = 768
                frequency = 44100
            
            # Pre-initialize with optimized parameters
            pygame.mixer.pre_init(
                frequency=frequency,
                size=-16,           # 16-bit signed (most compatible)
                channels=2,         # Stereo
                buffer=buffer_size
            )
            
            pygame.mixer.init()
            
            # Allocate channels for concurrent sound playback
            pygame.mixer.set_num_channels(16)
            
            # Reserve channel 0 for BGM
            pygame.mixer.set_reserved(1)
            
            self._initialized = True
            logger.info(
                f"🔊 Audio mixer initialized: {system}, "
                f"freq={frequency}Hz, buffer={buffer_size}"
            )
            
        except pygame.error as e:
            logger.warning(f"Primary audio init failed: {e}. Trying fallback...")
            self._fallback_init()
            
        except Exception as e:
            logger.error(f"Audio initialization failed: {e}")
            self._initialized = False
    
    def _fallback_init(self) -> None:
        """Fallback audio initialization with default settings."""
        try:
            pygame.mixer.quit()
            pygame.mixer.init()
            pygame.mixer.set_num_channels(8)
            self._initialized = True
            logger.info("🔊 Audio initialized with fallback settings")
        except Exception as e:
            logger.error(f"Fallback audio init failed: {e}")
            self._initialized = False
    
    def _preload_sounds(self) -> None:
        """
        Pre-load all defined sounds into cache.
        
        Loads each sound file once at startup to eliminate
        disk I/O latency during gameplay.
        """
        if not self._initialized:
            logger.warning("Audio not initialized, skipping preload")
            return
        
        for sound_type, config in self.SOUND_PATHS.items():
            try:
                full_path = Path(resource_path(config.file_path))
                
                if not full_path.exists():
                    # Don't log warning for optional sounds (vote, combo, etc.)
                    if sound_type in [SoundType.VOTE, SoundType.COMBO_FIRE, 
                                      SoundType.FINAL_STRETCH, SoundType.COUNTDOWN]:
                        logger.debug(f"Optional audio not found: {config.file_path}")
                    else:
                        logger.warning(f"Audio file not found: {config.file_path}")
                    self._missing_sounds.add(sound_type)
                    continue
                
                # Load and cache sound
                sound = pygame.mixer.Sound(str(full_path))
                sound.set_volume(config.volume)
                self._sound_cache[sound_type] = sound
                
                # Initialize active sounds tracker
                self._active_sounds[sound_type] = []
                
                logger.debug(f"Loaded audio: {sound_type.name} from {config.file_path}")
                
            except Exception as e:
                logger.error(f"Failed to load {config.file_path}: {e}")
                self._missing_sounds.add(sound_type)
        
        logger.info(
            f"🔊 Preloaded {len(self._sound_cache)}/{len(self.SOUND_PATHS)} audio files"
        )
    
    # ========================================================================
    # BACKGROUND MUSIC
    # ========================================================================
    
    def play_bgm(self, fade_in_ms: int = 1000) -> None:
        """
        Start background music with optional fade-in.
        
        Args:
            fade_in_ms: Fade-in duration in milliseconds (0 for instant)
        """
        if not self._initialized:
            return
        
        if SoundType.BGM not in self._sound_cache:
            logger.debug("BGM not available")
            return
        
        with self._lock:
            try:
                # Stop current BGM if playing
                self.stop_bgm()
                
                # Get reserved channel 0 for BGM
                self._bgm_channel = pygame.mixer.Channel(0)
                
                bgm_sound = self._sound_cache[SoundType.BGM]
                bgm_sound.set_volume(VOL_BGM)
                
                if fade_in_ms > 0:
                    self._bgm_channel.play(bgm_sound, loops=-1, fade_ms=fade_in_ms)
                else:
                    self._bgm_channel.play(bgm_sound, loops=-1)
                
                logger.info("🎵 Background music started")
                
            except Exception as e:
                logger.error(f"Failed to play BGM: {e}")
    
    def stop_bgm(self, fade_out_ms: int = 500) -> None:
        """
        Stop background music with optional fade-out.
        
        Args:
            fade_out_ms: Fade-out duration in milliseconds (0 for instant)
        """
        if self._bgm_channel and self._bgm_channel.get_busy():
            if fade_out_ms > 0:
                self._bgm_channel.fadeout(fade_out_ms)
            else:
                self._bgm_channel.stop()
            logger.info("🎵 Background music stopped")
    
    def pause_bgm(self) -> None:
        """Pause background music (can be resumed)."""
        if self._bgm_channel:
            self._bgm_channel.pause()
    
    def resume_bgm(self) -> None:
        """Resume paused background music."""
        if self._bgm_channel:
            self._bgm_channel.unpause()
    
    def set_bgm_volume(self, volume: float) -> None:
        """
        Set background music volume.
        
        Args:
            volume: Volume level (0.0 to 1.0)
        """
        if SoundType.BGM in self._sound_cache:
            self._sound_cache[SoundType.BGM].set_volume(max(0.0, min(1.0, volume)))
    
    def duck_bgm(self, duration: float = 2.0, duck_volume: float = 0.3) -> None:
        """
        Temporarily lower BGM volume (for announcements/victory).
        
        Args:
            duration: How long to keep volume lowered (seconds)
            duck_volume: Volume multiplier during duck (0.0-1.0)
        """
        if SoundType.BGM not in self._sound_cache:
            return
        
        bgm = self._sound_cache[SoundType.BGM]
        original_volume = VOL_BGM
        
        # Lower volume
        bgm.set_volume(original_volume * duck_volume)
        
        # Schedule restoration in a separate thread
        def restore_volume():
            import time
            time.sleep(duration)
            try:
                if SoundType.BGM in self._sound_cache:
                    self._sound_cache[SoundType.BGM].set_volume(original_volume)
            except Exception:
                pass
        
        threading.Thread(target=restore_volume, daemon=True).start()
    
    def is_bgm_playing(self) -> bool:
        """Check if background music is currently playing."""
        return bool(self._bgm_channel and self._bgm_channel.get_busy())
    
    # ========================================================================
    # SOUND EFFECTS
    # ========================================================================
    
    def play_sfx(
        self,
        sound_type: SoundType,
        pitch: float = 1.0,
        volume_mult: float = 1.0
    ) -> Optional[pygame.mixer.Channel]:
        """
        Play a sound effect.
        
        Args:
            sound_type: Type of sound to play
            pitch: Pitch multiplier (1.0 = normal, >1.0 = higher)
            volume_mult: Volume multiplier (1.0 = config volume)
            
        Returns:
            The channel playing the sound, or None if failed
        """
        if not self._initialized:
            return None
        
        if sound_type not in self._sound_cache:
            if sound_type not in self._missing_sounds:
                logger.debug(f"Sound not available: {sound_type.name}")
            return None
        
        config = self.SOUND_PATHS.get(sound_type)
        if not config:
            return None
        
        with self._lock:
            try:
                # Check max instances limit
                self._cleanup_finished_channels(sound_type)
                active_count = len(self._active_sounds.get(sound_type, []))
                
                if active_count >= config.max_instances and not config.allow_overlap:
                    logger.debug(f"Max instances reached for {sound_type.name}")
                    return None
                
                sound = self._sound_cache[sound_type]
                
                # Apply volume
                final_volume = config.volume * volume_mult
                sound.set_volume(max(0.0, min(1.0, final_volume)))
                
                # Note: pygame.mixer doesn't support pitch directly
                # For pitch variation, we'd need to use numpy to resample
                # For now, we'll just play the sound normally
                # TODO: Implement pitch shifting using numpy/scipy
                
                channel = sound.play()
                
                if channel:
                    self._active_sounds.setdefault(sound_type, []).append(channel)
                    logger.debug(f"🔊 Playing SFX: {sound_type.name}")
                
                return channel
                
            except Exception as e:
                logger.error(f"Failed to play SFX {sound_type.name}: {e}")
                return None
    
    def _cleanup_finished_channels(self, sound_type: SoundType) -> None:
        """Remove finished channels from active tracking."""
        if sound_type in self._active_sounds:
            self._active_sounds[sound_type] = [
                ch for ch in self._active_sounds[sound_type]
                if ch.get_busy()
            ]
    
    # ========================================================================
    # EVENT-SPECIFIC SOUND METHODS
    # ========================================================================
    
    def play_vote_sound(self) -> None:
        """
        Play vote/gift click sound.
        
        Plays a metallic click or coin sound when a user votes or sends a gift.
        Falls back to small_gift sound if vote sound is not available.
        """
        if SoundType.VOTE in self._sound_cache:
            self.play_sfx(SoundType.VOTE)
        else:
            # Fallback to small gift sound
            self.play_sfx(SoundType.SMALL_GIFT)
    
    def play_combo_fire_sound(self, combo_level: int = 1) -> None:
        """
        Play combo/ON FIRE ignition sound with pitch based on combo level.
        
        The pitch increases with combo level to create escalating intensity.
        
        Args:
            combo_level: Current combo level (1-5+)
        """
        # Clamp combo level to valid range
        level = max(0, min(5, combo_level))
        pitch = self.COMBO_PITCH_LEVELS.get(level, 1.0)
        
        self._combo_level = level
        
        if SoundType.COMBO_FIRE in self._sound_cache:
            self.play_sfx(SoundType.COMBO_FIRE, pitch=pitch)
        else:
            # Fallback: play big gift with higher volume
            self.play_sfx(SoundType.BIG_GIFT, volume_mult=1.0 + (level * 0.1))
        
        logger.debug(f"🔥 Combo fire sound: level {level}, pitch {pitch}")
    
    def play_final_stretch_sound(self) -> None:
        """
        Play final stretch siren/sonic boom sound.
        
        Played when a racer is close to the finish line.
        Also ducks the BGM for dramatic effect.
        """
        if SoundType.FINAL_STRETCH in self._sound_cache:
            self.play_sfx(SoundType.FINAL_STRETCH)
            self.duck_bgm(duration=3.0, duck_volume=0.4)
        else:
            # Fallback: play victory sound at lower volume
            self.play_sfx(SoundType.VICTORY, volume_mult=0.5)
    
    def play_victory_sound(self, winner_country: Optional[str] = None) -> None:
        """
        Play victory celebration sound (trumpets, applause, confetti).
        
        Includes TTS announcement if callback is set and country is provided.
        
        Args:
            winner_country: Name of the winning country for TTS announcement
        """
        # Duck BGM for victory fanfare
        self.duck_bgm(duration=5.0, duck_volume=0.2)
        
        # Play victory sound
        self.play_sfx(SoundType.VICTORY)
        
        # Trigger TTS if available
        if winner_country:
            if self._tts_callback:
                self._announce_winner(winner_country)
                logger.info(f"🎤 TTS announcement triggered for: {winner_country}")
            else:
                logger.debug(f"🎤 TTS not available (callback not set) for: {winner_country}")
        
        logger.info(f"🏆 Victory sound played for: {winner_country or 'unknown'}")
    
    def play_gift_sound(
        self,
        gift_name: Optional[str] = None,
        diamond_value: Optional[int] = None
    ) -> None:
        """
        Play appropriate gift sound based on gift value.
        
        Args:
            gift_name: Name of the gift (for diamond value lookup)
            diamond_value: Direct diamond value (overrides lookup)
        """
        # Determine diamond value
        if diamond_value is None and gift_name:
            diamond_value = GIFT_DIAMOND_VALUES.get(gift_name, 1)
        
        diamond_value = diamond_value or 1
        
        # Choose sound based on value
        if diamond_value >= 10:
            self.play_sfx(SoundType.BIG_GIFT)
        else:
            self.play_sfx(SoundType.SMALL_GIFT)
        
        logger.debug(f"🎁 Gift sound: {gift_name} ({diamond_value}💎)")
    
    def play_freeze_sound(self) -> None:
        """Play freeze effect sound."""
        self.play_sfx(SoundType.FREEZE)
    
    def play_countdown_beep(self, count: int = 3) -> None:
        """
        Play countdown beep sound.
        
        Args:
            count: Current countdown number (affects pitch)
        """
        # Higher pitch for lower numbers (more urgent)
        pitch = 1.0 + ((3 - count) * 0.1)
        self.play_sfx(SoundType.COUNTDOWN, pitch=pitch)
    
    # ========================================================================
    # TEXT-TO-SPEECH (TTS) INTEGRATION
    # ========================================================================
    
    def set_tts_callback(self, callback: Callable[[str], None]) -> None:
        """
        Set the TTS callback function for voice announcements.
        
        The callback will receive announcement text and should handle
        the actual TTS synthesis and playback.
        
        Args:
            callback: Function that takes announcement text as parameter
            
        Example:
            def my_tts_callback(text):
                # Use gTTS, pyttsx3, or cloud API
                engine = pyttsx3.init()
                engine.say(text)
                engine.runAndWait()
            
            audio_manager.set_tts_callback(my_tts_callback)
        """
        self._tts_callback = callback
        logger.info("🎤 TTS callback registered")
    
    def _announce_winner(self, country: str) -> None:
        """
        Announce the race winner using TTS.
        
        Args:
            country: Name of the winning country
        """
        if not self._tts_callback:
            logger.debug("TTS callback not set, skipping announcement")
            return
        
        # Generate announcement text (English)
        import random
        announcements = [
            f"{country} crosses the finish line!",
            f"{country} wins the race!",
            f"Victory for {country}!",
            f"{country} takes the checkered flag!",
            f"And the winner is {country}!",
        ]
        announcement = random.choice(announcements)
        
        # Run TTS in separate thread to avoid blocking
        def tts_thread():
            try:
                self._tts_callback(announcement)
            except Exception as e:
                logger.error(f"TTS announcement failed: {e}")
        
        threading.Thread(target=tts_thread, daemon=True).start()
        logger.info(f"🎤 TTS announcement triggered: {announcement}")
    
    def announce_combo(self, country: str, combo_level: int) -> None:
        """
        Announce combo achievement.
        
        Args:
            country: Country with combo
            combo_level: Combo level (1-5)
        """
        if not self._tts_callback:
            return
        
        import random
        
        if combo_level >= 5:
            announcements = [
                f"{country} is on fire!",
                f"{country} is unstoppable!",
                f"Amazing combo from {country}!",
            ]
        elif combo_level >= 3:
            announcements = [
                f"{country} is heating up!",
                f"Great combo from {country}!",
                f"{country} is gaining momentum!",
            ]
        else:
            announcements = [
                f"{country} combo!",
                f"Nice combo from {country}!",
            ]
        
        announcement = random.choice(announcements)
        
        def tts_thread():
            try:
                self._tts_callback(announcement)
            except Exception as e:
                logger.error(f"TTS combo announcement failed: {e}")
        
        threading.Thread(target=tts_thread, daemon=True).start()
    
    def announce_final_stretch(self, leader: str) -> None:
        """
        Announce final stretch.
        
        Args:
            leader: Leading country
        """
        if not self._tts_callback:
            return
        
        import random
        announcements = [
            f"Final stretch! {leader} is in the lead!",
            f"We're in the final stretch! {leader} leads the way!",
            f"Final lap! {leader} is out front!",
            f"Here comes the finish line! {leader} is ahead!",
        ]
        announcement = random.choice(announcements)
        
        def tts_thread():
            try:
                self._tts_callback(announcement)
            except Exception as e:
                logger.error(f"TTS final stretch announcement failed: {e}")
        
        threading.Thread(target=tts_thread, daemon=True).start()
    
    def announce_overtake(self, country: str, overtaken: str) -> None:
        """
        Announce an overtake.
        
        Args:
            country: Country that overtook
            overtaken: Country that was overtaken
        """
        if not self._tts_callback:
            return
        
        import random
        announcements = [
            f"{country} overtakes {overtaken}!",
            f"{country} passes {overtaken}!",
            f"{country} moves ahead of {overtaken}!",
        ]
        announcement = random.choice(announcements)
        
        def tts_thread():
            try:
                self._tts_callback(announcement)
            except Exception as e:
                logger.error(f"TTS overtake announcement failed: {e}")
        
        threading.Thread(target=tts_thread, daemon=True).start()
    
    def announce_close_race(self, leader: str, chaser: str) -> None:
        """
        Announce a close race between two countries.
        
        Args:
            leader: Leading country
            chaser: Chasing country
        """
        if not self._tts_callback:
            return
        
        import random
        announcements = [
            f"Close race! {leader} leads {chaser} by a hair!",
            f"It's neck and neck! {leader} and {chaser} are battling!",
            f"Tight race! {leader} just ahead of {chaser}!",
        ]
        announcement = random.choice(announcements)
        
        def tts_thread():
            try:
                self._tts_callback(announcement)
            except Exception as e:
                logger.error(f"TTS close race announcement failed: {e}")
        
        threading.Thread(target=tts_thread, daemon=True).start()
    
    def announce_custom(self, text: str) -> None:
        """
        Make a custom TTS announcement.
        
        Args:
            text: Text to announce
        """
        if self._tts_callback:
            threading.Thread(
                target=self._tts_callback,
                args=(text,),
                daemon=True
            ).start()
    
    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    def stop_all_sfx(self) -> None:
        """Stop all currently playing sound effects (except BGM)."""
        # Stop all channels except reserved BGM channel
        for i in range(1, pygame.mixer.get_num_channels()):
            try:
                channel = pygame.mixer.Channel(i)
                if channel.get_busy():
                    channel.stop()
            except Exception:
                pass
        
        self._active_sounds.clear()
    
    def set_master_volume(self, volume: float) -> None:
        """
        Set master volume for all sounds.
        
        Args:
            volume: Master volume (0.0 to 1.0)
        """
        volume = max(0.0, min(1.0, volume))
        
        for sound_type, sound in self._sound_cache.items():
            config = self.SOUND_PATHS.get(sound_type)
            if config:
                sound.set_volume(config.volume * volume)
    
    def reload_sounds(self) -> None:
        """Reload all sounds from disk (hot-reload for development)."""
        with self._lock:
            self._sound_cache.clear()
            self._missing_sounds.clear()
            self._active_sounds.clear()
            self._preload_sounds()
    
    @property
    def loaded_count(self) -> int:
        """Number of successfully loaded sounds."""
        return len(self._sound_cache)
    
    @property
    def missing_sounds(self) -> set:
        """Set of sounds that failed to load."""
        return self._missing_sounds.copy()
    
    @property
    def is_initialized(self) -> bool:
        """Whether audio system is initialized and ready."""
        return self._initialized


# =============================================================================
# TTS PROVIDER IMPLEMENTATIONS (Optional - requires additional packages)
# =============================================================================

class TTSProvider:
    """
    Base class for Text-to-Speech providers.
    
    Subclass this to implement different TTS backends:
    - pyttsx3 (offline, cross-platform)
    - gTTS (Google TTS, requires internet)
    - Azure/AWS/GCP TTS APIs
    """
    
    def speak(self, text: str) -> None:
        """
        Speak the given text.
        
        Args:
            text: Text to speak
        """
        raise NotImplementedError("Subclasses must implement speak()")
    
    def is_available(self) -> bool:
        """Check if this TTS provider is available."""
        return False


class Pyttsx3Provider(TTSProvider):
    """
    Offline TTS using pyttsx3.
    
    Requires: pip install pyttsx3
    Supports multiple system voices on macOS/Windows.
    """
    
    def __init__(self, rate: int = 150, voice_index: int = 0, voice_id: Optional[str] = None):
        """
        Initialize pyttsx3 TTS.
        
        Args:
            rate: Speech rate (words per minute)
            voice_index: Index of voice to use (0 = default)
            voice_id: Specific voice ID to use (overrides voice_index)
        """
        self._engine = None
        self._rate = rate
        self._voice_index = voice_index
        self._voice_id = voice_id
        self._available_voices = []
        self._init_engine()
    
    def _init_engine(self) -> None:
        """Initialize the TTS engine."""
        try:
            import pyttsx3
            self._engine = pyttsx3.init()
            self._engine.setProperty('rate', self._rate)
            
            # Get available voices
            voices = self._engine.getProperty('voices')
            if voices:
                self._available_voices = [v.id for v in voices]
                logger.debug(f"🎤 Found {len(self._available_voices)} voices available")
            
            # Set voice (by ID if provided, otherwise by index)
            if self._voice_id and self._voice_id in self._available_voices:
                self._engine.setProperty('voice', self._voice_id)
                logger.info(f"🎤 pyttsx3 TTS initialized with voice: {self._voice_id}")
            elif voices and len(voices) > self._voice_index:
                self._engine.setProperty('voice', voices[self._voice_index].id)
                logger.info(f"🎤 pyttsx3 TTS initialized with voice index {self._voice_index}")
            else:
                logger.info("🎤 pyttsx3 TTS initialized with default voice")
            
        except ImportError:
            logger.debug("pyttsx3 not installed, TTS unavailable")
            self._engine = None
        except Exception as e:
            logger.error(f"pyttsx3 init failed: {e}")
            self._engine = None
    
    def list_voices(self) -> List[str]:
        """
        List all available voices.
        
        Returns:
            List of voice IDs/names
        """
        return self._available_voices.copy()
    
    def set_voice(self, voice_id: str) -> bool:
        """
        Change the voice to use.
        
        Args:
            voice_id: Voice ID from list_voices()
            
        Returns:
            True if voice was set successfully
        """
        if not self._engine:
            return False
        
        if voice_id in self._available_voices:
            self._engine.setProperty('voice', voice_id)
            self._voice_id = voice_id
            logger.info(f"🎤 Voice changed to: {voice_id}")
            return True
        else:
            logger.warning(f"🎤 Voice not found: {voice_id}")
            return False
    
    def speak(self, text: str) -> None:
        """Speak text using pyttsx3."""
        if self._engine:
            try:
                self._engine.say(text)
                self._engine.runAndWait()
            except Exception as e:
                logger.error(f"pyttsx3 speak failed: {e}")
    
    def is_available(self) -> bool:
        """Check if pyttsx3 is available."""
        return self._engine is not None


class GTTSProvider(TTSProvider):
    """
    Online TTS using Google Text-to-Speech (gTTS).
    
    Requires: pip install gTTS
    Note: Requires internet connection
    """
    
    def __init__(self, lang: str = "es", slow: bool = False):
        """
        Initialize gTTS.
        
        Args:
            lang: Language code (e.g., 'es' for Spanish, 'en' for English)
            slow: Whether to speak slowly
        """
        self._lang = lang
        self._slow = slow
        self._available = self._check_available()
    
    def _check_available(self) -> bool:
        """Check if gTTS is available."""
        try:
            import gtts
            return True
        except ImportError:
            logger.debug("gTTS not installed")
            return False
    
    def speak(self, text: str) -> None:
        """Speak text using gTTS."""
        if not self._available:
            return
        
        try:
            from gtts import gTTS
            import tempfile
            
            # Generate speech to temp file
            tts = gTTS(text=text, lang=self._lang, slow=self._slow)
            
            with tempfile.NamedTemporaryFile(suffix='.mp3', delete=False) as fp:
                tts.save(fp.name)
                
                # Play using pygame.mixer
                pygame.mixer.music.load(fp.name)
                pygame.mixer.music.play()
                
                # Wait for playback to finish
                while pygame.mixer.music.get_busy():
                    pygame.time.Clock().tick(10)
                
                # Cleanup
                import os
                os.unlink(fp.name)
                
        except Exception as e:
            logger.error(f"gTTS speak failed: {e}")
    
    def is_available(self) -> bool:
        """Check if gTTS is available."""
        return self._available


def create_tts_provider(provider_type: str = "auto") -> Optional[TTSProvider]:
    """
    Factory function to create a TTS provider.
    
    Args:
        provider_type: 'pyttsx3', 'gtts', or 'auto' (tries pyttsx3 first)
        
    Returns:
        TTSProvider instance or None if none available
    """
    if provider_type == "pyttsx3" or provider_type == "auto":
        provider = Pyttsx3Provider()
        if provider.is_available():
            return provider
    
    if provider_type == "gtts" or provider_type == "auto":
        provider = GTTSProvider()
        if provider.is_available():
            return provider
    
    logger.warning("No TTS provider available")
    return None
