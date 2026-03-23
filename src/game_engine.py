"""Game Engine - Consumer that renders TikTok events using Pygame + Pymunk."""

import asyncio
import collections
import logging
from typing import Optional, Dict
import math
import random
import time
import sys
from .cloud_manager import CloudManager
from dataclasses import dataclass, field

import pygame
import pymunk

# Try to import psutil for memory monitoring (optional)
try:
    import psutil
    import os
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

from .config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    FPS,
    MAX_MESSAGES,
    FONT_SIZE,
    FONT_SIZE_SMALL,
    LINE_HEIGHT,
    PADDING,
    COLOR_BACKGROUND,
    COLOR_TEXT_GIFT,
    COLOR_TEXT_SYSTEM,
    COLOR_STATUS_CONNECTED,
    COLOR_STATUS_DISCONNECTED,
    COLOR_STATUS_RECONNECTING,
    AUTO_STRESS_TEST,
    STRESS_TEST_INTERVAL,
    PHYSICS_FIXED_HZ,
    # Floating Text (NEW)
    COLOR_TEXT_POSITIVE,
    COLOR_TEXT_NEGATIVE,
    COLOR_TEXT_FREEZE,
    FLOATING_TEXT_SPEED,
    FLOATING_TEXT_LIFESPAN,
    FLOATING_TEXT_FONT_SIZE,
    LIKES_GOAL_INITIAL,
    LIKES_SIMULATED_PER_KEY,
    HYPE_THRESHOLD_CPM,
    HYPE_COOLDOWN_DURATION,
    HYPE_PHYSICS_MULTIPLIER,
    TTS_ENABLED,
    FOLLOWER_BANNER_LIFESPAN,
    FOLLOWER_BANNER_Y,
    FOLLOWER_BANNER_WIDTH,
    FOLLOWER_BANNER_HEIGHT,
    HYPE_TIMER_ENABLED,
    HYPE_TIMER_INTERVAL,
    HYPE_TIMER_URGENCY_SECS,
    HYPE_TIMER_HOST_CUE_SECS,
    MOTOGP_MODE,
    MOTOGP_LITE_PARTICLES,
    MOTOGP_GIFT_COUNTRY_MAP,
    HYPE_TIMER_LABEL,
    HYPE_DISASTER_TITLE,
)
from .events import EventType, ConnectionState, GameEvent
from .physics_world import PhysicsWorld
from .database import Database
from .asset_manager import AssetManager
from .audio_manager import AudioManager, SoundType, create_tts_provider, Pyttsx3Provider
from .camera import ScreenShaker
from .background_manager import BackgroundManager
from .hype_manager import HypeManager
from .notification_manager import NotificationManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level font cache — eliminates repeated pygame.font.SysFont() calls.
# Key: (name, size, bold). Built lazily on first request, O(1) thereafter.
# ---------------------------------------------------------------------------
_font_cache: dict[tuple, "pygame.font.Font"] = {}


def _get_font(name: Optional[str], size: int, bold: bool = False) -> "pygame.font.Font":
    """Return a cached font, constructing it only on the first request.

    Args:
        name: Font family name (e.g. "Arial"), or None for the default font.
        size: Point size.
        bold: Whether to request the bold variant.

    Returns:
        A pygame.font.Font ready to render text.
    """
    key = (name, size, bold)
    if key not in _font_cache:
        if name is None:
            _font_cache[key] = pygame.font.Font(None, size)
        else:
            try:
                _font_cache[key] = pygame.font.SysFont(name, size, bold=bold)
            except Exception:
                _font_cache[key] = pygame.font.Font(None, size)
    return _font_cache[key]


_mono_font_cache: dict[tuple, "pygame.font.Font"] = {}


def _get_mono_font(size: int, bold: bool = False) -> "pygame.font.Font":
    """Return a cached monospace font for hacker-aesthetic HUD elements."""
    key = (size, bold)
    if key not in _mono_font_cache:
        for name in ["Courier New", "Courier", "Consolas", "Monaco", "monospace"]:
            try:
                _mono_font_cache[key] = pygame.font.SysFont(name, size, bold=bold)
                break
            except Exception:
                continue
        else:
            _mono_font_cache[key] = pygame.font.Font(None, size)
    return _mono_font_cache[key]


@dataclass
class Particle:
    """
    Professional particle system for juice effects.
    Uses Pymunk vectors for physics consistency.
    """
    pos: pymunk.Vec2d  # Position vector
    vel: pymunk.Vec2d  # Velocity vector
    color: tuple[int, int, int]
    radius: float      # Current radius
    initial_radius: float  # Initial radius for scaling
    lifetime: float    # Remaining lifetime (0.0 = dead)
    max_lifetime: float  # Maximum lifetime


@dataclass
class TrailParticle:
    """
    Simple trail particle for flag movement trails.
    Smaller and simpler than explosion particles.
    """
    pos: tuple[float, float]  # (x, y) position
    color: tuple[int, int, int]  # RGB color
    alpha: int  # Opacity (0-255)
    size: float  # Current particle size
    initial_size: float  # Initial size (for organic fade)
    lifetime: float  # Remaining lifetime


@dataclass
class MotionTrailSegment:
    """
    Segment of a motion trail for 'ON FIRE' combo state.
    Creates a neon streak effect behind the flag.
    Uses pygame.draw.line for crisp edges.
    
    Attributes:
        x1, y1: Start position (older)
        x2, y2: End position (newer, closer to flag)
        color: RGB color from country flag colors
        alpha: Transparency (fades over time)
        thickness: Line thickness (thicker when ON FIRE)
    """
    x1: float
    y1: float
    x2: float
    y2: float
    color: tuple[int, int, int]
    alpha: float
    thickness: int


@dataclass
class ComboFlash:
    """
    Flash effect triggered when combo reaches a new level.
    
    Attributes:
        country: Country that leveled up
        time: Time since flash started
        duration: Total flash duration
        intensity: Flash brightness
    """
    country: str
    time: float
    duration: float
    intensity: float


@dataclass
class ConfettiParticle:
    """
    Confetti particle for victory celebration.
    Colorful squares that fall and spin.
    
    Attributes:
        x, y: Position on screen
        vx, vy: Velocity (vy positive = falling)
        size: Square size in pixels
        color: RGB color
        rotation: Current rotation angle (degrees)
        rotation_speed: Degrees per second
        lifetime: Seconds remaining
    """
    x: float
    y: float
    vx: float
    vy: float
    size: float
    color: tuple[int, int, int]
    rotation: float
    rotation_speed: float
    lifetime: float


@dataclass
class Meteor:
    """
    Meteor for the Meteor Shower event. Crosses the screen with a trail.
    When it touches a flag, applies a random speed boost to that country.
    
    Attributes:
        x, y: Current position
        vx, vy: Velocity (pixels per second)
        radius: Visual radius
        trail: List of (x, y, alpha) for trail segments
        max_trail: Max trail segments to keep
        hit_countries: Set of countries already boosted by this meteor (avoid double hit)
    """
    x: float
    y: float
    vx: float
    vy: float
    radius: float
    trail: list = field(default_factory=list)
    max_trail: int = 12
    hit_countries: set = field(default_factory=set)


class ParticleManager:
    """
    Manages particle systems: trails and explosions.
    Handles trail generation for flags and explosion effects.
    """
    
    def __init__(self):
        """Initialize the particle manager."""
        # Trail particles: country -> list of trail particles
        self.trail_particles: dict[str, list[TrailParticle]] = {}
        # Trail configuration
        self.trail_max_particles = 20  # Max particles per trail
        self.trail_lifetime = 0.5  # Seconds
        # Increased particle density by 20%: 0.05 * 0.8 = 0.04 (spawns more frequently)
        self.trail_spawn_interval = 0.04  # Spawn every 0.04s (was 0.05s)
        self.trail_last_spawn: dict[str, float] = {}  # country -> last spawn time
    
    def update_trail(self, country: str, pos: tuple[float, float], color: tuple[int, int, int], dt: float) -> None:
        """
        Update trail for a flag. Spawns new particles and updates existing ones.
        
        Args:
            country: Country name (identifier)
            pos: Current flag position (x, y)
            color: Flag color for trail
            dt: Delta time since last frame
        """
        current_time = time.time()
        
        # Initialize trail if needed
        if country not in self.trail_particles:
            self.trail_particles[country] = []
            self.trail_last_spawn[country] = current_time
        
        # Spawn new trail particle if enough time has passed
        if current_time - self.trail_last_spawn[country] >= self.trail_spawn_interval:
            # Create trail particle with random size (2-5px) for organic look
            import random
            random_size = random.uniform(2.0, 5.0)  # Random size for organic trail effect
            trail_particle = TrailParticle(
                pos=pos,
                color=color,
                alpha=180,  # Start with good visibility
                size=random_size,  # Current size (starts at random)
                initial_size=random_size,  # Store initial size for fade calculation
                lifetime=self.trail_lifetime
            )
            
            self.trail_particles[country].append(trail_particle)
            self.trail_last_spawn[country] = current_time
            
            # Limit trail length
            if len(self.trail_particles[country]) > self.trail_max_particles:
                self.trail_particles[country].pop(0)
        
        # Update existing trail particles
        particles_to_keep = []
        for particle in self.trail_particles[country]:
            # Update lifetime
            particle.lifetime -= dt
            
            if particle.lifetime > 0:
                # Fade out over time
                life_ratio = particle.lifetime / self.trail_lifetime if self.trail_lifetime > 0 else 0
                particle.alpha = int(180 * life_ratio)
                # Fade size proportionally to lifetime, preserving initial random variation
                particle.size = particle.initial_size * life_ratio
                particles_to_keep.append(particle)
        
        self.trail_particles[country] = particles_to_keep
    
    def clear_trail(self, country: str) -> None:
        """Clear trail for a specific country."""
        if country in self.trail_particles:
            self.trail_particles[country].clear()
    
    def clear_all_trails(self) -> None:
        """Clear all trails."""
        self.trail_particles.clear()
        self.trail_last_spawn.clear()


@dataclass
class FloatingText:
    """
    Floating action text for visual feedback.
    Floats upward and fades out over time.
    Includes elastic pulse effect for combo texts.
    """
    text: str
    x: float
    y: float
    color: tuple[int, int, int]
    dy: float = -2.0           # Velocidad vertical (negativa = sube)
    lifespan: int = 60         # Frames restantes
    max_lifespan: int = 60     # Para calcular alpha
    font_size: int = 16
    is_welcome: bool = False   # Tag for welcome messages (cooldown counting)
    pulse_ratio: float = 0.15  # Fraction of life for elastic pulse (welcome uses 0.4)
    
    def update(self) -> None:
        """Update position and lifespan."""
        self.y += self.dy
        self.lifespan -= 1
    
    def draw(self, surface: pygame.Surface) -> None:
        """Render the floating text with fade and elastic pulse effect."""
        if self.lifespan <= 0:
            return
        
        # Calculate alpha
        alpha = int(255 * (self.lifespan / self.max_lifespan)) if self.max_lifespan > 0 else 0
        alpha = max(0, min(255, alpha))
        
        # 🎯 ELASTIC PULSE: Scale up then down (configurable ratio)
        life_progress = 1.0 - (self.lifespan / self.max_lifespan) if self.max_lifespan > 0 else 1.0
        ratio = getattr(self, "pulse_ratio", 0.15)
        
        if life_progress < ratio and ratio > 0:  # Configurable pulse duration
            # Elastic overshoot: grows to 1.3x then settles to 1.0x
            t = life_progress / ratio  # Normalize to 0-1
            # Elastic formula: overshoot then bounce back
            scale = 1.0 + 0.4 * math.sin(t * math.pi) * (1 - t * 0.5)
        else:
            scale = 1.0
        
        # Calculate actual font size with pulse
        actual_font_size = max(8, int(self.font_size * scale))
        
        # Create font con BOLD para mejor legibilidad
        font = _get_font("Arial", actual_font_size, bold=True)
    
        # Render main text con anti-aliasing
        text_surface = font.render(self.text, True, self.color)
    
        # Apply alpha
        temp_surface = pygame.Surface(text_surface.get_size(), pygame.SRCALPHA)
        temp_surface.fill((255, 255, 255, alpha))
        text_surface = text_surface.copy()
        text_surface.blit(temp_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    
        rect = text_surface.get_rect(center=(int(self.x), int(self.y)))
    
        # Outline MÁS GRUESO (era 1px en diagonal, ahora 2px)
        outline_color = (0, 0, 0)
        outline_surface = font.render(self.text, True, outline_color)
        outline_temp = pygame.Surface(outline_surface.get_size(), pygame.SRCALPHA)
        outline_temp.fill((255, 255, 255, alpha))
        outline_surface = outline_surface.copy()
        outline_surface.blit(outline_temp, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    
        # Outline en 8 direcciones con DOBLE grosor
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                if dx != 0 or dy != 0:
                    surface.blit(outline_surface, (rect.x + dx, rect.y + dy))
    
        # Draw main text
        surface.blit(text_surface, rect)
    
    @property
    def is_alive(self) -> bool:
        """Check if text should still be displayed."""
        return self.lifespan > 0


class GameEngine:
    """
    Consumer class that processes events and renders using Pygame.
    Integrates Pymunk physics with ball sizes based on gift value.
    Enhanced with professional particle system (juice).
    """
    
    # Maximum number of floating texts rendered at once
    MAX_FLOATING_TEXTS: int = 10
    
    def __init__(
        self, 
        queue: asyncio.Queue, 
        streamer_name: str,
        database: Optional[Database] = None
    ):
        self.queue = queue
        self.streamer_name = streamer_name
        self.database = database
        self.cloud_manager = CloudManager()
        self.running = True
        
        self.messages: list[tuple[str, EventType]] = []
        self.connection_state = ConnectionState.DISCONNECTED
        
        # Country assignment system
        self.user_country_cache: dict[str, str] = {}
        self.country_player_count: dict[str, int] = {}
        
        # Flag emoji mapping
        self.flag_map = {
            "🇦🇷": "Argentina",
            "🇧🇷": "Brasil", 
            "🇲🇽": "Mexico",
            "🇪🇸": "España",
            "🇨🇴": "Colombia",
            "🇨🇱": "Chile",
            "🇵🇪": "Peru",
            "🇻🇪": "Venezuela"
        }
        
        # Asset Manager
        self.asset_manager = AssetManager()
        
        # Audio Manager
        self.audio_manager = AudioManager()
        
        # Initialize TTS (Text-to-Speech) if available
        if TTS_ENABLED:
            # Try to find an English voice, fallback to voice_index=106 or default
            try:
                # First, try to find an English voice
                temp_provider = Pyttsx3Provider()
                if temp_provider.is_available():
                    voices = temp_provider.list_voices()
                    english_voice_id = None

                    # Look for common English voice patterns
                    for voice_id in voices:
                        voice_lower = voice_id.lower()
                        # Common English voice names on macOS/Windows
                        if any(name in voice_lower for name in ['alex', 'samantha', 'victoria', 'daniel',
                                                                 'karen', 'lee', 'zira', 'david', 'mark',
                                                                 'richard', 'susan', 'hazel', 'tom']):
                            english_voice_id = voice_id
                            break

                    # If no English voice found, use voice_index=106 or first available
                    if english_voice_id:
                        tts_provider = Pyttsx3Provider(voice_id=english_voice_id)
                        logger.info(f"🎤 TTS enabled with English voice: {english_voice_id.split('.')[-1]}")
                    else:
                        # Fallback to voice 106 if available, otherwise first voice
                        if len(voices) > 106:
                            tts_provider = Pyttsx3Provider(voice_index=106)
                            logger.info(f"🎤 TTS enabled with voice index 106")
                        else:
                            tts_provider = Pyttsx3Provider(voice_index=0)
                            logger.info(f"🎤 TTS enabled with default voice")

                    if tts_provider.is_available():
                        self.audio_manager.set_tts_callback(tts_provider.speak)
                    else:
                        raise Exception("TTS provider not available")
                else:
                    raise Exception("Could not initialize TTS")
            except Exception as e:
                logger.warning(f"Failed to initialize TTS: {e}, trying fallback...")
                # Fallback to auto detection
                tts_provider = create_tts_provider("auto")
                if tts_provider and tts_provider.is_available():
                    self.audio_manager.set_tts_callback(tts_provider.speak)
                    logger.info("🎤 TTS enabled (fallback to default voice)")
                else:
                    logger.debug("🎤 TTS not available (install pyttsx3 for voice announcements)")
        else:
            logger.debug("🎤 TTS disabled via TTS_ENABLED=False in config")
        
        # Physics World
        self.physics_world = PhysicsWorld(
            asset_manager=self.asset_manager,
            game_engine=self
        )
        
        # Particle system
        self.particles: list[Particle] = []
        
        # Particle Manager (trails and explosions)
        self.particle_manager = ParticleManager()
        
        # Floating texts
        self.floating_texts: list[FloatingText] = []
        
        self.screen: Optional[pygame.Surface] = None
        self.font: Optional[pygame.font.Font] = None
        self.font_small: Optional[pygame.font.Font] = None
        self.clock: Optional[pygame.time.Clock] = None

        # Pre-allocated alpha layers (set in init_pygame)
        self._particle_layer: Optional[pygame.Surface] = None
        self._trail_layer: Optional[pygame.Surface] = None
        self._flash_layer: Optional[pygame.Surface] = None
        self._ray_layer: Optional[pygame.Surface] = None
        self._lanes_surface: Optional[pygame.Surface] = None
        
        self.header_height = 36          # 36px — fits "1st:" left + Liga C5 right with 13px font
        self.message_area_height = 70   # Reducido de 105 a 70
        
        # Rendering surfaces
        self.render_surface: Optional[pygame.Surface] = None
        self.display_scale = 1.0
        
        # Winner celebration effects (NEW)
        self.winner_animation_time = 0.0
        self.winner_scale_pulse = 1.0
        self.winner_glow_alpha = 0
        
        # Auto stress test system
        self.stress_test_timer = 0.0
        self.frame_count = 0
        self.fps_update_timer = 0.0
        self.current_fps = 0.0
    
        # Game state system
        self.game_state = 'IDLE'  # 'IDLE' o 'RACING'
        self.idle_animation_time = 0.0  # Para animaciones pulsantes
        self.last_winner = None  # Last winner of previous race
        self.last_winner_distance = 0.0  # Distance of last winner
        
        # Leader change animation (VFX)
        self.last_leader_name = None  # Líder del frame anterior
        self.leader_pop_timer = 0  # Temporizador para efecto "pop" (frames)
    
        # Keyword Binding system
        self.user_assignments: dict[str, str] = {}  # username -> country
        self.users_notified: set[str] = set()       # Anti-spam para joins
        self.last_join_time: dict[str, float] = {}  # username -> timestamp

        # Captain/MVP System
        self.session_points: dict[str, dict[str, int]] = {}  # {country: {username: points}}
        self.current_captains: dict[str, str] = {}           # {country: username}
        self.captain_change_timer: dict[str, int] = {}       # {country: frames_remaining}
        
        # Cloud sync control
        self.race_synced = False  # Flag to prevent multiple syncs per race
        self._leaderboard_cache: Optional[pygame.Surface] = None  # Cached post-race leaderboard
        
        # 🏆 Global Ranking Panel
        self.global_rank_data: list[dict] = []  # Top 5 countries by wins (all-time)
        self.daily_rank_data: list[dict] = []   # Top 5 countries by wins (today)
        self.global_rank_last_update = 0.0  # Timestamp of last update
        self.global_rank_loading = False  # Flag to prevent multiple fetches
        
        # 3D Visualization animation state
        self.ranking_3d_animation_time = 0.0  # For animated effects
        self._show_ranking_panel: bool = False  # Toggle with H key
        self.hud_visible: bool = True  # Toggle with B key (Broadcast mode)
        
        # Victory flash effect (white screen flash on win)
        self.victory_flash_alpha = 0.0  # 0.0 = no flash, 255.0 = full white
        self.victory_flash_duration = 0.3  # Seconds to fade out
        self.victory_flash_time = 0.0  # Time elapsed since flash started

        # Hype Disaster flash (full-screen crimson burst on detonation)
        self._disaster_flash_alpha: float = 0.0
        self._disaster_flash_time: float = 0.0
        self._disaster_flash_dur: float = 0.6   # seconds to fade
        self._disaster_title_timer: float = 0.0  # counts down from 2.5s
        
        # 🏆 EPIC VICTORY SEQUENCE
        self.victory_sequence_active = False
        self.victory_sequence_time = 0.0
        self.victory_zoom_level = 1.0  # Camera zoom (1.0 = normal, 1.5 = zoomed in)
        self.victory_zoom_target = 1.0
        self.victory_zoom_center: tuple[float, float] = (0.0, 0.0)
        self.slow_motion_active = False
        self.slow_motion_duration = 2.0  # Seconds of slow motion
        self.slow_motion_factor = 0.5  # dt multiplier (0.5 = half speed)
        self.confetti_particles: list = []  # Confetti system
        self.max_confetti = 150
        self._confetti_pool: list[ConfettiParticle] = []  # Object pool to reduce GC pressure
        self.victory_banner_scale = 0.0  # For entrance animation
        self.victory_winner_captain: Optional[str] = None  # Captain who won
        self.victory_was_gift_mode = False  # Track if gift mode for monetization message
        
        # Shortcuts panel position (dynamic for COMMENT mode)
        self.shortcuts_panel_position = "right"  # "right" or "left"
        
        # 🎥 Screen Shaker (camera effects)
        self.screen_shaker = ScreenShaker()
        
        # 🌌 Background Manager (parallax starfield) - initialized after pygame
        self.background_manager: Optional[BackgroundManager] = None
        
        # 🌟 Leader spotlight with smooth interpolation
        self.leader_glow_time = 0.0  # Animation time for pulsing effect
        self.spotlight_current_pos: tuple[float, float] = (0.0, 0.0)  # Current interpolated position
        self.spotlight_target_pos: tuple[float, float] = (0.0, 0.0)   # Target position (leader)
        self.spotlight_lerp_speed = 5.0  # Interpolation speed (higher = faster)
        
        # 📺 HUD Timing (panel auto-hide after race starts)
        self.race_start_time: Optional[float] = None  # When racing started
        self.hud_fade_duration = 3.0  # Seconds before HUD fades
        
        # 📜 Ticker system for shortcuts (bottom scrolling bar)
        self.ticker_offset = 0.0
        self.ticker_speed = 40.0  # pixels per second

        # 👍 Likes goal bar (retention - Meteor Shower event)
        self.current_likes = 0
        self.likes_goal = LIKES_GOAL_INITIAL
        self.meteors: list[Meteor] = []
        self._likes_charge_played = False  # Play charge sound once when bar fills
        
        # 📢 CTA Banner - Smart rotation every 10 seconds
        self.cta_last_rotation_time: float = 0.0
        self.cta_message_index: int = 0
        self.cta_rotation_interval = 8.0  # seconds (Smart CTA rotation)
        self._cta_surface: Optional[pygame.Surface] = None  # Cached banner surface
        self._cta_cached_index: int = -1  # Index when cache was built
        
        # 🔥 COMBO SYSTEM
        from .config import COMBO_WINDOW, COMBO_THRESHOLD, ON_FIRE_THRESHOLD
        self.combo_tracker: dict[str, list[float]] = {}  # {country: [timestamps]}
        self.combo_counts: dict[str, int] = {}  # {country: current_combo_count}
        self.combo_window = COMBO_WINDOW        # seconds — see config.py
        self.combo_threshold = COMBO_THRESHOLD  # minimum gifts for "COMBO!" display
        self.on_fire_threshold = ON_FIRE_THRESHOLD  # threshold for "ON FIRE" state
        self.on_fire_countries: set[str] = set()  # countries currently on fire

        # 🌹 ROSA COMBO MULTIPLIER
        ROSA_COMBO_WINDOW     = 2.0   # seconds — shorter than general combo window
        ROSA_COMBO_THRESHOLDS = [     # (min_count, level, multiplier)
            (10, 3, 2.0),
            (6,  2, 1.5),
            (3,  1, 1.2),
        ]
        self.ROSA_COMBO_WINDOW     = ROSA_COMBO_WINDOW
        self.ROSA_COMBO_THRESHOLDS = ROSA_COMBO_THRESHOLDS
        self._rosa_tracker:     dict[str, list[float]] = {}  # country → [timestamp, ...]
        self._rosa_combo_level: dict[str, int]          = {}  # country → 0/1/2/3

        # 🌙 Lunar Gravity event
        self._lunar_active:        bool  = False
        self._lunar_timer:         float = 0.0
        self._lunar_overlay_alpha: int   = 0    # 0–55, fades in/out
        self.LUNAR_DURATION        = 30.0
        self.LUNAR_FADE_SPEED      = 55    # alpha units/second for overlay fade

        # ⚡ Hype Timer (Disaster Countdown)
        self._hype_timer_start: float = time.time()
        self._hype_timer_fired: bool  = False
        self._hype_cue_printed: bool  = False  # host 30s cue printed flag
        
        # 🌈 MOTION TRAILS (replaces fire_particles for crisp neon effect)
        self.motion_trails: dict[str, list[MotionTrailSegment]] = {}  # {country: [segments]}
        self.motion_trail_history: dict[str, list[tuple[float, float]]] = {}  # Position history
        self.max_trail_segments = 20  # Max segments per country
        self.trail_segment_lifetime = 0.3  # Seconds before fade
        self._motion_trail_segment_pool: list[MotionTrailSegment] = []  # Object pool to avoid GC spikes
        
        # ✨ COMBO FLASHES (flash effect on combo level up)
        self.combo_flashes: list[ComboFlash] = []
        
        # 🏁 FINAL STRETCH system
        self.final_stretch_triggered = False
        self.final_stretch_threshold = 0.80  # 80% of track
        self.final_stretch_time = 0.0  # animation timer
        self.original_parallax_speed = 50.0  # store original speed
        
        # 🎤 TTS Announcements tracking
        self._last_leader: Optional[str] = None
        self._last_positions: Dict[str, float] = {}  # Track positions for overtake detection
        self._last_overtake_announcement: float = 0.0  # Cooldown for overtake announcements
        self._last_close_race_announcement: float = 0.0  # Cooldown for close race announcements
        self._overtake_cooldown = 3.0  # Seconds between overtake announcements
        self._close_race_cooldown = 5.0  # Seconds between close race announcements
        
        # 🧪 Test FIRE (F key) rate limiting – avoid crash when spamming
        self._test_fire_active = False  # Skip TTS during TEST FIRE burst
        self._last_test_fire_time: float = 0.0
        self._test_fire_cooldown = 2.0  # Seconds before F can be pressed again
        
        # 🧪 Manual stress test (key K): inject VOTE/GIFT at 20/sec
        self._stress_test_active = False
        self._stress_test_last_inject: float = 0.0
        
        self.last_activity_time: float = time.time()

        # 🤖 Auto-Pilot (Chaos Loop)
        from .config import AUTOPILOT_ENABLED
        self._autopilot_enabled: bool                    = AUTOPILOT_ENABLED
        self._autopilot_active: bool                     = False
        self._autopilot_resume_after: float              = 0.0
        self._autopilot_task: Optional[asyncio.Task]     = None
        self._autopilot_recent_actions: collections.deque = collections.deque(maxlen=3)

        # 🚪 ESC double-press to quit – avoid accidental close when spamming 1/2/3
        self._esc_quit_requested = False
        self._esc_quit_time: float = 0.0
        self._esc_quit_window = 2.0  # Seconds to press ESC again to confirm
        
        # 📊 PERFORMANCE MONITORING
        self._fps_samples: list[float] = []  # FPS samples for averaging
        self._fps_sample_times: list[float] = []  # Timestamps for each sample
        self._perf_log_interval = 10.0  # Log performance every 10 seconds
        self._last_perf_log_time: float = time.time()
        self._low_fps_start_time: Optional[float] = None  # When low FPS started
        self._low_fps_threshold = float(FPS) * 0.6  # 18.0 @ 30 FPS, 36.0 @ 60 FPS
        self._low_fps_duration_threshold = 2.0  # Seconds of low FPS before warning
        self._frame_count = 0
        self._last_fps_check_time = time.time()
        self._last_frame_time = time.time()
        
        # Fixed timestep for physics (independent of render FPS)
        self._fixed_dt = 1.0 / PHYSICS_FIXED_HZ
        self._physics_accumulator = 0.0
        self._max_physics_catchup = self._fixed_dt * 5  # Cap to avoid spiral of death

        # 🔥 Hype Mode
        self.hype_manager = HypeManager(
            threshold_cpm=HYPE_THRESHOLD_CPM,
            cooldown_duration=HYPE_COOLDOWN_DURATION,
        )
        self._hype_micro_shake_timer: float = 0.0  # Countdown to next micro-shake

        # 👥 Follower Wall
        self.notification_manager = NotificationManager(
            banner_x=SCREEN_WIDTH // 2,
            banner_y=FOLLOWER_BANNER_Y,
            banner_w=FOLLOWER_BANNER_WIDTH,
            banner_h=FOLLOWER_BANNER_HEIGHT,
            lifespan=FOLLOWER_BANNER_LIFESPAN,
        )

        # 🔊 Audio toast HUD (shown on M/N key press)
        self._audio_toast_text = ""
        self._audio_toast_timer = 0.0

        # 🌑 Blackout Mode
        self.blackout_active: bool = False
        self.blackout_alpha: int = 0
        self._blackout_increase_timer: float = 0.0
        self._blackout_hype_timer: float = 0.0
        self._blackout_restored_timer: float = 0.0

        # Audience milestone state
        self.viewer_count: int = 0
        self._milestones_triggered: set = set()
        self._highest_milestone_reached: int = 0
        self._viewer_count_baseline: int = -1   # -1 = not yet set
        self._milestone_banner_timer: float = 0.0
        self._milestone_banner_count: int = 0
        self._milestone_banner_msg: str = ""

    def init_pygame(self) -> None:
        """Initialize Pygame with centered window and gradient background."""
        import os
        
        try:
            logger.info("🔧 Starting pygame init...")
            # Windows: high-DPI display before any SDL init to avoid blurry window
            if sys.platform == "win32":
                os.environ.setdefault("SDL_VIDEO_HIGHDPI_DISPLAY", "1")
            # Center the window on screen
            os.environ['SDL_VIDEO_WINDOW_POS'] = 'center'
            logger.info("🔧 SDL_VIDEO_WINDOW_POS set")
            
            pygame.init()
            logger.info("🔧 pygame.init() complete")
            
            from .config import (
                ACTUAL_WIDTH, ACTUAL_HEIGHT, SCREEN_WIDTH, SCREEN_HEIGHT,
                GRADIENT_TOP, GRADIENT_BOTTOM
            )
            logger.info(f"🔧 Config loaded: {ACTUAL_WIDTH}x{ACTUAL_HEIGHT}")
            
            pygame.display.set_caption("Moto Race")
            logger.info("🔧 Caption set")
            
            # Display flags: double buffer + hardware surface for smooth 60 FPS; SCALED for high-DPI
            flags = pygame.DOUBLEBUF | pygame.HWSURFACE
            if hasattr(pygame, "SCALED"):
                flags |= pygame.SCALED
            self.screen = pygame.display.set_mode((ACTUAL_WIDTH, ACTUAL_HEIGHT), flags)
            logger.info("🔧 Display mode set")
            
            # Render to inner game surface, then blit with margin
            self.render_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.display_scale = 1.0
            self.clock = pygame.time.Clock()
            logger.info("🔧 Clock created")
            
            # Try to load display font with fallback chain (Impact = bold, distinctive)
            from .config import DISPLAY_FONT_NAMES
            font_names = DISPLAY_FONT_NAMES
            font_loaded = False
            
            for font_name in font_names:
                try:
                    self.font = pygame.font.SysFont(font_name, FONT_SIZE, bold=True)
                    self.font_small = pygame.font.SysFont(font_name, FONT_SIZE_SMALL, bold=True)
                    logger.info(f"🔧 System font loaded: {font_name}")
                    font_loaded = True
                    break
                except Exception:
                    continue
            
            if not font_loaded:
                logger.warning("🔧 System fonts failed, using default")
                self.font = pygame.font.Font(None, FONT_SIZE)
                self.font_small = pygame.font.Font(None, FONT_SIZE_SMALL)
            
            # Create static gradient backgrounds
            logger.info("🔧 Creating gradients...")
            self.gradient_background = self._create_gradient_background()
            self.outer_background = self._create_outer_background()
            logger.info("🔧 Gradients created")
            
            # 🌌 Initialize parallax background manager
            logger.info("🔧 Creating parallax background...")
            self.background_manager = BackgroundManager(SCREEN_WIDTH, SCREEN_HEIGHT)
            logger.info("🔧 Parallax background created")
            
            # Render flag emojis
            logger.info("🔧 Rendering emojis...")
            self._render_flag_emojis()
            logger.info("🔧 Emojis rendered")

            # Pre-allocate reusable alpha layers (eliminates per-frame Surface allocations)
            self._particle_layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            self._trail_layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            self._flash_layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            self._ray_layer = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)

            # Pre-render static lanes surface (lane separators never change)
            self._lanes_surface = self._build_lanes_surface()
            logger.info("🔧 Alpha layers and lanes surface pre-allocated")

            logger.info("🔧 Starting BGM...")
            self.audio_manager.play_bgm()
            
            logger.info("✅ Pygame fully initialized")
            
        except Exception as e:
            logger.error(f"❌ pygame init failed at step: {e}")
            raise
    
    def _create_gradient_background(self) -> pygame.Surface:
        """
        Create a static gradient background surface for optimal performance.
        Called once during initialization to avoid recalculating every frame.
        
        Returns:
            pygame.Surface with vertical gradient from GRADIENT_TOP to GRADIENT_BOTTOM
        """
        from .config import GRADIENT_TOP, GRADIENT_BOTTOM, SCREEN_WIDTH, SCREEN_HEIGHT
        
        gradient_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        
        # Draw gradient line by line
        for y in range(SCREEN_HEIGHT):
            # Linear interpolation between top and bottom colors
            ratio = y / SCREEN_HEIGHT
            r = int(GRADIENT_TOP[0] + (GRADIENT_BOTTOM[0] - GRADIENT_TOP[0]) * ratio)
            g = int(GRADIENT_TOP[1] + (GRADIENT_BOTTOM[1] - GRADIENT_TOP[1]) * ratio)
            b = int(GRADIENT_TOP[2] + (GRADIENT_BOTTOM[2] - GRADIENT_TOP[2]) * ratio)
            
            pygame.draw.line(gradient_surf, (r, g, b), (0, y), (SCREEN_WIDTH, y))
        
        logger.info("✨ Gradient background created (static surface)")
        return gradient_surf

    def _create_outer_background(self) -> pygame.Surface:
        """
        Create a subtle outer gradient background for the window margins.
        
        Returns:
            pygame.Surface with vertical gradient for outer margins
        """
        from .config import OUTER_GRADIENT_TOP, OUTER_GRADIENT_BOTTOM, ACTUAL_WIDTH, ACTUAL_HEIGHT
        
        outer_surf = pygame.Surface((ACTUAL_WIDTH, ACTUAL_HEIGHT))
        
        for y in range(ACTUAL_HEIGHT):
            ratio = y / ACTUAL_HEIGHT
            r = int(OUTER_GRADIENT_TOP[0] + (OUTER_GRADIENT_BOTTOM[0] - OUTER_GRADIENT_TOP[0]) * ratio)
            g = int(OUTER_GRADIENT_TOP[1] + (OUTER_GRADIENT_BOTTOM[1] - OUTER_GRADIENT_TOP[1]) * ratio)
            b = int(OUTER_GRADIENT_TOP[2] + (OUTER_GRADIENT_BOTTOM[2] - OUTER_GRADIENT_TOP[2]) * ratio)
            pygame.draw.line(outer_surf, (r, g, b), (0, y), (ACTUAL_WIDTH, y))
        
        logger.info("✨ Outer gradient background created (static surface)")
        return outer_surf

    def _render_flag_emojis(self) -> None:
        """Render text abbreviation sprites for countries without PNG sprites.

        Emoji flags (🇦🇷 etc.) are not supported by pygame's FreeType renderer —
        they render as empty squares. Instead, we draw a colored circle with the
        country abbreviation (ARG, BRA...) as a crisp text sprite.
        """
        from .config import COUNTRY_ABBREV, GIFT_COLORS, FLAG_RADIUS

        for country, racer in self.physics_world.racers.items():
            if racer.sprite is not None:
                continue

            abbrev = COUNTRY_ABBREV.get(country, country[:3].upper())
            color = GIFT_COLORS.get(country, (180, 180, 220))
            size = FLAG_RADIUS * 2 + 4

            # Draw a filled circle with abbreviation text
            surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(surf, color, (size // 2, size // 2), size // 2)
            pygame.draw.circle(surf, (255, 255, 255), (size // 2, size // 2), size // 2, 1)
            try:
                abbrev_font = pygame.font.SysFont("Arial", max(7, size // 3), bold=True)
                abbrev_surf = abbrev_font.render(abbrev, False, (255, 255, 255))
                ax = (size - abbrev_surf.get_width()) // 2
                ay = (size - abbrev_surf.get_height()) // 2
                surf.blit(abbrev_surf, (ax, ay))
            except Exception:
                pass
            racer.sprite = surf
            logger.info(f"Created text sprite for {country} ({abbrev})")
    
    def emit_explosion(
        self, 
        pos: tuple[float, float], 
        color: tuple[int, int, int],
        count: int,
        power: float,
        diamond_count: int = 0
    ) -> None:
        """
        Emit particle explosion with configurable power and premium effects.
        
        Args:
            pos: (x, y) position to spawn particles from
            color: Base RGB color tuple for particles
            count: Number of particles to spawn
            power: Velocity multiplier (1.0 = normal, 2.0 = double speed)
            diamond_count: Gift value for premium effects (>100 = golden/brilliant)
        """
        x, y = pos
        
        # Premium gift detection (expensive gifts get golden particles)
        is_premium = diamond_count > 100
        
        if is_premium:
            # Golden/brilliant color for expensive gifts
            color = (255, 215, 0)  # Gold
            count = int(count * 1.5)  # 50% more particles
            power *= 1.3  # 30% more explosive
        
        for _ in range(count):
            # Random direction (full 360 degrees)
            angle = random.uniform(0, 2 * math.pi)
            
            # Base speed with power multiplier
            base_speed = random.uniform(80, 200)
            speed = base_speed * power
            
            # Velocity vector
            vel = pymunk.Vec2d(
                math.cos(angle) * speed,
                math.sin(angle) * speed
            )
            
            # Lifetime (premium gifts = longer lasting particles)
            if is_premium:
                max_lifetime = random.uniform(80, 120)  # 1.3-2.0 seconds
                # 🎯 VARIEDAD EN TAMAÑO: rango más amplio para victoria
                initial_radius = random.randint(4, 14)  # Era uniform(10, 20)
            else:
                max_lifetime = random.uniform(40, 70)  # 0.66-1.16 seconds
                # 🎯 VARIEDAD EN TAMAÑO: partículas normales con más variación
                initial_radius = random.randint(4, 10)  # Era uniform(6, 12)
            
            particle = Particle(
                pos=pymunk.Vec2d(x, y),
                vel=vel,
                color=color,
                radius=initial_radius,
                initial_radius=initial_radius,
                lifetime=max_lifetime,
                max_lifetime=max_lifetime
            )
            
            self.particles.append(particle)
    
    def emit_collision_particles(
        self, 
        pos: tuple[float, float],
        impulse_magnitude: float
    ) -> None:
        """
        Emit small particle burst on collision.
        Only triggers on high-force impacts.
        
        Args:
            pos: Collision point
            impulse_magnitude: Force of collision (from Pymunk)
        """
        # Threshold for visible collision (tune this value)
        if impulse_magnitude < 500:
            return
        
        # Scale particle count with impact force
        count = min(int(impulse_magnitude / 300), 8)  # Max 8 particles
        count = max(count, 3)  # Min 3 particles
        
        # White sparks for collision effect
        color = (255, 255, 255)
        
        # Lower power, shorter burst
        power = 0.6
        
        self.emit_explosion(pos, color, count, power)
    
    def update_particles(self, dt: float) -> None:
        """
        Update all particles: physics, lifetime, and cleanup.
        Optimized for performance with list comprehension.
        """
        particles_to_keep = []
        
        for particle in self.particles:
            # Physics update using Pymunk vectors
            particle.pos += particle.vel * dt
            
            # Apply gravity to velocity
            particle.vel += pymunk.Vec2d(0, 400) * dt  # Gravity acceleration
            
            # Reduce lifetime (frame-based)
            particle.lifetime -= 60 * dt  # Convert dt to frames (60fps)
            
            # Proportional radius reduction based on lifetime
            life_ratio = particle.lifetime / particle.max_lifetime if particle.max_lifetime > 0 else 0
            particle.radius = particle.initial_radius * life_ratio
            
            # Keep particle if still alive
            if particle.lifetime > 0:
                particles_to_keep.append(particle)
        
        # Efficient cleanup
        self.particles = particles_to_keep
    
    def update_floating_texts(self) -> None:
        """Update and remove floating texts."""
        texts_to_keep = []
        
        for text in self.floating_texts:
            text.update()
            
            # Keep alive texts
            if text.is_alive:
                texts_to_keep.append(text)
        
        # Cleanup
        self.floating_texts = texts_to_keep
    
    def _render_trails(self) -> None:
        """
        Render trail particles into a shared alpha layer then blit once.
        Eliminates per-particle Surface allocations.
        """
        if not self.particle_manager.trail_particles or self._trail_layer is None:
            return
        self._trail_layer.fill((0, 0, 0, 0))
        has_any = False
        for trail_particles in self.particle_manager.trail_particles.values():
            for particle in trail_particles:
                if particle.alpha <= 0 or particle.size <= 0:
                    continue
                color_with_alpha = (*particle.color, particle.alpha)
                cx = int(particle.pos[0])
                cy = int(particle.pos[1])
                radius = max(int(particle.size), 1)
                pygame.draw.circle(self._trail_layer, color_with_alpha, (cx, cy), radius)
                has_any = True
        if has_any:
            self.render_surface.blit(self._trail_layer, (0, 0))
    
    def _render_particles(self) -> None:
        """
        Render particles into a shared alpha layer then blit once.
        Eliminates per-particle Surface allocations.
        """
        if not self.particles or self._particle_layer is None:
            return
        self._particle_layer.fill((0, 0, 0, 0))
        for particle in self.particles:
            # Skip if position is invalid
            if not math.isfinite(particle.pos.x) or not math.isfinite(particle.pos.y):
                continue

            # Calculate lifetime ratio for opacity
            life_ratio = particle.lifetime / particle.max_lifetime if particle.max_lifetime > 0 else 0

            # Opacity fade
            opacity = self._safe_int(255 * life_ratio, 0)

            # Clamp radius to minimum 1 pixel
            radius = max(self._safe_int(particle.radius, 1), 1)

            # Skip if too transparent
            if opacity < 10:
                continue

            # Draw directly onto shared layer
            color_with_alpha = (*particle.color, opacity)
            cx = self._safe_int(particle.pos.x, 0)
            cy = self._safe_int(particle.pos.y, 0)
            pygame.draw.circle(self._particle_layer, color_with_alpha, (cx, cy), radius)

        self.render_surface.blit(self._particle_layer, (0, 0))
    
    def _render_floating_texts(self) -> None:
        """Render all floating texts for visual feedback."""
        for text in self.floating_texts:
            text.draw(self.render_surface)
    
    def _on_real_activity(self) -> None:
        """Reset activity timer and deactivate Auto-Pilot when real user activity occurs."""
        now = time.time()
        self.last_activity_time = now

        # Preempt Auto-Pilot when a real viewer interacts
        if self._autopilot_active:
            from .config import AUTOPILOT_COOLDOWN_AFTER_REAL
            self._autopilot_active = False
            self._autopilot_resume_after = now + AUTOPILOT_COOLDOWN_AFTER_REAL
            logger.info("[AutoPilot] DEACTIVATED by real activity — resumes in %.0fs",
                        AUTOPILOT_COOLDOWN_AFTER_REAL)

    # Max events to process per frame to avoid backlog causing a single frame to stall
    MAX_EVENTS_PER_FRAME = 200
    LAG_WARNING_THRESHOLD_SEC = 1.5

    async def process_events(self) -> None:
        """Drain the event queue in one frame (burst handling) to avoid backlog on vote spam."""
        processed = 0
        while processed < self.MAX_EVENTS_PER_FRAME:
            try:
                event = self.queue.get_nowait()
                await self._handle_event(event)
                processed += 1
            except asyncio.QueueEmpty:
                break

    async def _handle_event(self, event: GameEvent) -> None:
        """Handle a single event from the queue. Logs input latency when above threshold."""
        if event.created_at_sec is not None:
            latency_sec = time.perf_counter() - event.created_at_sec
            if latency_sec > self.LAG_WARNING_THRESHOLD_SEC:
                logger.warning(
                    "[LAG] Event latency detected: %.0fms (type=%s)",
                    latency_sec * 1000,
                    event.type.name,
                )
        if event.type == EventType.QUIT:
            logger.info("🚪 Exiting: EventType.QUIT (e.g. TikTok disconnect)")
            self.running = False
            return
        
        if event.type == EventType.CONNECTION_STATUS:
            if event.extra and "state" in event.extra:
                self.connection_state = event.extra["state"]
            
            message = event.format_message()
            self.messages.append((message, event.type))
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]
        
        elif event.type == EventType.GIFT:
            self._on_real_activity()
            # TRANSICIÓN: IDLE -> RACING al primer regalo
            if self.game_state == 'IDLE':
                self._transition_to_racing()
                logger.info("🏁 Game state: RACING (first gift received!)")
        
            gift_count = event.extra.get("count", 1) if event.extra else 1
            diamond_count = event.extra.get("diamond_count", 1) if event.extra else 1
            gift_name = event.content
            username = self.sanitize_username(event.username)
            
            # SMART COUNTRY ASSIGNMENT
            # MOTOGP: si el regalo está mapeado a un país, ese país avanza directamente
            if MOTOGP_MODE:
                gift_key = gift_name.strip().lower()
                mapped_country = MOTOGP_GIFT_COUNTRY_MAP.get(gift_key)
                if mapped_country and mapped_country in self.physics_world.racers:
                    country = mapped_country
                    assignment_type = "gift_map"
                    self.user_assignments[username] = mapped_country
                else:
                    country, assignment_type = self._get_user_country_with_autojoin(username, gift_name)
            else:
                country, assignment_type = self._get_user_country_with_autojoin(username, gift_name)
            
            # 🏆 CAPTAIN SYSTEM: Track points
            self._update_captain_points(username, country, diamond_count)

            # 🔥 HYPE: Register engagement event
            self.hype_manager.register_event()

            # 🔥 COMBO SYSTEM: Register this gift (count each gift_count as separate)
            for _ in range(min(gift_count, 5)):  # Cap at 5 to prevent abuse
                self.register_combo_event(country)

            logger.info(f"🎁 REGALO: {username} ({assignment_type}) → {country} | regalo: {gift_name}")
            
            # Apply impulse to country's flag
            success, was_frozen = self.physics_world.apply_gift_impulse(
                country=country,
                gift_name=gift_name,
                diamond_count=diamond_count
            )

            if success:
                # Play appropriate sound effect based on gift value
                self.audio_manager.play_gift_sound(
                    gift_name=gift_name,
                    diamond_value=diamond_count
                )

                # Emit particle effect at flag position
                racer = self.physics_world.racers[country]
                pos = (racer.body.position.x, racer.body.position.y)

                # Larger explosions for bigger gifts
                is_large_gift = diamond_count > 50
                count = 15 + int(diamond_count / 8) if is_large_gift else 10 + int(diamond_count / 10)
                power = 1.2 if is_large_gift else 0.8

                # 🎥 Big impact shake for large gifts
                if diamond_count >= 100:
                    self.screen_shaker.big_impact_shake()
                elif is_large_gift:
                    self.screen_shaker.impact_shake()

                self.emit_explosion(
                    pos=pos,
                    color=racer.color,
                    count=count,
                    power=power,
                    diamond_count=diamond_count
                )

                # Emit floating text feedback at top (respect global limit)
                from .config import SCREEN_WIDTH, FLOATING_TEXT_TOP_Y
                if was_frozen:
                    # Country is frozen — movement is queued, not visible yet.
                    # Show a clear message so the viewer knows their gift was registered.
                    freeze_remaining = self.physics_world.frozen_countries.get(country, 0.0)
                    self.floating_texts.append(
                        FloatingText(
                            text=f"FROZEN! +{diamond_count}💎 queued ({freeze_remaining:.1f}s)",
                            x=SCREEN_WIDTH / 2,
                            y=FLOATING_TEXT_TOP_Y,
                            color=(0, 200, 255),  # ice-blue matches freeze theme
                            lifespan=70,
                            max_lifespan=70,
                            font_size=18,
                            dy=-0.8
                        )
                    )
                else:
                    self.floating_texts.append(
                        FloatingText(
                            text=f"{gift_name} x{gift_count}",
                            x=SCREEN_WIDTH / 2,
                            y=FLOATING_TEXT_TOP_Y,
                            color=(255, 255, 255),
                            lifespan=40,
                            max_lifespan=40,
                            font_size=20,
                            dy=-1.0
                        )
                    )
                if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
                    self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]
            
            # Blackout recharge: Rosa/Rose recharges the lights
            if self.blackout_active and gift_name.lower() in ("rosa", "rose"):
                self._recharge_blackout()

            # Rosa combo multiplier tracking
            if gift_name.lower() in ("rosa", "rose") and country:
                self._update_rosa_combo(country, time.perf_counter())

            # Apply combat effects (Rosa, Pesa, Helado)
            combat_result = self.physics_world.apply_gift_effect(
                gift_name=gift_name,
                sender_country=country
            )
            
            # Handle freeze effect
            if combat_result['effect'] == 'freeze':
                target = combat_result['target']
                if target in self.physics_world.racers:
                    # Play freeze sound effect
                    self.audio_manager.play_freeze_sound()

                    # 🎥 Trigger screen shake for impact
                    self.screen_shaker.impact_shake()

                    target_racer = self.physics_world.racers[target]
                    pos = (target_racer.body.position.x, target_racer.body.position.y)

                    # Global alert floating text (centered, long-lived ~3s)
                    self.floating_texts.append(FloatingText(
                        text=f"** {target} FROZEN! **",
                        x=SCREEN_WIDTH / 2,
                        y=FLOATING_TEXT_TOP_Y,
                        color=COLOR_TEXT_FREEZE,
                        dy=-0.8,
                        lifespan=180,
                        max_lifespan=180,
                        font_size=18,
                    ))

                    # Emit freeze particles (blue ice effect)
                    self.emit_explosion(pos=pos, color=(100, 200, 255), count=35, power=1.0, diamond_count=0)

                    self.hype_manager.register_event()
            
            # Handle setback/pesa effect
            elif combat_result['effect'] == 'setback':
                target = combat_result.get('target')
                if target in self.physics_world.racers:
                    # 🎥 Trigger screen shake for attack impact
                    self.screen_shaker.impact_shake()
            
            if self.database:
                asyncio.create_task(
                    self.database.save_event_to_db(
                        user=username,
                        gift_name=gift_name,
                        diamond_count=diamond_count,
                        gift_count=gift_count,
                        streamer=self.streamer_name
                    )
                )
            
            # Message with assignment indicator
            assignment_indicator = {
                "cached": "✓",
                "flag": ">",
                "balanced": "~"
            }.get(assignment_type, "")

            message = f"{assignment_indicator} {username} → {country}: {gift_name} x{gift_count} ({diamond_count}d)"
            self.messages.append((message, event.type))
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]
    
        elif event.type == EventType.JOIN:
            await self._handle_join_event(event)
        
        elif event.type == EventType.VOTE:
            await self._handle_vote_event(event)
        
        elif event.type == EventType.LIKE:
            self._on_real_activity()
            count = (event.extra or {}).get("count", 1)
            self.add_likes(max(1, int(count)))
            msg = event.format_message()
            self.messages.append((msg, event.type))
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]

        elif event.type == EventType.FOLLOW:
            await self._handle_follow_event(event)

        elif event.type == EventType.VIEWER_COUNT:
            count = event.extra.get("count", 0) if event.extra else 0
            if count > 0:
                self.viewer_count = count
                self._check_audience_milestones(count)

        elif event.type == EventType.COMMENT:
            self._on_real_activity()
            # TRANSICIÓN: IDLE -> RACING al primer comentario (incluso sin shortcut)
            if self.game_state == 'IDLE':
                logger.info(f"🏁 First comment received from {event.username}: '{event.content}' - Starting race!")
                self._transition_to_racing()
                logger.info("🏁 Game state: RACING (first comment received!)")
            
            # Display comment in message log
            message = event.format_message()
            self.messages.append((message, event.type))
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]
    
    async def _handle_join_event(self, event: GameEvent) -> None:
        """Handle user joining: either room join (welcome) or team join (keyword)."""
        # Room join: viewer entered the livestream → Visual Welcome
        if event.extra and event.extra.get("room_join"):
            self._handle_user_join(event.username)
            return

        # Team join: user joins a country via keyword
        username = event.username
        requested_country = event.content
        keyword = event.extra.get("keyword", "") if event.extra else ""
        
        # Check if user is already assigned
        if username in self.user_assignments:
            current_country = self.user_assignments[username]
            if current_country == requested_country:
                logger.debug(f"🏁 {username} already in {current_country}")
                return
            else:
                # User wants to switch teams
                logger.info(f"🔄 {username} switching from {current_country} to {requested_country}")
        
        # Anti-spam check
        import time
        current_time = time.time()
        last_time = self.last_join_time.get(username, 0)
        
        from .config import JOIN_NOTIFICATION_COOLDOWN
        if current_time - last_time < JOIN_NOTIFICATION_COOLDOWN:
            return  # Too soon, ignore
        
        # Check if country exists in race
        if requested_country not in self.physics_world.racers:
            logger.warning(f"❌ Country {requested_country} not found in race")
            return
        
        # Assign user to team
        self.user_assignments[username] = requested_country
        self.last_join_time[username] = current_time
        self._on_real_activity()
        
        # Visual feedback: floating text on the country's lane
        racer = self.physics_world.racers[requested_country]
        lane_y = self.physics_world.game_area_top + (racer.lane * self.physics_world.lane_height) + (self.physics_world.lane_height // 2)
        
        self.spawn_floating_text(
            f"@{username} joined!",
            100,  # x position (start of lane)
            lane_y,
            (220, 220, 220)
        )
        
        logger.info(f"✅ {username} joined {requested_country} (keyword: {keyword})")

    def _handle_user_join(self, username: str) -> None:
        """
        Handle viewer entering the livestream with Visual Welcome effect.
        Spawns a welcome FloatingText with Neon Cyan, Elastic Pulse, centered above flags.
        Cooldown: max 2 simultaneous welcomes, 1.5s between spawns.
        """
        import time
        from .config import (
            SCREEN_WIDTH,
            WELCOME_COOLDOWN,
            MAX_SIMULTANEOUS_WELCOMES,
            WELCOME_TEXT_Y,
            WELCOME_TEXT_LIFESPAN,
            WELCOME_FONT_SIZE,
            COLOR_NEON_CYAN,
        )

        current_time = time.time()

        # Count active welcome messages
        active_welcomes = sum(
            1 for t in self.floating_texts
            if getattr(t, "is_welcome", False) and t.is_alive
        )

        # Cooldown: max 2 simultaneous OR 1.5s between spawns
        last_welcome = getattr(self, "_last_welcome_spawn_time", 0.0)
        if active_welcomes >= MAX_SIMULTANEOUS_WELCOMES:
            return
        if current_time - last_welcome < WELCOME_COOLDOWN:
            return

        self._last_welcome_spawn_time = current_time

        # Spawn welcome FloatingText: center, above flags, Neon Cyan, Elastic Pulse
        welcome_text = FloatingText(
            text=f"WELCOME @{username}!",
            x=SCREEN_WIDTH / 2,
            y=WELCOME_TEXT_Y,
            color=COLOR_NEON_CYAN,
            dy=0.0,  # Stay in place (no float up)
            lifespan=WELCOME_TEXT_LIFESPAN,
            max_lifespan=WELCOME_TEXT_LIFESPAN,
            font_size=WELCOME_FONT_SIZE,
            is_welcome=True,
            pulse_ratio=0.4,  # Longer elastic pulse for welcome (40% of life)
        )
        self.floating_texts.append(welcome_text)

        if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
            # Remove oldest non-welcome first to preserve welcomes
            non_welcome = [t for t in self.floating_texts if not getattr(t, "is_welcome", False)]
            if len(non_welcome) > 0:
                self.floating_texts.remove(non_welcome[0])
            else:
                self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]

        logger.debug(f"👋 Welcome displayed for @{username}")

    async def _handle_follow_event(self, event: GameEvent) -> None:
        """Handle new follower: queue banner, register hype, log message."""
        username = event.username or "someone"
        self.notification_manager.enqueue(username)
        self.hype_manager.register_event()
        self._on_real_activity()
        self.messages.append((f"❤ {username} followed!", EventType.FOLLOW))
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]

    async def _handle_vote_event(self, event: GameEvent) -> None:
        """
        Handle vote event in COMMENT mode.
        User votes for a country by typing sigla/number in chat.
        
        Args:
            event: Vote event with country as content
        """
        from .config import COMMENT_POINTS_PER_MESSAGE, COMMENT_COOLDOWN
        import time
        
        # TRANSICIÓN: IDLE -> RACING al primer voto
        if self.game_state == 'IDLE':
            self._transition_to_racing()
            logger.info("🏁 Game state: RACING (first vote received!)")
        
        username = self.sanitize_username(event.username)
        country = event.content
        shortcut_used = event.extra.get("shortcut", "") if event.extra else ""
        
        # Anti-spam: cooldown between votes
        current_time = time.time()
        last_vote_time = getattr(self, '_last_vote_time', {})
        if username in last_vote_time:
            time_since_last = current_time - last_vote_time[username]
            if time_since_last < COMMENT_COOLDOWN:
                return  # Too soon, ignore
        
        self._on_real_activity()
        # Update last vote time
        if not hasattr(self, '_last_vote_time'):
            self._last_vote_time = {}
        self._last_vote_time[username] = current_time

        # 🔥 HYPE: Register engagement event
        self.hype_manager.register_event()

        # 🎥 Register vote for burst detection (micro-shake on vote bursts)
        self.screen_shaker.register_vote()
        
        # Update user assignment
        self.user_assignments[username] = country
        
        # 🔥 COMBO SYSTEM: Register this vote
        self.register_combo_event(country)
        
        # 🏆 CAPTAIN SYSTEM: Track points
        self._update_captain_points(username, country, COMMENT_POINTS_PER_MESSAGE)

        logger.debug(f"🗳️ VOTE: {username} → {country} ({shortcut_used})")
        
        # Apply movement to country's flag
        success, _ = self.physics_world.apply_gift_impulse(
            country=country,
            gift_name="Vote",
            diamond_count=COMMENT_POINTS_PER_MESSAGE
        )

        if success:
            # Visual feedback: small particle effect
            racer = self.physics_world.racers[country]
            pos = (racer.body.position.x, racer.body.position.y)
            
            self.emit_explosion(
                pos=pos,
                color=racer.color,
                count=5,
                power=0.6,
                diamond_count=COMMENT_POINTS_PER_MESSAGE
            )
            
            # Optional: floating text feedback at top (limited)
            if len(self.floating_texts) < self.MAX_FLOATING_TEXTS // 2:
                from .config import SCREEN_WIDTH, FLOATING_TEXT_TOP_Y
                self.floating_texts.append(
                    FloatingText(
                        text=f"+{COMMENT_POINTS_PER_MESSAGE}",
                        x=SCREEN_WIDTH / 2,
                        y=FLOATING_TEXT_TOP_Y,
                        color=(0, 200, 255),  # Neon blue for votes
                        lifespan=30,
                        max_lifespan=30,
                        font_size=14,
                        dy=-1.0
                    )
                )
        
        # Add message to feed
        message = event.format_message()
        self.messages.append((message, event.type))
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]
    
    def handle_pygame_events(self) -> None:
        """Process Pygame input events."""
        try:
            events = pygame.event.get()
        except Exception as e:
            logger.exception("Error getting pygame events: %s", e)
            return
        
        for event in events:
            if event.type == pygame.QUIT:
                logger.info("🚪 Exiting: window closed (pygame.QUIT)")
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    now = time.time()
                    if not self._esc_quit_requested:
                        self._esc_quit_requested = True
                        self._esc_quit_time = now
                        logger.info("🚪 Press ESC again within 2s to quit")
                    elif (now - self._esc_quit_time) < self._esc_quit_window:
                        logger.info("🚪 Exiting: ESC confirmed")
                        self.running = False
                    else:
                        self._esc_quit_requested = True
                        self._esc_quit_time = now
                        logger.info("🚪 Press ESC again within 2s to quit")
                elif event.key == pygame.K_c:
                    pass  # disabled (use R to reset)
                elif event.key == pygame.K_r:
                    if self.blackout_active:
                        self._recharge_blackout()
                    else:
                        self._return_to_idle()
                        logger.info("Race reset to IDLE!")
                elif event.key == pygame.K_t:  # Test mode — burst of 5 Rosas
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")

                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
                    for _ in range(5):
                        self.queue.put_nowait(GameEvent(
                            type=EventType.GIFT,
                            username=f"test_{country.lower()}",
                            content="Rosa",
                            extra={"diamond_count": 1, "count": 1},
                        ))
                    self._on_real_activity()
                    self.hype_manager.register_event()

                    logger.info(f"TEST: {country} received 5x Rosa (combo test)")
                    
                elif event.key == pygame.K_y:  # Y = Test Big Gift
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")

                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
                    diamonds = random.randint(25, 50)

                    self.physics_world.apply_gift_impulse(
                        country=country,
                        gift_name="Big Test Gift",
                        diamond_count=diamonds
                    )
                    self._on_real_activity()
                    self.hype_manager.register_event()

                    logger.info(f"TEST BIG: {country} received {diamonds}💎")

                elif event.key == pygame.K_1:  # 1 = Test Vote/Rosa (depends on mode)
                    from .config import GAME_MODE
                    
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
                    
                    if GAME_MODE == "COMMENT":
                        # Test vote for country
                        test_username = f"TestVoter{int(time.time() * 1000) % 1000}"
                        
                        vote_event = GameEvent(
                            type=EventType.VOTE,
                            username=test_username,
                            content=country,
                            extra={"shortcut": "1"}
                        )
                        
                        try:
                            self.queue.put_nowait(vote_event)
                            logger.info(f"TEST VOTE: {test_username} → {country}")
                        except Exception as e:
                            logger.error(f"Error adding test vote: {e}")
                    else:
                        # Test Rosa effect (GIFT mode)
                        result = self.physics_world.apply_gift_effect("Rosa", country)
                        logger.info(f"TEST ROSA: {country}")
                        
                        # Spawn floating text
                        if result['effect'] == 'advance':
                            racer = self.physics_world.racers[country]
                            self.spawn_floating_text(
                                "+5m", 
                                racer.body.position.x, 
                                racer.body.position.y,
                                COLOR_TEXT_POSITIVE
                            )

                elif event.key == pygame.K_2:  # 2 = Test Vote/Pesa (depends on mode)
                    from .config import GAME_MODE
                    
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
                    
                    if GAME_MODE == "COMMENT":
                        # Test vote for country
                        test_username = f"TestVoter{int(time.time() * 1000) % 1000}"
                        
                        vote_event = GameEvent(
                            type=EventType.VOTE,
                            username=test_username,
                            content=country,
                            extra={"shortcut": "2"}
                        )
                        
                        try:
                            self.queue.put_nowait(vote_event)
                            logger.info(f"TEST VOTE: {test_username} → {country}")
                        except Exception as e:
                            logger.error(f"Error adding test vote: {e}")
                    else:
                        # Test Pesa effect (GIFT mode)
                        result = self.physics_world.apply_gift_effect("Pesa", country)
                        logger.info(f"TEST PESA: attacking leader")
                        
                        # Spawn floating text on the affected target (leader)
                        if result['effect'] == 'setback':
                            target = result['target']
                            if target in self.physics_world.racers:
                                racer = self.physics_world.racers[target]
                                self.spawn_floating_text(
                                    "-10m", 
                                    racer.body.position.x, 
                                    racer.body.position.y,
                                    COLOR_TEXT_NEGATIVE
                                )
                    
                elif event.key == pygame.K_3:  # 3 = Test Vote/Helado (depends on mode)
                    from .config import GAME_MODE
                    
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
                    
                    if GAME_MODE == "COMMENT":
                        # Test vote for country
                        test_username = f"TestVoter{int(time.time() * 1000) % 1000}"
                        
                        vote_event = GameEvent(
                            type=EventType.VOTE,
                            username=test_username,
                            content=country,
                            extra={"shortcut": "3"}
                        )
                        
                        try:
                            self.queue.put_nowait(vote_event)
                            logger.info(f"TEST VOTE: {test_username} → {country}")
                        except Exception as e:
                            logger.error(f"Error adding test vote: {e}")
                    else:
                        # Test Helado effect (GIFT mode)
                        from .config import FLOATING_TEXT_TOP_Y
                        result = self.physics_world.apply_gift_effect("Helado", country)
                        logger.info(f"TEST HELADO: freezing leader")

                        if result['effect'] == 'freeze':
                            target = result['target']
                            if target in self.physics_world.racers:
                                self.screen_shaker.impact_shake()
                                self.audio_manager.play_freeze_sound()
                                target_racer = self.physics_world.racers[target]
                                pos = (target_racer.body.position.x, target_racer.body.position.y)
                                self.emit_explosion(pos=pos, color=(100, 200, 255), count=35, power=1.0, diamond_count=0)
                                self.floating_texts.append(FloatingText(
                                    text=f"** {target} FROZEN! **",
                                    x=SCREEN_WIDTH / 2,
                                    y=FLOATING_TEXT_TOP_Y,
                                    color=COLOR_TEXT_FREEZE,
                                    dy=-0.8,
                                    lifespan=180,
                                    max_lifespan=180,
                                    font_size=18,
                                ))
                                self.hype_manager.register_event()

                elif event.key == pygame.K_w:  # disabled
                    pass

                elif event.key == pygame.K_j:  # disabled
                    pass

                # K (stress test) disabled
                
                elif event.key == pygame.K_f:  # disabled
                    pass
                
                elif event.key == pygame.K_g:  # disabled
                    pass
                
                elif event.key == pygame.K_v:  # disabled
                    pass

                elif event.key == pygame.K_l:  # L = Simulate likes (retention bar; production uses real LIKE events)
                    self.add_likes(LIKES_SIMULATED_PER_KEY)

                elif event.key == pygame.K_m:  # M = Toggle BGM
                    muted = self.audio_manager.toggle_bgm()
                    status = "OFF" if muted else "ON"
                    self._audio_toast_text = f"BGM: {status}"
                    self._audio_toast_timer = 3.0

                elif event.key == pygame.K_n:  # N = Toggle SFX
                    muted = self.audio_manager.toggle_sfx()
                    status = "OFF" if muted else "ON"
                    self._audio_toast_text = f"SFX: {status}"
                    self._audio_toast_timer = 3.0

                elif event.key == pygame.K_s:  # S = Lunar Gravity test
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                    self._activate_lunar_gravity()
                    logger.info("[LUNAR] Manually triggered via key S")

                elif event.key == pygame.K_o:  # O = Toggle Blackout Mode (test)
                    if self.blackout_active:
                        self.blackout_active = False
                        self.blackout_alpha = 0
                    else:
                        self._activate_blackout()

                elif event.key == pygame.K_p:  # disabled
                    pass

                elif event.key == pygame.K_a:  # A = Toggle Auto-Pilot
                    self._autopilot_enabled = not self._autopilot_enabled
                    if not self._autopilot_enabled:
                        self._autopilot_active = False
                    status = "ON" if self._autopilot_enabled else "OFF"
                    logger.info("[AutoPilot] Toggled: %s", status)
                    self.spawn_floating_text(f"Auto-Pilot {status}", 0, 0, (0, 200, 255))

                elif event.key == pygame.K_h:  # H = Toggle ranking panel + refresh
                    self._show_ranking_panel = not self._show_ranking_panel
                    if self._show_ranking_panel:
                        asyncio.create_task(self._fetch_global_ranking())
                    logger.info(f"🏆 Ranking panel: {'ON' if self._show_ranking_panel else 'OFF'}")

                elif event.key == pygame.K_b:  # B = Toggle HUD (Broadcast mode)
                    self.hud_visible = not self.hud_visible
                    logger.info("📺 HUD: %s", "ON" if self.hud_visible else "OFF")

                elif event.key == pygame.K_z:  # disabled
                    pass

    def _update_captain_points(self, username: str, country: str, points: int) -> None:
        """
        Update session points and check for new captain.
        
        Args:
            username: User who sent the gift
            country: Country team the user belongs to
            points: Diamond count from the gift
        """
        # Initialize country tracking if needed
        if country not in self.session_points:
            self.session_points[country] = {}
        
        # Add points to user's total
        if username not in self.session_points[country]:
            self.session_points[country][username] = 0
        
        self.session_points[country][username] += points
        
        # Check for new captain
        old_captain = self.current_captains.get(country, "")
        new_captain = self.get_mvp_for_country(country)
        
        if new_captain and new_captain != old_captain:
            self.current_captains[country] = new_captain
            self._announce_new_captain(country, new_captain, old_captain)
            logger.info(f"👑 NEW CAPTAIN: {new_captain} leads {country} with {self.session_points[country][new_captain]}💎")

    def get_mvp_for_country(self, country: str) -> str:
        """
        Get the MVP (most points) for a specific country.
        In case of tie, returns the first user to reach that score.
        
        Args:
            country: Country to check
            
        Returns:
            Username of MVP, or empty string if no contributions
        """
        if country not in self.session_points:
            return ""
        
        country_points = self.session_points[country]
        if not country_points:
            return ""
        
        # Find max points
        max_points = max(country_points.values())
        
        # Find first user to reach max points (maintains insertion order)
        for username, points in country_points.items():
            if points == max_points:
                return username
        
        return ""

    def _announce_new_captain(self, country: str, new_captain: str, old_captain: str) -> None:
        """
        Trigger visual effect when captain changes.
        Creates a vibrant "dopamine" floating text that jumps upward.
        
        Args:
            country: Country that got a new captain
            new_captain: Username of new captain
            old_captain: Username of previous captain (can be empty)
        """
        # Find racer position for floating text
        if country not in self.physics_world.racers:
            return
        
        from .config import SCREEN_WIDTH, FLOATING_TEXT_TOP_Y
        # Floating text for new captain at top
        crown_text = f"@{new_captain}"
        self.floating_texts.append(
            FloatingText(
                text=crown_text,
                x=SCREEN_WIDTH / 2,
                y=FLOATING_TEXT_TOP_Y,
                color=(255, 215, 0),  # Gold
                lifespan=80,
                max_lifespan=80,
                font_size=18,
                dy=-1.0
            )
        )
        self.floating_texts.append(
            FloatingText(
                text="NEW CAPTAIN!",
                x=SCREEN_WIDTH / 2,
                y=FLOATING_TEXT_TOP_Y + 20,
                color=(255, 255, 100),  # Bright yellow
                lifespan=60,
                max_lifespan=60,
                font_size=14,
                dy=-1.0
            )
        )
        
        # 🎥 Trigger screen shake for impact
        self.screen_shaker.micro_shake()
        
        # Set timer for captain highlight effect
        self.captain_change_timer[country] = 90  # 1.5 seconds at 60fps

    # --- Audience Milestone constants ---
    _AUDIENCE_MILESTONES: dict = {
        15:  "SALA ACTIVA",
        30:  "OBJETIVO ALCANZADO",
        50:  "SALA LLENA",
        100: "RECORD HISTORICO",
    }

    # --- Lunar Gravity scaling per milestone ---
    _LUNAR_MILESTONE_PARAMS: dict = {
        15:  {"amplitude": 6.0,  "elasticity": 0.85, "duration": 30.0},
        30:  {"amplitude": 9.0,  "elasticity": 0.88, "duration": 35.0},
        50:  {"amplitude": 13.0, "elasticity": 0.93, "duration": 40.0},
        100: {"amplitude": 20.0, "elasticity": 0.97, "duration": 45.0},
    }

    def _check_audience_milestones(self, count: int) -> None:
        """Fire audience milestone effects when viewer count crosses a threshold."""
        # First call: capture baseline and silently mark all pre-existing milestones
        if self._viewer_count_baseline < 0:
            self._viewer_count_baseline = count
            for threshold in self._AUDIENCE_MILESTONES:
                if threshold <= count:
                    self._milestones_triggered.add(threshold)
            self._highest_milestone_reached = count
            logger.info("[MILESTONE] Baseline set to %d viewers; pre-marked %s",
                        count, sorted(t for t in self._AUDIENCE_MILESTONES if t <= count))
            return  # no effects for initial state

        # Only advance, never retreat
        if count <= self._highest_milestone_reached:
            return
        self._highest_milestone_reached = count

        for threshold, message in sorted(self._AUDIENCE_MILESTONES.items()):
            if threshold <= count and threshold not in self._milestones_triggered:
                self._milestones_triggered.add(threshold)
                self._trigger_audience_milestone(threshold, message)

    def _trigger_audience_milestone(self, count: int, message: str) -> None:
        """Execute all bonus effects for a milestone trigger."""
        # Banner
        self._milestone_banner_count = count
        self._milestone_banner_msg = message
        self._milestone_banner_timer = 6.0

        # Bonus: restore blackout
        self.blackout_alpha = 0

        # Bonus: thaw all frozen countries
        self.physics_world.frozen_countries.clear()

        # Bonus: haptic shake
        self.screen_shaker.impact_shake()

        # Bonus: floating text
        self.spawn_floating_text("BONO DE ENERGIA ACTIVADO", 0, 0, (255, 215, 0))

        # TTS
        if TTS_ENABLED:
            self.audio_manager.announce_custom(
                f"Atencion, hemos alcanzado un hito de {count} cientificos en el laboratorio"
            )

        # 🌙 Trigger Lunar Gravity scaled to milestone level
        params = self._LUNAR_MILESTONE_PARAMS.get(count, {})
        self._activate_lunar_gravity(
            duration   = params.get("duration",   self.LUNAR_DURATION),
            amplitude  = params.get("amplitude",  None),
            elasticity = params.get("elasticity", None),
            extend     = True,
        )
        self.screen_shaker.meteor_shake()

    def update(self, dt: float) -> None:
        """Update physics and particles."""
        # 🚪 Reset ESC “press again to quit” if window expired
        if self._esc_quit_requested and (time.time() - self._esc_quit_time) >= self._esc_quit_window:
            self._esc_quit_requested = False
        
        # 🎬 SLOW MOTION: Apply time dilation during victory sequence
        original_dt = dt
        if self.slow_motion_active:
            dt *= self.slow_motion_factor
        
        # 🏆 Update victory sequence (uses original dt for timing)
        if self.victory_sequence_active:
            self._update_victory_sequence(original_dt)
        
        # Update captain change timers
        for country in list(self.captain_change_timer.keys()):
            self.captain_change_timer[country] -= 1
            if self.captain_change_timer[country] <= 0:
                del self.captain_change_timer[country]

        # Fixed timestep physics: run at PHYSICS_FIXED_HZ regardless of render FPS
        self._physics_accumulator += dt
        if self._physics_accumulator > self._max_physics_catchup:
            self._physics_accumulator = self._max_physics_catchup
        while self._physics_accumulator >= self._fixed_dt:
            self.physics_world.update(self._fixed_dt)
            self._physics_accumulator -= self._fixed_dt

        # ❄️ Process unfreeze events — ice block 'shatter' on timer end
        for country in self.physics_world.just_unfrozen:
            racer = self.physics_world.racers.get(country)
            if racer:
                pos = (racer.body.position.x, racer.body.position.y)
                self.screen_shaker.impact_shake()
                self.emit_explosion(pos=pos, color=(180, 240, 255), count=40, power=1.2, diamond_count=0)
                self.spawn_floating_text(f"{country} THAWED!", 0, 0, (180, 240, 255))

        self.update_particles(dt)
        self.update_floating_texts()
        self.notification_manager.update()

        # 🌹 Rosa combo multiplier decay
        self._decay_rosa_combos()

        # 🌙 Lunar Gravity timer & overlay fade
        if self._lunar_active:
            self._lunar_timer -= dt
            target_alpha = 55
            self._lunar_overlay_alpha = min(
                target_alpha,
                self._lunar_overlay_alpha + int(self.LUNAR_FADE_SPEED * dt)
            )
            if self._lunar_timer <= 0.0:
                self._deactivate_lunar_gravity()
        else:
            self._lunar_overlay_alpha = max(
                0,
                self._lunar_overlay_alpha - int(self.LUNAR_FADE_SPEED * dt)
            )

        # 🔥 Hype Mode state machine
        prev_hype = self.hype_manager.is_hype_active
        self.hype_manager.update(dt)
        if self.hype_manager.is_hype_active and not prev_hype:
            # Hype just activated
            self.physics_world.hype_speed_multiplier = HYPE_PHYSICS_MULTIPLIER
            if self.background_manager:
                self.background_manager.activate_hype_mode()
            self.screen_shaker.impact_shake()
            self._emit_hype_activation_text()
        elif not self.hype_manager.is_hype_active and prev_hype:
            # Hype just ended → cooldown
            self.physics_world.hype_speed_multiplier = 1.0
            if self.background_manager:
                self.background_manager.deactivate_hype_mode()

        # Hype micro-shake every ~3 seconds while active
        if self.hype_manager.is_hype_active:
            self._hype_micro_shake_timer -= dt
            if self._hype_micro_shake_timer <= 0.0:
                self._hype_micro_shake_timer = 3.0
                self.screen_shaker.micro_shake()

        # 🌑 Blackout Mode update
        from .config import (BLACKOUT_MAX_ALPHA, BLACKOUT_INCREASE_PER_SEC,
                             BLACKOUT_HYPE_INTERVAL, BLACKOUT_HYPE_CHANCE)
        if self.blackout_active:
            self._blackout_increase_timer += dt
            if self._blackout_increase_timer >= 1.0:
                self._blackout_increase_timer -= 1.0
                self.blackout_alpha = min(BLACKOUT_MAX_ALPHA,
                                          self.blackout_alpha + BLACKOUT_INCREASE_PER_SEC)
        if not self.blackout_active and self.hype_manager.is_hype_active:
            self._blackout_hype_timer += dt
            if self._blackout_hype_timer >= BLACKOUT_HYPE_INTERVAL:
                self._blackout_hype_timer = 0.0
                if random.random() < BLACKOUT_HYPE_CHANCE:
                    self._activate_blackout()
        if self._blackout_restored_timer > 0:
            self._blackout_restored_timer -= dt

        # 🌌 Update parallax background
        if self.background_manager:
            self.background_manager.update(dt)
        
        # 🎥 Update screen shaker
        self.screen_shaker.update(dt)

        # Milestone banner countdown
        if self._milestone_banner_timer > 0:
            self._milestone_banner_timer -= dt

        # 🌠 Update Meteor Shower meteors (position, trail, flag collisions)
        self._update_meteors(dt)
        
        # 🌟 Update leader glow animation
        self.leader_glow_time += dt
        
        # 📢 Rotate CTA banner every 8 seconds (COMMENT mode, RACING)
        from .config import GAME_MODE
        if GAME_MODE == "COMMENT" and self.game_state == 'RACING':
            now = time.time()
            if self.cta_last_rotation_time == 0:
                self.cta_last_rotation_time = now
            elif now - self.cta_last_rotation_time >= self.cta_rotation_interval:
                self.cta_last_rotation_time = now
                self.cta_message_index = (self.cta_message_index + 1) % 4  # 4 message variants
        
        # 🌟 Update spotlight position with smooth interpolation
        if self.game_state == 'RACING':
            leader_info = self.physics_world.get_leader()
            if leader_info and leader_info[0] in self.physics_world.racers:
                leader_racer = self.physics_world.racers[leader_info[0]]
                self.spotlight_target_pos = (
                    float(leader_racer.body.position.x),
                    float(leader_racer.body.position.y)
                )
            
            # Lerp (smooth interpolation) towards target
            lerp_factor = min(1.0, self.spotlight_lerp_speed * dt)
            self.spotlight_current_pos = (
                self.spotlight_current_pos[0] + (self.spotlight_target_pos[0] - self.spotlight_current_pos[0]) * lerp_factor,
                self.spotlight_current_pos[1] + (self.spotlight_target_pos[1] - self.spotlight_current_pos[1]) * lerp_factor
            )
            
            # 🌈 Update motion trails for ON FIRE countries (disabled in lite-particle mode)
            if not MOTOGP_LITE_PARTICLES:
                self._update_motion_trails(dt)
            
            # Update combo flashes
            self._update_combo_flashes(dt)
            
            # 🏁 Check for final stretch
            self._check_final_stretch()
            
            # Update final stretch animation timer
            if self.final_stretch_triggered:
                self.final_stretch_time += dt
            
            # 🎤 Check for overtakes and close races (TTS announcements)
            self._check_race_events(dt)
        
        # Update disaster flash + title card
        if self._disaster_flash_alpha > 0:
            self._disaster_flash_time += dt
            progress = self._disaster_flash_time / self._disaster_flash_dur
            if progress >= 1.0:
                self._disaster_flash_alpha = 0.0
                self._disaster_flash_time = 0.0
            else:
                self._disaster_flash_alpha = 220.0 * (1.0 - progress)

        if self._disaster_title_timer > 0:
            self._disaster_title_timer -= dt

        # Update victory flash effect (fade out) - non-blocking, runs independently
        if self.victory_flash_alpha > 0:
            self.victory_flash_time += dt
            # Fade out over 0.3 seconds
            fade_progress = self.victory_flash_time / self.victory_flash_duration if self.victory_flash_duration > 0 else 1.0
            if fade_progress >= 1.0:
                self.victory_flash_alpha = 0.0
                self.victory_flash_time = 0.0
            else:
                # Linear fade out
                self.victory_flash_alpha = 255.0 * (1.0 - fade_progress)
        
        # Update trail particles for all flags
        if self.game_state == 'RACING':
            for country, racer in self.physics_world.get_racers().items():
                x = float(racer.body.position.x) if math.isfinite(racer.body.position.x) else self.physics_world.start_x
                y = float(racer.body.position.y) if math.isfinite(racer.body.position.y) else (racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2)
                self.particle_manager.update_trail(country, (x, y), racer.color, dt)
        
        # Update idle animation timer
        if self.game_state == 'IDLE':
            self.idle_animation_time += dt
            self.ranking_3d_animation_time += dt * 0.5  # Slower animation for 3D effect
        elif self._show_ranking_panel:
            self.ranking_3d_animation_time += dt * 0.5  # Keep glow animated during RACING panel
            
            # 🏆 Load global ranking on first IDLE state (non-blocking)
            if not self.global_rank_data and not self.global_rank_loading and self.global_rank_last_update == 0:
                self._trigger_ranking_update()
        
        # 🎯 LEADER CHANGE DETECTION (VFX)
        leader_info = self.physics_world.get_leader()
        current_leader = leader_info[0] if leader_info else None
        
        if current_leader != self.last_leader_name and current_leader is not None:
            # ¡Nuevo líder! Activar efecto "pop"
            self.leader_pop_timer = 10  # 10 frames de animación
            self.last_leader_name = current_leader
        
        # Decrementar timer del efecto pop
        if self.leader_pop_timer > 0:
            self.leader_pop_timer -= 1
        
        # Auto stress test (if enabled)
        if AUTO_STRESS_TEST:
            self._auto_stress_test(dt)
        
        # Manual stress test (key K): inject VOTE/GIFT @ 20/sec
        if self._stress_test_active:
            self._manual_stress_test_inject()
        
        # FPS monitoring (if any stress test enabled)
        if AUTO_STRESS_TEST or self._stress_test_active:
            self._monitor_performance(dt)
        
        # Update winner celebration animation
        if self.physics_world.race_finished and self.physics_world.winner:
            # ☁️ CLOUD SYNC: Sync to Supabase on first detection (non-blocking)
            if not self.race_synced and self.winner_animation_time < dt * 2:
                self.race_synced = True
                
                # 🎥 BIG VICTORY SHAKE!
                self.screen_shaker.big_impact_shake()
                
                winner_country = self.physics_world.winner
                winner_captain = self.current_captains.get(winner_country, "Unknown")
                winner_points = self.session_points.get(winner_country, {}).get(winner_captain, 0)
                
                # 🏆 TRIGGER EPIC VICTORY SEQUENCE
                self._trigger_victory_sequence(winner_country, winner_captain)
                
                # Async sync to cloud + update ranking (runs in background, won't block rendering)
                asyncio.create_task(
                    self._sync_and_update_ranking(
                        country=winner_country,
                        winner_name=winner_captain,
                        total_diamonds=winner_points,
                        streamer_name=self.streamer_name
                    )
                )
                logger.info(f"☁️ Queued cloud sync: {winner_country} - {winner_captain} ({winner_points}💎)")
            
            self.winner_animation_time += dt
            
            # Pulse effect (breathing animation)
            pulse_speed = 4.0
            self.winner_scale_pulse = 1.0 + 0.3 * math.sin(self.winner_animation_time * pulse_speed * math.pi)
            
            # Glow pulsing
            self.winner_glow_alpha = self._safe_int(128 + 127 * math.sin(self.winner_animation_time * 3.0 * math.pi), 128)
            
            # Continuous sparkles around winner
            if self.winner_animation_time % 0.1 < dt:
                winner_racer = self.physics_world.racers[self.physics_world.winner]
                raw_x = winner_racer.body.position.x
                raw_y = winner_racer.body.position.y
                
                x = float(raw_x) if math.isfinite(raw_x) else self.physics_world.finish_line_x
                y = float(raw_y) if math.isfinite(raw_y) else (winner_racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2)
                
                self.emit_explosion(
                    pos=(x, y),
                    color=(255, 215, 0),
                    count=5,
                    power=0.5,
                    diamond_count=100
                )
            
            # Auto-return to IDLE after 10 seconds (era 5)
            if self.winner_animation_time >= 10.0:
                logger.info(f"⏱️ Returning to IDLE after 10s")
                self._return_to_idle()
        else:
            # Reset animation state when no winner
            self.winner_animation_time = 0.0
            self.winner_scale_pulse = 1.0
            self.winner_glow_alpha = 0
            # ☁️ Reset cloud sync flag when race resets
            self.race_synced = False

        # 🔊 Decay audio toast timer
        if self._audio_toast_timer > 0:
            self._audio_toast_timer = max(0.0, self._audio_toast_timer - dt)

        # ⚡ Hype Timer (Disaster Countdown)
        if HYPE_TIMER_ENABLED:
            self._update_hype_timer()

    def render(self) -> None:
        """Render all visual elements."""
        # Track frame for FPS calculation
        self._frame_count += 1
        current_time = time.time()
        if self._frame_count > 0:
            elapsed = current_time - self._last_fps_check_time
            if elapsed >= 1.0:  # Calculate FPS every second
                fps = self._frame_count / elapsed
                self._fps_samples.append(fps)
                self._fps_sample_times.append(current_time)
                self._frame_count = 0
                self._last_fps_check_time = current_time
        
        from .config import GAME_MARGIN
        
        # Draw outer background (window margin)
        self.screen.blit(self.outer_background, (0, 0))
        
        # 🌌 Render parallax background FIRST (behind everything)
        if self.background_manager:
            try:
                self.background_manager.render(self.render_surface)
            except Exception as e:
                logger.exception("Error rendering background: %s", e)
                # Fallback to static gradient on error
                self.render_surface.blit(self.gradient_background, (0, 0))
        else:
            # Fallback to static gradient if no background manager
            self.render_surface.blit(self.gradient_background, (0, 0))
        
        # 🌙 Lunar Gravity: space atmosphere overlay
        if self._lunar_overlay_alpha > 0:
            _lunar_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            _lunar_surf.fill((15, 0, 50, self._lunar_overlay_alpha))
            self.render_surface.blit(_lunar_surf, (0, 0))

        self._render_balls()
        self._render_trails()  # Render trails before particles (behind)
        if not MOTOGP_LITE_PARTICLES:
            self._render_motion_trails()  # 🌈 Neon motion trails for ON FIRE state
        self._render_particles()
        self._render_meteors()
        self._render_floating_texts()
        self._render_combo_flashes()  # ✨ Flash effects on combo level up
        self._render_blackout_overlay()  # 🌑 Blackout Mode (between particles and notifications)
        self._render_milestone_banner()
        self.notification_manager.render(self.render_surface)
        if self.hud_visible:
            self._render_header()
        # Draw CTA first (when COMMENT+RACING) so likes bar hint "Dale like o tap..." is drawn on top and visible
        from .config import GAME_MODE
        if GAME_MODE == "COMMENT" and self.game_state == 'RACING' and not HYPE_TIMER_ENABLED and not MOTOGP_MODE:
            self._draw_permanent_cta(self.render_surface)
        self._render_likes_bar()
        self._render_leaderboard()

        # 🏁 Render FINAL STRETCH announcement
        self._render_final_stretch_announcement()
        
        # 🧪 Stress test indicator (key K)
        if self._stress_test_active:
            self._render_stress_test_banner()

        # ⚡ Hype Timer overlay (respects HUD visibility)
        if HYPE_TIMER_ENABLED and self.hud_visible:
            self._render_hype_timer(self.render_surface)

        # Render shortcuts panel in COMMENT mode (solo durante RACING)
        import time as time_module
        
        if GAME_MODE == "COMMENT" and self.game_state == "RACING":
            
            # Show fade-out HUD overlay for first 3 seconds
            if self.race_start_time:
                elapsed = time_module.time() - self.race_start_time
                if elapsed < self.hud_fade_duration:
                    # Calculate fade alpha (1.0 -> 0.0 over 3 seconds)
                    fade_progress = elapsed / self.hud_fade_duration
                    overlay_alpha = int(255 * (1.0 - fade_progress))
                    if overlay_alpha > 20:  # Only render if visible
                        self._render_race_start_hud(overlay_alpha)
        
        # Render IDLE screen on top if in IDLE state
        if self.game_state == 'IDLE':
            self._render_idle_screen()
        elif self._show_ranking_panel:
            # Dim the race behind the ranking panel so it's clearly readable
            _overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            _overlay.fill((0, 0, 0, 160))
            self.render_surface.blit(_overlay, (0, 0))
            self._render_global_ranking_futuristic()

        # Render disaster flash + title card (crimson burst on hype detonation)
        if self._disaster_flash_alpha > 0:
            self._render_disaster_flash()
        if self._disaster_title_timer > 0:
            self._render_disaster_title()

        # Render victory flash effect (white screen flash)
        if self.victory_flash_alpha > 0:
            self._render_victory_flash()
        
        # 🏆 Render EPIC VICTORY SEQUENCE (on top of almost everything)
        if self.victory_sequence_active:
            self._render_victory_sequence()
    
        # 🎥 Apply screen shake offset when blitting to window
        shake_offset = self.screen_shaker.current_offset
        blit_x = GAME_MARGIN + int(shake_offset[0])
        blit_y = GAME_MARGIN + int(shake_offset[1])
        
        # 🎬 Apply subtle camera zoom during victory sequence (scale() not smoothscale for 60 FPS)
        if self.victory_sequence_active and self.victory_zoom_level > 1.01:
            zoom = min(self.victory_zoom_level, 1.15)  # Cap at 15% zoom
            scaled_width = int(SCREEN_WIDTH * zoom)
            scaled_height = int(SCREEN_HEIGHT * zoom)
            scaled_surface = pygame.transform.scale(
                self.render_surface, (scaled_width, scaled_height)
            )
            offset_x = (scaled_width - SCREEN_WIDTH) // 2
            offset_y = (scaled_height - SCREEN_HEIGHT) // 2
            self.screen.blit(scaled_surface, (blit_x - offset_x, blit_y - offset_y))
        else:
            self.screen.blit(self.render_surface, (blit_x, blit_y))

        # 🔊 Audio toast overlay (always rendered on top of everything)
        if self._audio_toast_timer > 0:
            self._render_audio_toast()

        pygame.display.flip()

    def _activate_blackout(self) -> None:
        """Activate Blackout Mode at the initial darkness level."""
        from .config import BLACKOUT_ENABLED, BLACKOUT_INITIAL_ALPHA
        if not BLACKOUT_ENABLED:
            return
        self.blackout_active = True
        self.blackout_alpha = BLACKOUT_INITIAL_ALPHA
        self._blackout_increase_timer = 0.0

    def _recharge_blackout(self) -> None:
        """Reduce blackout darkness; deactivate when fully recharged."""
        from .config import BLACKOUT_RECHARGE_DECREASE
        self.blackout_alpha = max(0, self.blackout_alpha - BLACKOUT_RECHARGE_DECREASE)
        if self.blackout_alpha == 0:
            self.blackout_active = False
            self._blackout_restored_timer = 3.0

        # Thaw: each Rosa recharge also reduces all active freeze timers by 1.5 s
        THAW_REDUCTION = 1.5
        thawed = [c for c, t in self.physics_world.frozen_countries.items()
                  if t - THAW_REDUCTION <= 0]
        for c in thawed:
            del self.physics_world.frozen_countries[c]
            self.physics_world.just_unfrozen.append(c)
        for c in list(self.physics_world.frozen_countries):
            if c not in thawed:
                self.physics_world.frozen_countries[c] -= THAW_REDUCTION

    def _update_rosa_combo(self, country: str, now: float) -> None:
        """Record a Rosa gift, recalculate combo level, apply multiplier and visuals."""
        tracker = self._rosa_tracker.setdefault(country, [])
        tracker.append(now)
        cutoff = now - self.ROSA_COMBO_WINDOW
        self._rosa_tracker[country] = [t for t in tracker if t >= cutoff]

        count = len(self._rosa_tracker[country])
        new_level = 0
        new_mult  = 1.0
        for min_count, level, mult in self.ROSA_COMBO_THRESHOLDS:
            if count >= min_count:
                new_level = level
                new_mult  = mult
                break

        old_level = self._rosa_combo_level.get(country, 0)
        self._rosa_combo_level[country] = new_level

        if self.physics_world:
            self.physics_world.rosa_combo_multiplier = new_mult

        if new_level > old_level:
            self._show_rosa_combo_visuals(country, new_level, new_mult)

    def _show_rosa_combo_visuals(self, country: str, level: int, multiplier: float) -> None:
        """Spawn FloatingText and optional particles near the country's flag."""
        racer = self.physics_world.racers.get(country) if self.physics_world else None
        if racer is None:
            return

        fx = racer.body.position.x
        fy = racer.body.position.y

        if level == 3:
            text    = "COMBO DE ENERGIA X2"
            color   = (255, 120, 0)
            fsize   = 22
            dur     = 90
            p_count = 15
            p_power = 1.5
        elif level == 2:
            text    = "COMBO X1.5"
            color   = (255, 200, 0)
            fsize   = 16
            dur     = 60
            p_count = 8
            p_power = 1.0
        else:  # level 1
            text    = "COMBO X1.2"
            color   = (200, 255, 200)
            fsize   = 14
            dur     = 45
            p_count = 0
            p_power = 0.0

        self.floating_texts.append(FloatingText(
            text=text, x=fx, y=fy - 20,
            color=color, lifespan=dur, max_lifespan=dur,
            font_size=fsize, dy=-1.2,
        ))

        if p_count > 0:
            self.emit_explosion(
                pos=(fx, fy),
                color=color,
                count=p_count,
                power=p_power,
            )

    def _activate_lunar_gravity(
        self,
        duration: float | None = None,
        amplitude: float | None = None,
        elasticity: float | None = None,
        extend: bool = False,
    ) -> None:
        """Start the Lunar Gravity event, or extend/upgrade it if already running."""
        effective_duration = duration if duration is not None else self.LUNAR_DURATION

        if self._lunar_active:
            if extend:
                self._lunar_timer = max(self._lunar_timer, effective_duration)
                if self.physics_world and (amplitude is not None or elasticity is not None):
                    self.physics_world.set_lunar_gravity(True, amplitude=amplitude, elasticity=elasticity)
                logger.info("[LUNAR] Timer extended to %.0fs", self._lunar_timer)
            return   # either extended or ignored

        self._lunar_active = True
        self._lunar_timer  = effective_duration

        if self.physics_world:
            self.physics_world.set_lunar_gravity(True, amplitude=amplitude, elasticity=elasticity)

        self.floating_texts.append(FloatingText(
            text=":: ADVERTENCIA: GRAVEDAD ZERO ::",
            x=SCREEN_WIDTH / 2,
            y=SCREEN_HEIGHT / 2 - 30,
            color=(180, 220, 255),
            lifespan=150, max_lifespan=150,
            font_size=22, dy=-0.2,
        ))

        self.screen_shaker.big_impact_shake()
        try:
            self.audio_manager.play_sfx("freeze")
        except Exception:
            pass
        logger.info("[LUNAR] Lunar Gravity activated (%.0fs)", effective_duration)

    def _deactivate_lunar_gravity(self) -> None:
        """End the Lunar Gravity event and restore normal physics."""
        self._lunar_active = False
        self._lunar_timer  = 0.0

        if self.physics_world:
            self.physics_world.set_lunar_gravity(False)

        self.floating_texts.append(FloatingText(
            text="GRAVEDAD RESTABLECIDA",
            x=SCREEN_WIDTH / 2,
            y=SCREEN_HEIGHT / 2,
            color=(100, 255, 160),
            lifespan=120, max_lifespan=120,
            font_size=18, dy=-0.5,
        ))
        logger.info("[LUNAR] Lunar Gravity deactivated")

    def _decay_rosa_combos(self) -> None:
        """Remove expired Rosa timestamps and reset multiplier if all combos cleared."""
        now    = time.perf_counter()
        cutoff = now - self.ROSA_COMBO_WINDOW
        any_active = False

        for country in list(self._rosa_tracker.keys()):
            self._rosa_tracker[country] = [t for t in self._rosa_tracker[country] if t >= cutoff]
            count = len(self._rosa_tracker[country])

            new_level = 0
            for min_count, level, _ in self.ROSA_COMBO_THRESHOLDS:
                if count >= min_count:
                    new_level = level
                    break

            self._rosa_combo_level[country] = new_level
            if new_level > 0:
                any_active = True

        if not any_active and self.physics_world:
            self.physics_world.rosa_combo_multiplier = 1.0

    def _render_blackout_overlay(self) -> None:
        """Render the Blackout Mode darkness overlay + HUD indicators."""
        if self.blackout_alpha <= 0 and self._blackout_restored_timer <= 0:
            return

        if self.blackout_alpha > 0:
            overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, self.blackout_alpha))
            self.render_surface.blit(overlay, (0, 0))

            # Flashing warning banner
            flash_alpha = int(180 + 75 * math.sin(pygame.time.get_ticks() * 0.008))
            flash_alpha = max(0, min(255, flash_alpha))
            warn_font = _get_font("Arial", 13, bold=True)
            warn_surf = warn_font.render(
                "\u00a1BAJA VISIBILIDAD - ACTIVEN LINTERNAS!",
                True, (255, 80, 0)
            )
            warn_surf.set_alpha(flash_alpha)
            warn_rect = warn_surf.get_rect(centerx=SCREEN_WIDTH // 2, y=290)
            self.render_surface.blit(warn_surf, warn_rect)

            # Energy indicator (below warning banner)
            pct = int((1.0 - self.blackout_alpha / 240) * 100)
            energy_font = _get_font("Arial", 15, bold=True)
            if pct > 40:
                energy_color = (0, 255, 100)
            elif pct > 15:
                energy_color = (255, 160, 0)
            else:
                energy_color = (255, 40, 40)
            energy_surf = energy_font.render(f"ENERGIA LUMINICA: {pct}%", True, energy_color)
            energy_rect = energy_surf.get_rect(centerx=SCREEN_WIDTH // 2, y=warn_rect.bottom + 8)
            self.render_surface.blit(energy_surf, energy_rect)

            # Energy bar at bottom
            bar_w = 200
            bar_h = 8
            bar_x = (SCREEN_WIDTH - bar_w) // 2
            bar_y = SCREEN_HEIGHT - 28
            fill_w = max(0, int(bar_w * (pct / 100)))

            pygame.draw.rect(self.render_surface, (40, 40, 40), (bar_x, bar_y, bar_w, bar_h), border_radius=4)
            pygame.draw.rect(self.render_surface, energy_color, (bar_x, bar_y, fill_w, bar_h), border_radius=4)
            pygame.draw.rect(self.render_surface, (120, 120, 120), (bar_x, bar_y, bar_w, bar_h), 1, border_radius=4)

            bar_label_font = _get_font("Arial", 11, bold=False)
            bar_label_surf = bar_label_font.render("Energ\u00eda", True, (200, 200, 200))
            bar_label_rect = bar_label_surf.get_rect(centerx=SCREEN_WIDTH // 2, bottom=bar_y - 3)
            self.render_surface.blit(bar_label_surf, bar_label_rect)

        # "VISION RESTABLECIDA" restored banner
        if self._blackout_restored_timer > 0:
            fade = min(1.0, self._blackout_restored_timer)
            r_alpha = int(255 * fade)
            r_font = _get_font("Arial", 16, bold=True)
            r_surf = r_font.render("VISION RESTABLECIDA", True, (255, 255, 150))
            r_surf.set_alpha(r_alpha)
            r_rect = r_surf.get_rect(centerx=SCREEN_WIDTH // 2, centery=SCREEN_HEIGHT // 2)
            self.render_surface.blit(r_surf, r_rect)

    def _render_milestone_banner(self) -> None:
        """Render a golden audience milestone banner at screen center."""
        if self._milestone_banner_timer <= 0:
            return

        GOLD      = (255, 215,   0)
        DARK_GOLD = (180, 140,   0)
        BG_COLOR  = ( 30,  20,   0, 200)

        line1 = "HITO DE AUDIENCIA"
        line2 = self._milestone_banner_msg + "  ::  GRAVEDAD CERO"

        font_big   = _get_font("Arial", 16, bold=True)
        font_small = _get_font("Arial", 12, bold=False)

        surf1 = font_big.render(line1, True, GOLD)
        surf2 = font_small.render(line2, True, DARK_GOLD)

        padding = 12
        w = max(surf1.get_width(), surf2.get_width()) + padding * 2
        h = surf1.get_height() + surf2.get_height() + padding * 2 + 4

        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2 - 60

        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        bg.fill(BG_COLOR)
        pygame.draw.rect(bg, GOLD, bg.get_rect(), 2)
        self.render_surface.blit(bg, (cx - w // 2, cy - h // 2))

        self.render_surface.blit(surf1, (cx - surf1.get_width() // 2, cy - h // 2 + padding))
        self.render_surface.blit(surf2, (cx - surf2.get_width() // 2, cy - h // 2 + padding + surf1.get_height() + 4))

    def _render_audio_toast(self) -> None:
        """Render a semi-transparent toast in the top-right corner showing BGM/SFX status."""
        if not self.screen or not self._audio_toast_text:
            return

        from .config import GAME_MARGIN, SCREEN_WIDTH

        font = _get_font(None, 22)
        text_surf = font.render(self._audio_toast_text, True, (255, 255, 255))
        padding_x, padding_y = 10, 6
        toast_w = text_surf.get_width() + padding_x * 2
        toast_h = text_surf.get_height() + padding_y * 2

        # Fade-out in the last 0.5 seconds
        alpha = 180
        if self._audio_toast_timer < 0.5:
            alpha = int(180 * (self._audio_toast_timer / 0.5))

        # Position: top-right of the game area on screen
        x = GAME_MARGIN + SCREEN_WIDTH - toast_w - 8
        y = GAME_MARGIN + 8

        bg_surf = pygame.Surface((toast_w, toast_h), pygame.SRCALPHA)
        bg_surf.fill((20, 20, 20, alpha))
        self.screen.blit(bg_surf, (x, y))

        text_alpha_surf = pygame.Surface(text_surf.get_size(), pygame.SRCALPHA)
        text_alpha_surf.blit(text_surf, (0, 0))
        text_alpha_surf.set_alpha(min(255, int(alpha * 255 / 180)))
        self.screen.blit(text_alpha_surf, (x + padding_x, y + padding_y))

    def _render_balls(self) -> None:
        """Render all flag racers with winner spotlight and leader glow."""
        # Draw lanes
        self._render_lanes()
        
        # Draw final stretch line (80% of track) – where stretch begins
        self._render_final_stretch_line()
        
        # Draw finish line
        self._render_finish_line()
        
        # Get winner and current leader
        winner = self.physics_world.winner if self.physics_world.race_finished else None
        leader_info = self.physics_world.get_leader()
        current_leader = leader_info[0] if leader_info else None
        
        # 🏍️ Fixed neon lane labels (behind everything)
        if MOTOGP_MODE:
            self._render_neon_lane_labels()

        # 🌟 Render leader spotlight FIRST (behind the leader flag)
        if current_leader and current_leader in self.physics_world.racers and not winner:
            self._render_leader_spotlight(self.physics_world.racers[current_leader])
        
        # Render non-winners first (back layer)
        for country, racer in self.physics_world.get_racers().items():
            # Skip winner for now (render last = on top)
            if country == winner:
                continue
            
            self._render_racer(racer, is_winner=False)
        
        # Render winner LAST (appears on top)
        if winner and winner in self.physics_world.racers:
            winner_racer = self.physics_world.racers[winner]
            self._render_winner_spotlight(winner_racer)
            self._render_racer(winner_racer, is_winner=True)

        # 🏍️ Podium tags at lane start (MOTOGP_MODE only)
        if MOTOGP_MODE and not winner:
            self._render_podium_tags()
    
    def _render_leader_spotlight(self, racer) -> None:
        """
        Render a pulsing golden glow with smooth interpolation.
        The spotlight smoothly 'travels' when leadership changes.
        
        Args:
            racer: The FlagRacer object of the current leader (used for fallback)
        """
        # Use interpolated spotlight position for smooth movement
        x, y = self.spotlight_current_pos
        
        # Sanitize position values
        if not math.isfinite(x) or not math.isfinite(y):
            x = float(racer.body.position.x)
            y = float(racer.body.position.y)
        
        ix = self._safe_int(x, self.physics_world.start_x)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        
        # Pulsing effect using leader_glow_time
        pulse = 0.5 + 0.5 * math.sin(self.leader_glow_time * 4.0)
        
        # Golden glow colors
        glow_color = (255, 215, 0)  # Gold
        
        # Draw outer soft glow (larger, more transparent)
        for i in range(5, 0, -1):
            glow_radius = 40 + i * 10
            glow_alpha = int((25 + 15 * pulse) / i)
            
            glow_surf = pygame.Surface((glow_radius * 2, glow_radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                glow_surf,
                (*glow_color, glow_alpha),
                (glow_radius, glow_radius),
                glow_radius
            )
            
            self.render_surface.blit(
                glow_surf,
                (ix - glow_radius, iy - glow_radius)
            )
        
        # Add subtle particle sparkles around the leader
        if random.random() < 0.3:  # 30% chance per frame
            offset_x = random.uniform(-30, 30)
            offset_y = random.uniform(-30, 30)
            sparkle_size = random.randint(2, 4)
            sparkle_alpha = random.randint(100, 200)
            
            sparkle_surf = pygame.Surface((sparkle_size * 2, sparkle_size * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                sparkle_surf,
                (255, 255, 200, sparkle_alpha),
                (sparkle_size, sparkle_size),
                sparkle_size
            )
            self.render_surface.blit(
                sparkle_surf,
                (ix + int(offset_x) - sparkle_size, iy + int(offset_y) - sparkle_size)
            )
    
    def _render_racer(self, racer, is_winner: bool = False) -> None:
        """Render a single racer flag with ON FIRE jitter effect."""
        x = racer.body.position.x
        y = racer.body.position.y + (racer.y_offset if hasattr(racer, 'y_offset') else 0.0)
        radius = racer.draw_radius
        angle = racer.body.angle

        # Sanitize position values
        x = float(x) if math.isfinite(x) else self.physics_world.start_x
        y = float(y) if math.isfinite(y) else (racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2)
        radius = float(radius) if math.isfinite(radius) else 30
        
        # ❄️ FREEZE shiver (takes priority over ON FIRE; flag can't be both)
        is_frozen = self.physics_world.is_country_frozen(racer.country)
        if is_frozen:
            x += random.uniform(-3, 3)
            y += random.uniform(-2, 2)
        elif racer.country in self.on_fire_countries:
            # 🔥 ON FIRE jitter effect
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)

        # Winner gets scaled up
        if is_winner:
            scale = self.winner_scale_pulse
            radius = radius * scale
    
        if racer.sprite:
            # Scale sprite if winner
            if is_winner:
                w = self._safe_int(radius * 2, 1)
                scaled_sprite = pygame.transform.scale(racer.sprite, (w, w))
                self._render_sprite(scaled_sprite, x, y, angle, radius)
            else:
                self._render_sprite(racer.sprite, x, y, angle, radius)
        else:
            # Fallback: colored circle
            ix = self._safe_int(x, self.physics_world.start_x)
            iy = self._safe_int(y, SCREEN_HEIGHT // 2)
            ir = self._safe_int(radius, 30)
            pygame.draw.circle(self.render_surface, racer.color, (ix, iy), ir)
            pygame.draw.circle(self.render_surface, (0, 0, 0), (ix, iy), ir, 2)
        
        # ❄️ ICE BLOCK overlay when frozen
        ix = self._safe_int(x, self.physics_world.start_x)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        ir = self._safe_int(radius, 10)
        if is_frozen:
            size = ir * 2 + 4
            ice_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            ice_surf.fill((80, 210, 255, 100))          # Cyan fill, semi-transparent
            pygame.draw.rect(ice_surf, (200, 240, 255, 200), (0, 0, size, size), 2)  # Bright border
            self.render_surface.blit(ice_surf, (ix - ir - 2, iy - ir - 2))
            # Timer countdown above the block
            remaining = self.physics_world.frozen_countries.get(racer.country, 0.0)
            timer_font = _get_font("Arial", 10, bold=True)
            timer_surf = timer_font.render(f"{remaining:.1f}s", True, (180, 235, 255))
            self.render_surface.blit(timer_surf, (ix - timer_surf.get_width() // 2, iy - ir - 16))

        # 👑 CAPTAIN LABEL
        self._render_captain_label(racer, ix, iy)

    def _render_neon_lane_labels(self) -> None:
        """Render fixed country name labels centered horizontally in each lane with 80s neon glow."""
        label_x = SCREEN_WIDTH // 2
        font = _get_font("Arial", 10, bold=True)
        # Subtle flicker: fast sine at 7 Hz, range 85%–100% brightness
        flicker = 0.85 + 0.15 * math.sin(self.leader_glow_time * 7.3)

        for country, racer in self.physics_world.get_racers().items():
            lane_y = int(racer.body.position.y + (racer.y_offset if hasattr(racer, 'y_offset') else 0.0))
            neon_col = racer.color

            # Measure text
            text_w, text_h = font.size(country)
            pad_x, pad_y = 8, 3
            pill_w = text_w + pad_x * 2
            pill_h = text_h + pad_y * 2
            margin = 14  # room for outermost glow halo

            surf_w = pill_w + margin * 2
            surf_h = pill_h + margin * 2
            s = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
            cx, cy = surf_w // 2, surf_h // 2

            # Neon glow layers: outermost (diffuse) → innermost (bright rim)
            for extra, base_alpha in ((12, 18), (8, 38), (5, 65), (3, 105)):
                alpha = int(base_alpha * flicker)
                glow_rect = pygame.Rect(
                    cx - pill_w // 2 - extra,
                    cy - pill_h // 2 - extra,
                    pill_w + extra * 2,
                    pill_h + extra * 2,
                )
                pygame.draw.rect(s, (*neon_col, alpha), glow_rect,
                                 border_radius=pill_h // 2 + extra)

            # Dark translucent pill background
            bg_rect = pygame.Rect(cx - pill_w // 2, cy - pill_h // 2, pill_w, pill_h)
            pygame.draw.rect(s, (8, 4, 20, 200), bg_rect, border_radius=pill_h // 2)

            # Bright neon border line
            border_alpha = int(210 * flicker)
            pygame.draw.rect(s, (*neon_col, border_alpha), bg_rect,
                             width=1, border_radius=pill_h // 2)

            # Text boosted toward white for neon look
            bright = tuple(min(255, c + 110) for c in neon_col)
            text_surf = font.render(country, True, bright)
            s.blit(text_surf, (cx - text_w // 2, cy - text_h // 2))

            self.render_surface.blit(s, (label_x - surf_w // 2, lane_y - surf_h // 2))

    def _render_podium_tags(self) -> None:
        """Render '1st/2nd/3rd' gold/silver/bronze badges fixed at the start of each podium lane."""
        lb = self.physics_world.get_leaderboard()[:3]
        podium = [
            ("1st", (255, 215,   0), (255, 245, 180)),  # gold
            ("2nd", (192, 192, 192), (230, 230, 230)),  # silver
            ("3rd", (176, 107,  42), (220, 165, 100)),  # bronze
        ]
        tag_x = max(4, self.physics_world.start_x - 18)
        font = _get_font("Arial", 11, bold=True)
        pulse = 0.7 + 0.3 * math.sin(self.leader_glow_time * 4.0)

        for (label, glow_col, text_col), (_, country, *_rest) in zip(podium, lb):
            racer = self.physics_world.racers.get(country)
            if racer is None:
                continue
            y = float(racer.body.position.y) + (racer.y_offset if hasattr(racer, 'y_offset') else 0.0)
            tag_y = int(y)

            text_w, text_h = font.size(label)
            pad_x, pad_y = 5, 2
            badge_w = text_w + pad_x * 2
            badge_h = text_h + pad_y * 2
            margin = 6

            s = pygame.Surface((badge_w + margin * 2, badge_h + margin * 2), pygame.SRCALPHA)
            cx, cy = (badge_w + margin * 2) // 2, (badge_h + margin * 2) // 2

            # Outer glow
            for extra, base_a in ((6, 30), (4, 60), (2, 100)):
                a = int(base_a * pulse)
                gr = pygame.Rect(cx - badge_w // 2 - extra, cy - badge_h // 2 - extra,
                                 badge_w + extra * 2, badge_h + extra * 2)
                pygame.draw.rect(s, (*glow_col, a), gr, border_radius=badge_h // 2 + extra)

            # Dark pill background
            br = pygame.Rect(cx - badge_w // 2, cy - badge_h // 2, badge_w, badge_h)
            pygame.draw.rect(s, (20, 12, 0, 210), br, border_radius=badge_h // 2)
            pygame.draw.rect(s, (*glow_col, int(220 * pulse)), br, width=1, border_radius=badge_h // 2)

            # Text
            text_surf = font.render(label, True, text_col)
            s.blit(text_surf, (cx - text_w // 2, cy - text_h // 2))

            self.render_surface.blit(s, (tag_x - (badge_w + margin * 2) // 2,
                                         tag_y - (badge_h + margin * 2) // 2))

    def _render_captain_label(self, racer, flag_x: int, flag_y: int) -> None:
        """
        Render captain name below country flag.
        
        Args:
            racer: Racer object with country info
            flag_x: X position of flag center
            flag_y: Y position of flag center
        """
        country = racer.country
        captain = self.current_captains.get(country, "")
        
        # Position below the flag (closer now that we removed country name)
        label_y = flag_y + 25  # Below flag (reduced from 35 since no country name)
        
        if captain:
            captain_text = f"@{captain}"

            # Special highlight if just became captain
            if country in self.captain_change_timer:
                color = (255, 223, 0)  # Golden yellow for new captain
                font_size = 12
            else:
                # Improved: Golden/white color for better visibility
                color = (255, 245, 200)  # Soft golden-white for better readability
                font_size = 10

            # Render with enhanced text (outline) - stronger outline for cross-platform visibility
            try:
                captain_font = _get_font("Arial", font_size, bold=True)
                captain_surface = self._render_text_enhanced(
                    captain_text,
                    captain_font,
                    color,
                    outline_color=(0, 0, 0),
                    outline_width=2  # Thicker outline for better visibility on Mac and Windows
                )

                captain_rect = captain_surface.get_rect(center=(flag_x, label_y))
                self.render_surface.blit(captain_surface, captain_rect)

            except Exception as e:
                logger.debug(f"Error rendering captain label: {e}")
        # No "No Captain" text displayed - cleaner look when no captain assigned

    def _render_sprite(
        self, 
        sprite: pygame.Surface, 
        x: float, 
        y: float, 
        angle: float,
        radius: float
    ) -> None:
        """
        Render a rotated sprite at the physics position.
        
        Args:
            sprite: Surface to render
            x, y: Center position
            angle: Angle in radians (from Pymunk)
            radius: Ball radius (for scaling if needed)
        """
        # Convert angle from radians to degrees for Pygame
        angle_degrees = math.degrees(angle) if math.isfinite(angle) else 0.0
        
        # Rotate the sprite
        rotated_sprite = pygame.transform.rotate(sprite, -angle_degrees)
        
        # Get centered rect (safe int conversion)
        ix = self._safe_int(x, self.physics_world.start_x)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        rect = rotated_sprite.get_rect(center=(ix, iy))
        
        # Draw
        self.render_surface.blit(rotated_sprite, rect)

    def _draw_star(self, x: float, y: float, size: int, color: tuple[int, int, int]) -> None:
        """Draw a simple 8-point star (cross + diagonals)."""
        # Safe int conversions for all coordinates
        ix = self._safe_int(x, SCREEN_WIDTH // 2)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        
        pygame.draw.line(self.render_surface, color, 
                         (ix - size, iy), (ix + size, iy), 2)
        pygame.draw.line(self.render_surface, color, 
                         (ix, iy - size), (ix, iy + size), 2)
        pygame.draw.line(self.render_surface, color, 
                         (self._safe_int(ix - size*0.7), self._safe_int(iy - size*0.7)), 
                         (self._safe_int(ix + size*0.7), self._safe_int(iy + size*0.7)), 1)
        pygame.draw.line(self.render_surface, color, 
                         (self._safe_int(ix - size*0.7), self._safe_int(iy + size*0.7)), 
                         (self._safe_int(ix + size*0.7), self._safe_int(iy - size*0.7)), 1)

    @property
    def _hud_offset(self) -> int:
        """Vertical offset so the HUD sits flush against the first lane."""
        return self.physics_world.lane_y_offset

    def _render_header(self) -> None:
        """Render header with leader info and drop shadow for visibility."""
        if MOTOGP_MODE:
            return  # Leader tag rendered inline in _render_balls instead
        off = self._hud_offset

        # Leader info
        leader_info = self.physics_world.get_leader()
        leader_text = f"1st: {leader_info[0]}" if leader_info else "1st: ---"

        # 🎯 EFECTO POP cuando cambia el líder
        if self.leader_pop_timer > 0:
            pop_scale = 1.1
            pop_font = _get_font("Arial", int(FONT_SIZE * pop_scale), bold=True)
            count_surface = self._render_text_with_shadow(
                leader_text, pop_font, (255, 255, 0), shadow_offset=2
            )
        else:
            count_surface = self._render_text_with_shadow(
                leader_text, self.font, (255, 255, 255), shadow_offset=2
            )

        # Compact gold badge sized to text
        pad_x, pad_y = 10, 3
        badge_x = 6
        badge_y = off + self.header_height // 2 - count_surface.get_height() // 2 - pad_y
        badge_w = count_surface.get_width() + pad_x * 2
        badge_h = count_surface.get_height() + pad_y * 2
        badge_surf = pygame.Surface((badge_w, badge_h), pygame.SRCALPHA)
        pygame.draw.rect(badge_surf, (190, 150, 45, 220), (0, 0, badge_w, badge_h), border_radius=8)
        self.render_surface.blit(badge_surf, (badge_x, badge_y))

        # Leader text: left-aligned with badge
        text_rect = count_surface.get_rect()
        text_rect.left = badge_x + pad_x
        text_rect.centery = off + self.header_height // 2
        self.render_surface.blit(count_surface, text_rect)

        # Last follower: right-aligned in header (gold)
        if self.notification_manager.last_follower:
            lf_surf = _get_mono_font(13).render(
                f"Ultimo seguidor: {self.notification_manager.last_follower}", True, (255, 255, 255)
            )
            lf_rect = lf_surf.get_rect()
            lf_rect.right = SCREEN_WIDTH - 8
            lf_rect.centery = off + self.header_height // 2
            self.render_surface.blit(lf_surf, lf_rect)

    def _get_status_color(self) -> tuple[int, int, int]:
        if self.connection_state == ConnectionState.CONNECTED:
            return COLOR_STATUS_CONNECTED
        elif self.connection_state == ConnectionState.RECONNECTING:
            return COLOR_STATUS_RECONNECTING
        return COLOR_STATUS_DISCONNECTED
    
    def _get_status_text(self) -> str:
        if self.connection_state == ConnectionState.CONNECTED:
            return "Conectado"
        elif self.connection_state == ConnectionState.RECONNECTING:
            return "Reconectando..."
        elif self.connection_state == ConnectionState.FAILED:
            return "Conexión fallida"
        return "Desconectado"
    
    def _render_messages(self) -> None:
        """Render messages at bottom with semi-transparent background."""
        msg_surface = pygame.Surface((SCREEN_WIDTH, self.message_area_height), pygame.SRCALPHA)
        msg_surface.fill((0, 0, 0, 140))  # Más transparente (140 en lugar de 180)
        self.render_surface.blit(msg_surface, (0, SCREEN_HEIGHT - self.message_area_height))
        
        y = SCREEN_HEIGHT - PADDING
        
        for message, event_type in reversed(self.messages):
            color = COLOR_TEXT_GIFT if event_type == EventType.GIFT else COLOR_TEXT_SYSTEM
            
            if len(message) > 55:
                message = message[:52] + "..."
            
            text_surface = self.font_small.render(message, True, color)
            y -= LINE_HEIGHT
            
            if y < SCREEN_HEIGHT - self.message_area_height + PADDING:
                break
            
            self.render_surface.blit(text_surface, (PADDING, y))
    
    def _build_lanes_surface(self) -> pygame.Surface:
        """Build the static lanes surface once; reused every frame."""
        from .config import COLOR_LANE_LINE
        surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        start_x = self.physics_world.start_x
        finish_x = self.physics_world.finish_line_x
        game_area_top = self.physics_world.game_area_top
        lane_height = self.physics_world.lane_height
        for i in range(1, self.physics_world.num_lanes):
            y = game_area_top + i * lane_height
            pygame.draw.line(surf, COLOR_LANE_LINE, (start_x, y), (finish_x, y), 1)
        return surf

    def _render_lanes(self) -> None:
        """Draw subtle lane separators using pre-rendered static surface."""
        if self._lanes_surface is not None:
            self.render_surface.blit(self._lanes_surface, (0, 0))
    
    def _render_final_stretch_line(self) -> None:
        """Draw a dashed, blurred yellow line at 80% of track marking where final stretch begins."""
        start_x = self.physics_world.start_x
        finish_x = self.physics_world.finish_line_x
        track_len = finish_x - start_x
        if track_len <= 0:
            return
        stretch_x = start_x + self.final_stretch_threshold * track_len
        ix = self._safe_int(stretch_x, SCREEN_WIDTH // 2)
        
        # Yellow color (golden yellow)
        base_color = (255, 215, 0)
        
        # Create dashed pattern: draw segments with gaps
        dash_length = 12  # Length of each dash
        gap_length = 8    # Length of gap between dashes
        segment_length = dash_length + gap_length
        
        # Blur effect: draw multiple lines with slight offsets and reduced opacity
        # Create a temporary surface with alpha channel for blur effect
        blur_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        
        # Draw multiple blurred layers
        blur_offsets = [-2, -1, 0, 1, 2]  # Horizontal blur spread
        blur_alphas = [60, 100, 200, 100, 60]  # Opacity for each blur layer (center is brightest)
        
        for offset, alpha in zip(blur_offsets, blur_alphas):
            # Create color with alpha for this blur layer
            blur_color = (*base_color, alpha)
            
            # Draw dashed segments for this blur layer
            y = 0
            while y < SCREEN_HEIGHT:
                # Draw dash segment
                dash_end = min(y + dash_length, SCREEN_HEIGHT)
                pygame.draw.line(blur_surf, blur_color, (ix + offset, y), (ix + offset, dash_end), 3)
                # Move to next segment
                y += segment_length
        
        # Blit the blurred dashed line onto the render surface
        self.render_surface.blit(blur_surf, (0, 0))
    
    def _render_finish_line(self) -> None:
        """Draw the finish line with smaller checkered pattern."""
        finish_x = self.physics_world.finish_line_x
        square_size = 12  # Reducido de 30 a 12
        
        for y in range(0, SCREEN_HEIGHT, square_size):
            for x in range(0, square_size * 2, square_size):
                color = (255, 255, 255) if (y // square_size + x // square_size) % 2 == 0 else (0, 0, 0)
                rect = pygame.Rect(finish_x + x - square_size, y, square_size, square_size)
                pygame.draw.rect(self.render_surface, color, rect)

    def _render_winner_spotlight(self, winner_racer) -> None:
        """Render special effects around the winner (rings, rays, stars)."""
        # Sanitize base position
        raw_x, raw_y = winner_racer.body.position
        x = float(raw_x) if math.isfinite(raw_x) else self.physics_world.start_x
        y = float(raw_y) if math.isfinite(raw_y) else (winner_racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2)
        
        raw_radius = winner_racer.draw_radius * self.winner_scale_pulse
        radius = float(raw_radius) if math.isfinite(raw_radius) else 30.0

        # Glow rings
        for i in range(3):
            glow_radius = radius + 20 + i * 18 + (self.winner_animation_time * 30) % 45
            if not math.isfinite(glow_radius) or glow_radius <= 0:
                continue
            glow_alpha = max(0, self.winner_glow_alpha - i * 45)
            glow_size = self._safe_int(glow_radius * 2, 60)
            if glow_size <= 0:
                continue
            glow_surf = pygame.Surface((glow_size, glow_size), pygame.SRCALPHA)
            pygame.draw.circle(glow_surf, (255, 215, 0, glow_alpha), (glow_size//2, glow_size//2), self._safe_int(glow_radius, 30), 4)
            self.render_surface.blit(glow_surf, (self._safe_int(x - glow_radius), self._safe_int(y - glow_radius)))

        # Radial light rays — drawn into shared layer, one blit total
        if self._ray_layer is not None:
            self._ray_layer.fill((0, 0, 0, 0))
            num_rays = 8
            ray_length = 80
            ray_alpha = max(0, self.winner_glow_alpha - 80)
            ray_color = (255, 223, 0, ray_alpha)
            for i in range(num_rays):
                angle = (self.winner_animation_time * 2.0 + i * (2 * math.pi / num_rays))
                start_x_r = x + math.cos(angle) * radius
                start_y_r = y + math.sin(angle) * radius
                end_x_r = x + math.cos(angle) * (radius + ray_length)
                end_y_r = y + math.sin(angle) * (radius + ray_length)
                pygame.draw.line(
                    self._ray_layer,
                    ray_color,
                    (self._safe_int(start_x_r), self._safe_int(start_y_r)),
                    (self._safe_int(end_x_r), self._safe_int(end_y_r)),
                    3
                )
            self.render_surface.blit(self._ray_layer, (0, 0))

        # Orbiting stars
        num_stars = 10
        star_distance = radius + 48
        for i in range(num_stars):
            star_angle = self.winner_animation_time * 1.5 + i * (2 * math.pi / num_stars)
            star_x = x + math.cos(star_angle) * star_distance
            star_y = y + math.sin(star_angle) * star_distance
            twinkle = (math.sin(self.winner_animation_time * 8 + i) + 1) / 2
            star_size = self._safe_int(2 + twinkle * 5, 3)
            self._draw_star(star_x, star_y, star_size, (255, 255, 200))

    def _draw_star(self, x: float, y: float, size: int, color: tuple[int, int, int]) -> None:
        """Draw a simple 8-point star (cross + diagonals)."""
        # Safe int conversions for all coordinates
        ix = self._safe_int(x, SCREEN_WIDTH // 2)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        
        pygame.draw.line(self.render_surface, color, 
                         (ix - size, iy), (ix + size, iy), 2)
        pygame.draw.line(self.render_surface, color, 
                         (ix, iy - size), (ix, iy + size), 2)
        pygame.draw.line(self.render_surface, color, 
                         (self._safe_int(ix - size*0.7), self._safe_int(iy - size*0.7)), 
                         (self._safe_int(ix + size*0.7), self._safe_int(iy + size*0.7)), 1)
        pygame.draw.line(self.render_surface, color, 
                         (self._safe_int(ix - size*0.7), self._safe_int(iy + size*0.7)), 
                         (self._safe_int(ix + size*0.7), self._safe_int(iy - size*0.7)), 1)

    def _build_leaderboard_surface(self) -> pygame.Surface:
        """Render the leaderboard table into a cached surface (called once per race end)."""
        leaderboard = self.physics_world.get_leaderboard()[:10]

        side_margin = 20
        left_margin = 15
        table_w, table_h = SCREEN_WIDTH - (side_margin * 2), 420
        bar_margin_left = 90 + left_margin
        bar_margin_right = 80
        bar_h = 10
        bar_w = table_w - bar_margin_left - bar_margin_right
        bar_x = bar_margin_left
        max_distance = max(1, self.physics_world.finish_line_x - self.physics_world.start_x)

        surf = pygame.Surface((table_w, table_h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (5, 5, 10, 255), (0, 0, table_w, table_h), border_radius=10)
        pygame.draw.rect(surf, (255, 215, 0, 180), (0, 0, table_w, table_h), 2, border_radius=10)

        header_font = _get_font("Arial", 18, bold=True)
        hdr = header_font.render("FINAL CLASSIFICATION", True, (255, 215, 0))
        surf.blit(hdr, (15 + left_margin, 10))

        row_font = _get_font("Arial", 14, bold=True)
        start_y = 45
        row_h = 35
        medal_colors = {1: (255, 215, 0), 2: (192, 192, 192), 3: (205, 127, 50)}

        for idx, (position, country, distance, _medal) in enumerate(leaderboard):
            y = start_y + idx * row_h

            if position == 1:
                bg = (50, 40, 20, 140)
            elif position == 2:
                bg = (40, 40, 40, 100)
            elif position == 3:
                bg = (45, 35, 25, 100)
            else:
                bg = (20, 20, 20, 70)

            pygame.draw.rect(surf, bg, (10 + left_margin, y - 5, table_w - 20 - left_margin, row_h - 4), border_radius=6)

            position_x = 25 + left_margin
            if position <= 3:
                medal_color = medal_colors[position]
                pygame.draw.circle(surf, medal_color, (position_x, y + 8), 10)
                pygame.draw.circle(surf, (255, 255, 255), (position_x, y + 8), 10, 1)
                pos_s = row_font.render(f"{position}", True, (0, 0, 0))
                surf.blit(pos_s, (position_x - 4, y))
            else:
                pos_s = row_font.render(f"{position}", True, (200, 200, 200))
                surf.blit(pos_s, (position_x - 5, y))

            country_x = 45 + left_margin
            country_s = row_font.render(country, True, (255, 255, 255))
            max_country_width = bar_x - country_x - 10
            if country_s.get_width() > max_country_width:
                truncated = country[:12] + "..." if len(country) > 12 else country
                country_s = row_font.render(truncated, True, (255, 255, 255))
            surf.blit(country_s, (country_x, y))

            dist_val = distance if (isinstance(distance, (int, float)) and math.isfinite(distance)) else 0.0
            diamonds_approx = self._safe_int(dist_val / 0.8, 0)
            dist_s = row_font.render(f"{diamonds_approx}d", True, (255, 215, 100))
            surf.blit(dist_s, (table_w - bar_margin_right - 5, y))

            prog = min(max((dist_val / max_distance) if max_distance > 0 else 0.0, 0.0), 1.0)
            filled = self._safe_int(bar_w * prog, 0)
            pygame.draw.rect(surf, (50, 50, 50), (bar_x, y + 20, bar_w, bar_h), border_radius=5)
            if filled > 0:
                bar_color = medal_colors.get(position, (80, 180, 80))
                pygame.draw.rect(surf, bar_color, (bar_x, y + 20, filled, bar_h), border_radius=5)

        return surf

    def _render_leaderboard(self) -> None:
        """Render leaderboard overlay when race finished. Table surface is cached."""
        if not self.physics_world.race_finished:
            return

        # Render 3D ranking visualization behind the final classification (animated, not cached)
        if self.global_rank_data:
            self._render_3d_ranking_visualization()

        # Dim background behind the final classification panel
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.render_surface.blit(overlay, (0, 0))

        # Build (once) and blit the static leaderboard table
        if self._leaderboard_cache is None:
            self._leaderboard_cache = self._build_leaderboard_surface()

        side_margin = 20
        table_h = 420
        table_x = side_margin
        table_y = SCREEN_HEIGHT - table_h - 60

        # Second dim overlay
        overlay2 = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay2.fill((0, 0, 0, 180))
        self.render_surface.blit(overlay2, (0, 0))

        self.render_surface.blit(self._leaderboard_cache, (table_x, table_y))

    def _render_legend(self) -> None:
        """Render combat powers panel in bottom-right corner with transparent background."""
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT

        # Panel dimensions - compact vertical layout
        panel_width = 140
        panel_height = 110
        margin = 10
        panel_x = SCREEN_WIDTH - panel_width - margin
        panel_y = SCREEN_HEIGHT - panel_height - margin
        padding = 8

        # Transparent background panel
        legend_surf = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        legend_surf.fill((15, 15, 20, 140))  # Very transparent dark background
        # Subtle golden border
        pygame.draw.rect(legend_surf, (255, 215, 0, 180), (0, 0, panel_width, panel_height), 2, border_radius=8)

        # Title
        title_font = _get_font("Arial", 10, bold=True)
        title_surf = self._render_text_enhanced(
            "COMBAT POWERS",
            title_font,
            (255, 235, 90),
            outline_color=(0, 0, 0),
            outline_width=2,  # Thicker outline for Mac/Windows visibility
        )
        title_rect = title_surf.get_rect(center=(panel_width // 2, padding + 6))
        legend_surf.blit(title_surf, title_rect)

        # Three items: [shape] effect / gift name (vertical layout) - no icons, shapes only
        items = [
            ("rosa", "+5m", "Rosa", (255, 150, 180)),
            ("pesa", "-10m", "Pesa", (190, 190, 200)),
            ("hielo", "Freeze", "Helado", (140, 200, 255)),
        ]

        row_height = 22
        start_y = padding + 20
        shape_size = 16
        eff_font = _get_font("Arial", 10, bold=True)
        name_font = _get_font("Arial", 8)

        for i, (shape_type, effect, gift_name, color) in enumerate(items):
            y = start_y + i * row_height
            shape_x = padding + 10
            shape_y = y + 8
            text_x = shape_x + shape_size + 6
            r = shape_size // 2

            # Draw colored shape (no icons)
            if shape_type == "rosa":
                pygame.draw.circle(legend_surf, color, (shape_x, shape_y), r)
            elif shape_type == "pesa":
                pygame.draw.rect(legend_surf, color, (shape_x - r, shape_y - r, 2 * r, 2 * r))
            else:  # hielo
                pts = [(shape_x, shape_y - r), (shape_x + r, shape_y), (shape_x, shape_y + r), (shape_x - r, shape_y)]
                pygame.draw.polygon(legend_surf, color, pts)

            # Effect text
            eff_surf = self._render_text_enhanced(
                effect,
                eff_font,
                (240, 240, 240),
                outline_color=(0, 0, 0),
                outline_width=2,  # Strong outline for cross-platform visibility
            )
            eff_rect = eff_surf.get_rect(midleft=(text_x, shape_y - 4))
            legend_surf.blit(eff_surf, eff_rect)

            # Gift name (smaller, below effect)
            name_surf = name_font.render(gift_name, True, (180, 180, 190))
            name_rect = name_surf.get_rect(midleft=(text_x, shape_y + 7))
            legend_surf.blit(name_surf, name_rect)

        # Blit panel to screen
        self.render_surface.blit(legend_surf, (panel_x, panel_y))

        # Frozen indicator (if active, show above the panel)
        if self.physics_world.frozen_countries:
            parts = [f"{c}: {t:.1f}s" for c, t in self.physics_world.frozen_countries.items()]
            frozen_font = _get_font("Arial", 10, bold=True)
            frozen_surf = self._render_text_enhanced(
                f"FROZEN: {' | '.join(parts)}",
                frozen_font,
                (150, 220, 255),
                outline_color=(0, 0, 0),
                outline_width=2,
            )
            frozen_rect = frozen_surf.get_rect(bottomright=(SCREEN_WIDTH - margin, panel_y - 5))
            self.render_surface.blit(frozen_surf, frozen_rect)

    def assign_country_to_user(self, username: str) -> tuple[str, str]:
        """
        Assign a country to a user using a smart 3-tier system.
        
        Returns:
            (country, assignment_type) where assignment_type is one of:
            - "cached": User was already assigned
            - "flag": User mentioned a flag emoji in their username
            - "balanced": Auto-balanced assignment
        """
        # Tier 1: Check cache (already assigned)
        if username in self.user_country_cache:
            return self.user_country_cache[username], "cached"
        
        # Tier 2: Flag emoji detection in username
        for flag_emoji, country in self.flag_map.items():
            if flag_emoji in username:
                self.user_country_cache[username] = country
                self.country_player_count[country] = self.country_player_count.get(country, 0) + 1
                logger.info(f"🚩 {username} → {country} (flag detected)")
                return country, "flag"
        
        # Tier 3: Auto-balance (assign to country with fewest players)
        countries = list(self.physics_world.racers.keys())
        
        # Count players per country (default to 0)
        counts = {country: self.country_player_count.get(country, 0) for country in countries}
        
        # Find country with minimum players
        min_count = min(counts.values())
        candidates = [c for c, count in counts.items() if count == min_count]
        
        # Pick first candidate (or random if you prefer)
        country = random.choice(candidates)
        
        # Update cache and count
        self.user_country_cache[username] = country
        self.country_player_count[country] = self.country_player_count.get(country, 0) + 1
        
        logger.info(f"⚖️ {username} → {country} (auto-balanced: {counts[country]+1} players)")
        return country, "balanced"
    
    # Ensure cleanup is a method on GameEngine (paste if missing or indent correctly)
    def cleanup(self) -> None:
        """Clean up Pygame and related resources."""
        try:
            pygame.quit()
        except Exception:
            pass
        logger.info("Pygame cleaned up")
    
    import math

    def _safe_int(self, v: float, default: int = 0) -> int:
        try:
            if not math.isfinite(v):
                return default
            return int(v)
        except Exception:
            return default
    
    def _auto_stress_test(self, dt: float) -> None:
        """
        Automatic stress test: inject random gifts at regular intervals.
        Only active when AUTO_STRESS_TEST is True in config.
        """
        self.stress_test_timer += dt
        
        if self.stress_test_timer >= STRESS_TEST_INTERVAL:
            self.stress_test_timer = 0.0
            
            # Skip if race is finished
            if self.physics_world.race_finished:
                return
            
            # Choose random country
            countries = list(self.physics_world.racers.keys())
            country = random.choice(countries)
            
            # Random diamond count (1-100)
            diamond_count = random.randint(1, 100)
            
            # Apply gift
            success, _ = self.physics_world.apply_gift_impulse(
                country=country,
                gift_name="Auto Test Gift",
                diamond_count=diamond_count
            )

            if success:
                # Emit particles
                racer = self.physics_world.racers[country]
                pos = (racer.body.position.x, racer.body.position.y)
                
                count = 10 + int(diamond_count / 10)
                power = 0.8
                
                self.emit_explosion(
                    pos=pos,
                    color=racer.color,
                    count=count,
                    power=power,
                    diamond_count=diamond_count
                )

    def _manual_stress_test_inject(self) -> None:
        """
        Inject random VOTE and GIFT events at 20/sec for stress testing.
        Rotates through the 12 countries. Used to test TTS queue, motion trails,
        and FPS stability under load. Toggle with key K.
        """
        from .config import RACE_COUNTRIES, GIFT_DIAMOND_VALUES

        now = time.time()
        if now - self._stress_test_last_inject < 0.05:
            return
        self._stress_test_last_inject = now

        if self.physics_world.race_finished:
            return

        countries = list(RACE_COUNTRIES)
        if not countries:
            return

        country = random.choice(countries)
        stress_gifts = ["Rosa", "Dona", "Galaxia", "TikTok", "León"]
        gift_name = random.choice(stress_gifts)
        diamond_count = GIFT_DIAMOND_VALUES.get(gift_name, 1)

        use_vote = random.choice([True, False])
        ts = int(now * 1000)

        try:
            if use_vote:
                username = f"stress_{ts}"
                ev = GameEvent(
                    type=EventType.VOTE,
                    username=username,
                    content=country,
                    extra={"shortcut": "1"},
                )
                self.queue.put_nowait(ev)
            else:
                username = f"stress_{country}_{ts}"
                self.user_country_cache[username] = country
                ev = GameEvent(
                    type=EventType.GIFT,
                    username=username,
                    content=gift_name,
                    extra={"count": 1, "diamond_count": diamond_count},
                )
                self.queue.put_nowait(ev)
        except Exception as e:
            logger.debug("Stress test inject skipped (queue full?): %s", e)

    def _monitor_performance(self, dt: float) -> None:
        """
        Monitor and log FPS and particle count for stress testing.
        Prints stats every second.
        """
        self.frame_count += 1
        self.fps_update_timer += dt
        
        # Update FPS every second
        if self.fps_update_timer >= 1.0:
            self.current_fps = self.frame_count / self.fps_update_timer
            
            # Get stats
            particle_count = len(self.particles)
            racer_count = len(self.physics_world.racers)
            
            # Calculate average distance traveled
            total_distance = sum(
                r.body.position.x - self.physics_world.start_x 
                for r in self.physics_world.racers.values()
            )
            avg_distance = total_distance / racer_count if racer_count > 0 else 0
            
            # Log performance
            logger.info(
                f"📊 STRESS TEST | FPS: {self.current_fps:.1f} | "
                f"Particles: {particle_count} | "
                f"Avg Distance: {avg_distance:.0f}px"
            )
            
            # Reset counters
            self.frame_count = 0
            self.fps_update_timer = 0.0
    
    def sanitize_username(self, username: str) -> str:
        """Limpia usernames problemáticos que pueden romper el renderizado."""
        # Eliminar solo caracteres de control; permitir acentos y la mayoría de símbolos
        sanitized = ''.join(
            ch for ch in username
            if ch.isprintable() and ch not in {'\n', '\r', '\t'}
        )
        
        # Limitar longitud
        if len(sanitized) > 20:
            sanitized = sanitized[:17] + "..."
        
        # Fallback si queda vacío
        if not sanitized.strip():
            sanitized = "Usuario"
        
        return sanitized
    
    def spawn_floating_text(
        self, 
        text: str, 
        x: float, 
        y: float, 
        color: tuple[int, int, int]
    ) -> None:
        """Spawn a floating text effect at the top of the screen for better visibility."""
        from .config import (
            SCREEN_WIDTH,
            FLOATING_TEXT_TOP_Y,
            FLOATING_TEXT_SPEED,
            FLOATING_TEXT_LIFESPAN,
            FLOATING_TEXT_FONT_SIZE,
        )
    
        floating_text = FloatingText(
            text=text,
            x=SCREEN_WIDTH / 2,  # Center at top
            y=FLOATING_TEXT_TOP_Y,
            color=color,
            dy=-FLOATING_TEXT_SPEED,
            lifespan=FLOATING_TEXT_LIFESPAN,
            max_lifespan=FLOATING_TEXT_LIFESPAN,
            font_size=FLOATING_TEXT_FONT_SIZE
        )
        self.floating_texts.append(floating_text)
        
        # Keep floating texts under the configured limit
        if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
            self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]

    def _emit_hype_activation_text(self) -> None:
        """Spawn 'HYPE MODE!' floating text when hype activates."""
        self.spawn_floating_text(
            ">> HYPE MODE! <<",
            x=0,   # spawn_floating_text centers horizontally
            y=0,
            color=(255, 50, 180),
        )

    def _render_victory_flash(self) -> None:
        """
        Render white flash effect on victory.
        Creates a full-screen white overlay that fades out over 0.3 seconds.
        Does not block state updates or final classification rendering.
        """
        from .config import ACTUAL_WIDTH, ACTUAL_HEIGHT
        
        if self.victory_flash_alpha <= 0:
            return
        
        # Create white surface with alpha
        flash_surface = pygame.Surface((ACTUAL_WIDTH, ACTUAL_HEIGHT), pygame.SRCALPHA)
        alpha = int(self.victory_flash_alpha)
        flash_surface.fill((255, 255, 255, alpha))
        
        # Blit flash overlay on top of everything
        self.render_surface.blit(flash_surface, (0, 0))
    
    def _render_disaster_flash(self) -> None:
        """Full-screen crimson flash that fires on Hype Disaster detonation."""
        from .config import ACTUAL_WIDTH, ACTUAL_HEIGHT
        if self._disaster_flash_alpha <= 0:
            return
        surf = pygame.Surface((ACTUAL_WIDTH, ACTUAL_HEIGHT), pygame.SRCALPHA)
        surf.fill((30, 200, 60, int(self._disaster_flash_alpha)))
        self.render_surface.blit(surf, (0, 0))

    def _render_disaster_title(self) -> None:
        """Centered title card shown for 2.5s after Hype Disaster detonation."""
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        if self._disaster_title_timer <= 0:
            return
        alpha = min(255, int(self._disaster_title_timer * 200))
        font = _get_font("Arial", 52, bold=True)
        text_surf = font.render(HYPE_DISASTER_TITLE, True, (50, 220, 80))
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 40, 10, 130))
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2
        overlay.blit(text_surf, text_surf.get_rect(center=(cx, cy)))
        overlay.set_alpha(alpha)
        self.render_surface.blit(overlay, (0, 0))

    def _render_text_enhanced(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        outline_color: tuple[int, int, int] = (0, 0, 0),
        outline_width: int = 2
    ) -> pygame.Surface:
        """
        Render text with enhanced quality: anti-aliasing and thick outline.
        
        Args:
            text: Text to render
            font: Pygame font to use
            color: Main text color (RGB)
            outline_color: Outline color (RGB)
            outline_width: Thickness of outline in pixels
        
        Returns:
            Surface with rendered text
        """
        # Render outline (multiple passes for thickness)
        outline_surfaces = []
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    outline_surf = font.render(text, True, outline_color)
                    outline_surfaces.append((outline_surf, dx, dy))
        
        # Render main text with anti-aliasing (True)
        main_text = font.render(text, True, color)
        
        # Create composite surface
        if outline_surfaces:
            # Calculate size including outline
            width = main_text.get_width() + outline_width * 2
            height = main_text.get_height() + outline_width * 2
            
            composite = pygame.Surface((width, height), pygame.SRCALPHA)
            
            # Draw all outline layers
            for outline_surf, dx, dy in outline_surfaces:
                composite.blit(outline_surf, (outline_width + dx, outline_width + dy))
            
            # Draw main text on top
            composite.blit(main_text, (outline_width, outline_width))
            
            return composite
        else:
            return main_text
    
    def _render_text_with_shadow(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        shadow_offset: int = 2,
        shadow_color: tuple[int, int, int] = (0, 0, 0),
        shadow_alpha: int = 128
    ) -> pygame.Surface:
        """
        Render text with a soft drop shadow for modern look.
        More performant than full outline for general UI.
        
        Args:
            text: Text to render
            font: Pygame font to use
            color: Main text color (RGB)
            shadow_offset: Shadow offset in pixels
            shadow_color: Shadow color (RGB)
            shadow_alpha: Shadow transparency (0-255)
        
        Returns:
            Surface with text and drop shadow
        """
        main_text = font.render(text, True, color)
        shadow_text = font.render(text, True, shadow_color)
        
        # Create surface with room for shadow
        width = main_text.get_width() + shadow_offset + 2
        height = main_text.get_height() + shadow_offset + 2
        
        composite = pygame.Surface((width, height), pygame.SRCALPHA)
        
        # Draw shadow with alpha
        shadow_surf = pygame.Surface(shadow_text.get_size(), pygame.SRCALPHA)
        shadow_surf.blit(shadow_text, (0, 0))
        shadow_surf.set_alpha(shadow_alpha)
        composite.blit(shadow_surf, (shadow_offset, shadow_offset))
        
        # Draw main text on top
        composite.blit(main_text, (0, 0))
        
        return composite
    
    def _render_idle_screen(self) -> None:
        """Render the IDLE state screen with animated prompt."""
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT, GAME_MODE, COUNTRY_ABBREV
        
        # 1️⃣ OVERLAY OSCURO (alpha=150 como solicitado)
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))  # ← Cambiado de 180 a 150
        self.render_surface.blit(overlay, (0, 0))
        
        # Central message box
        if GAME_MODE == "COMMENT":
            box_width = 320
            box_height = 205
        else:
            box_width = 380
            box_height = 200

        box_x = (SCREEN_WIDTH - box_width) // 2
        box_y = (SCREEN_HEIGHT - box_height) // 2 + 40
        
        # Box with gradient effect
        box_surface = pygame.Surface((box_width, box_height), pygame.SRCALPHA)
        
        # Gradient background
        for i in range(box_height):
            ratio = i / box_height
            r = int(20 + (40 - 20) * ratio)
            g = int(20 + (50 - 20) * ratio)
            b = int(60 + (80 - 60) * ratio)
            pygame.draw.line(box_surface, (r, g, b, 230), (0, i), (box_width, i))
        
        # Border with golden glow
        pygame.draw.rect(box_surface, (255, 215, 0, 255), (0, 0, box_width, box_height), 3, border_radius=15)
        
        self.render_surface.blit(box_surface, (box_x, box_y))
        
        # 2️⃣ TEXTO PULSANTE CON EFECTO "RESPIRACIÓN"
        # Usar pygame.time.get_ticks() y math.sin para escala sutil (1.0 - 1.05)
        ticks = pygame.time.get_ticks()
        breathe_scale = 1.0 + 0.05 * math.sin(ticks * 0.003)  # Oscila entre 1.0 y 1.05
        pulse_alpha = int(200 + 55 * math.sin(ticks * 0.0025))  # Alpha pulsante

        # Main title - different text depending on mode
        title_font = _get_font("Arial", 22, bold=True)
        if GAME_MODE == "COMMENT":
            title_text = "VOTE IN CHAT!"
        else:
            title_text = "SEND A ROSE"
        
        title_surface = self._render_text_enhanced(
            title_text,
            title_font,
            (255, 215, 0),
            outline_color=(0, 0, 0),
            outline_width=3
        )
        
        # Apply breathe scale (scale() not smoothscale to avoid stutter in render loop)
        scaled_width = int(title_surface.get_width() * breathe_scale)
        scaled_height = int(title_surface.get_height() * breathe_scale)
        title_surface = pygame.transform.scale(title_surface, (scaled_width, scaled_height))
        
        # Apply pulsating alpha
        title_alpha_surface = pygame.Surface(title_surface.get_size(), pygame.SRCALPHA)
        title_alpha_surface.fill((255, 255, 255, pulse_alpha))
        title_surface = title_surface.copy()
        title_surface.blit(title_alpha_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        
        title_rect = title_surface.get_rect(center=(box_x + box_width // 2, box_y + 40))
        self.render_surface.blit(title_surface, title_rect)

        # COMMENT MODE: Mostrar lista de opciones dentro del recuadro
        if GAME_MODE == "COMMENT":
            # Subtitle
            subtitle_font = _get_font("Arial", 14, bold=True)
            subtitle_text = "Type # or SIGLA to start:"
            subtitle_surface = subtitle_font.render(subtitle_text, True, (200, 200, 200))
            subtitle_rect = subtitle_surface.get_rect(center=(box_x + box_width // 2, box_y + 70))
            self.render_surface.blit(subtitle_surface, subtitle_rect)
            
            # Lista de países: 2 columnas × 4 filas (4 países por columna)
            item_font = _get_font("Arial", 12, bold=True)
            y_offset = box_y + 95
            line_height = 24
            col_width = box_width // 2
            
            for i, country in enumerate(self.physics_world.countries, start=1):
                abbrev = COUNTRY_ABBREV.get(country, country[:3].upper())
                color = self.physics_world.racers[country].color
                
                # 2 columns × 4 rows: left col = 1-4, right col = 5-8
                col = (i - 1) // 4
                row = (i - 1) % 4
                
                x_base = box_x + 20 + (col * col_width)
                y_pos = y_offset + (row * line_height)
                
                # Number
                number_text = f"{i:2d}"
                number_surface = item_font.render(number_text, True, (255, 255, 100))
                self.render_surface.blit(number_surface, (x_base, y_pos))
                
                # Separator
                sep_surface = item_font.render("→", True, (150, 150, 150))
                self.render_surface.blit(sep_surface, (x_base + 25, y_pos))
                
                # Sigla (with country color)
                sigla_surface = item_font.render(abbrev, True, color)
                self.render_surface.blit(sigla_surface, (x_base + 45, y_pos))
        
        else:
            # GIFT MODE: Subtitle con mismo efecto de respiración
            subtitle_font = _get_font("Arial", 20, bold=True)
            subtitle_text = "TO START!"
            subtitle_surface = self._render_text_enhanced(
                subtitle_text,
                subtitle_font,
                (255, 255, 100),
                outline_color=(0, 0, 0),
                outline_width=3
            )
            
            # Apply breathe scale (scale() not smoothscale for performance)
            scaled_width = int(subtitle_surface.get_width() * breathe_scale)
            scaled_height = int(subtitle_surface.get_height() * breathe_scale)
            subtitle_surface = pygame.transform.scale(subtitle_surface, (scaled_width, scaled_height))
            
            # Apply pulsating alpha
            subtitle_alpha_surface = pygame.Surface(subtitle_surface.get_size(), pygame.SRCALPHA)
            subtitle_alpha_surface.fill((255, 255, 255, pulse_alpha))
            subtitle_surface = subtitle_surface.copy()
            subtitle_surface.blit(subtitle_alpha_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
            subtitle_rect = subtitle_surface.get_rect(center=(box_x + box_width // 2, box_y + 95))
            self.render_surface.blit(subtitle_surface, subtitle_rect)

        # Last winner info (if exists) - below country list to avoid overlap
        if self.last_winner:
            winner_font = _get_font("Arial", 14, bold=True)
            winner_text = f"Last winner: {self.last_winner}"
            winner_surface = self._render_text_enhanced(
                winner_text,
                winner_font,
                (100, 255, 150),
                outline_color=(0, 0, 0),
                outline_width=2
            )
            # In COMMENT mode place below the 4-row country list; in GIFT mode keep higher
            if GAME_MODE == "COMMENT":
                winner_y = box_y + 210
                distance_y = box_y + 235
            else:
                winner_y = box_y + 140
                distance_y = box_y + 165
            winner_rect = winner_surface.get_rect(center=(box_x + box_width // 2, winner_y))
            self.render_surface.blit(winner_surface, winner_rect)
            
            # Distance info
            diamonds_approx = self._safe_int(self.last_winner_distance / 0.8, 0)
            distance_text = f"Distance: {diamonds_approx} diamonds"
            distance_surface = winner_font.render(distance_text, True, (200, 200, 200))
            distance_rect = distance_surface.get_rect(center=(box_x + box_width // 2, distance_y))
            self.render_surface.blit(distance_surface, distance_rect)
        
        # 🏆 Render Global Ranking Panel (futuristic style) only
        # 3D tracks visualization is reserved for post-race screens
        self._render_global_ranking_futuristic()
    
    def _render_shortcuts_panel(self) -> None:
        """
        Render shortcuts as a modern scrolling ticker at the TOP of screen.
        Semi-transparent, non-intrusive, and always visible during racing.
        Positioned above the race area to avoid interfering with combat powers.
        """
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT, COUNTRY_ABBREV
        
        # Ticker dimensions - positioned below header but above first lane
        ticker_height = 20
        ticker_y = 32  # Between leader score and first flag lane
        
        # Semi-transparent background
        ticker_bg = pygame.Surface((SCREEN_WIDTH, ticker_height), pygame.SRCALPHA)
        ticker_bg.fill((0, 0, 0, 180))  # Dark with 70% opacity
        self.render_surface.blit(ticker_bg, (0, ticker_y))
        
        # Build ticker content string with colors
        item_font = _get_font("Arial", 12, bold=True)
        separator = "  •  "
        
        # Calculate total width of one complete cycle
        items = []
        for i, country in enumerate(self.physics_world.countries, start=1):
            abbrev = COUNTRY_ABBREV.get(country, country[:3].upper())
            color = self.physics_world.racers[country].color
            items.append((f"{i}", (255, 255, 100), abbrev, color))
        
        # Render items and calculate positions
        item_surfaces = []
        total_width = 0
        
        for num, num_color, abbrev, abbrev_color in items:
            # Number
            num_surf = self._render_text_with_shadow(num, item_font, num_color, shadow_offset=1, shadow_alpha=100)
            # Arrow
            arrow_surf = item_font.render("→", True, (100, 100, 100))
            # Sigla
            sigla_surf = self._render_text_with_shadow(abbrev, item_font, abbrev_color, shadow_offset=1, shadow_alpha=100)
            # Separator
            sep_surf = item_font.render(separator, True, (80, 80, 80))
            
            item_surfaces.append((num_surf, arrow_surf, sigla_surf, sep_surf))
            total_width += num_surf.get_width() + arrow_surf.get_width() + sigla_surf.get_width() + sep_surf.get_width() + 15
        
        # Wrap ticker offset
        if total_width > 0:
            self.ticker_offset = self.ticker_offset % total_width
        
        # Draw items with scroll offset (draw twice for seamless loop)
        x_pos = -int(self.ticker_offset)
        y_center = ticker_y + ticker_height // 2
        
        for _ in range(2):  # Draw twice for seamless scrolling
            for num_surf, arrow_surf, sigla_surf, sep_surf in item_surfaces:
                # Render each component
                self.render_surface.blit(num_surf, (x_pos, y_center - num_surf.get_height() // 2))
                x_pos += num_surf.get_width() + 3
                
                self.render_surface.blit(arrow_surf, (x_pos, y_center - arrow_surf.get_height() // 2))
                x_pos += arrow_surf.get_width() + 3
                
                self.render_surface.blit(sigla_surf, (x_pos, y_center - sigla_surf.get_height() // 2))
                x_pos += sigla_surf.get_width() + 3
                
                self.render_surface.blit(sep_surf, (x_pos, y_center - sep_surf.get_height() // 2))
                x_pos += sep_surf.get_width() + 6
        
        # Optional: Add subtle gold borders at top and bottom
        pygame.draw.line(self.render_surface, (255, 215, 0, 100), (0, ticker_y), (SCREEN_WIDTH, ticker_y), 1)
        pygame.draw.line(self.render_surface, (255, 215, 0, 50), (0, ticker_y + ticker_height - 1), (SCREEN_WIDTH, ticker_y + ticker_height - 1), 1)

    def _render_likes_bar(self) -> None:
        """
        Render the likes goal bar below the CTA banner and above the first lane.
        TikTok-style gradient (orange to pink), thin and elegant.
        Text: 'PRÓXIMO NITRO BOOST (actual/meta)'.
        """
        from .config import GAME_MODE, CTA_BANNER_Y, CTA_BANNER_HEIGHT, LIKES_BAR_HEIGHT
        bar_height = LIKES_BAR_HEIGHT
        bar_margin_x = 20
        bar_width = SCREEN_WIDTH - 2 * bar_margin_x
        progress = min(1.0, self.current_likes / self.likes_goal) if self.likes_goal > 0 else 0.0

        label_font = _get_font("Arial Black", 12, bold=False)
        label = f"PRÓXIMO NITRO BOOST ({self.current_likes}/{self.likes_goal})"
        label_surf = label_font.render(label, True, (255, 255, 255))

        if GAME_MODE == "COMMENT" and self.game_state == "RACING":
            label_y = CTA_BANNER_Y + CTA_BANNER_HEIGHT + 2 + self._hud_offset
            bar_y = label_y + label_surf.get_height() + 2
        else:
            bar_y = self.header_height + 2 + self._hud_offset
            label_y = bar_y - 2 - label_surf.get_height()

        # Background track (dark, pill-shaped)
        track_rect = pygame.Rect(bar_margin_x, bar_y, bar_width, bar_height)
        track_surf = pygame.Surface((bar_width, bar_height), pygame.SRCALPHA)
        track_surf.fill((0, 0, 0, 0))
        pygame.draw.rect(track_surf, (30, 30, 40, 220),
                         (0, 0, bar_width, bar_height), border_radius=bar_height // 2)
        self.render_surface.blit(track_surf, (bar_margin_x, bar_y))
        if progress > 0.001:
            fill_w = max(bar_height, int(bar_width * progress))
            grad_surf = pygame.Surface((fill_w, bar_height), pygame.SRCALPHA)
            for col in range(fill_w):
                t = col / bar_width
                r, g, b = 255, int(120 * (1 - t) + 105 * t), int(50 * (1 - t) + 180 * t)
                pygame.draw.line(grad_surf, (r, g, b, 255), (col, 0), (col, bar_height - 1))
            clip_surf = pygame.Surface((fill_w, bar_height), pygame.SRCALPHA)
            pygame.draw.rect(clip_surf, (255, 255, 255, 255),
                             (0, 0, fill_w, bar_height), border_radius=bar_height // 2)
            grad_surf.blit(clip_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self.render_surface.blit(grad_surf, (bar_margin_x, bar_y))
        pygame.draw.rect(self.render_surface, (255, 180, 180, 120),
                         track_rect, 1, border_radius=bar_height // 2)

        self.render_surface.blit(label_surf, (int(bar_margin_x), int(label_y)))

    def _trigger_meteor_shower(self) -> None:
        """
        Trigger Meteor Shower event: intense screen shake, 5 meteors with trails,
        each meteor that touches a flag gives a random boost. Then double goal and reset likes.
        """
        # Audio: charge when bar is full, then explosion
        if SoundType.LIKES_CHARGE in getattr(self.audio_manager, '_sound_cache', {}):
            self.audio_manager.play_sfx(SoundType.LIKES_CHARGE)
        if SoundType.METEOR_EXPLOSION in getattr(self.audio_manager, '_sound_cache', {}):
            self.audio_manager.play_sfx(SoundType.METEOR_EXPLOSION)
        self.screen_shaker.meteor_shake()
        self.current_likes = 0
        self.likes_goal = min(self.likes_goal * 2, 2000)
        self._likes_charge_played = False

        # Spawn 15 meteors: cross screen quickly with trail
        self.meteors.clear()
        for _ in range(15):
            # Start from random edge, move across screen
            side = random.choice(["left", "right", "top"])
            if side == "left":
                x = -20
                y = random.uniform(80, SCREEN_HEIGHT - 80)
                vx = random.uniform(350, 550)
                vy = random.uniform(-80, 80)
            elif side == "right":
                x = SCREEN_WIDTH + 20
                y = random.uniform(80, SCREEN_HEIGHT - 80)
                vx = random.uniform(-550, -350)
                vy = random.uniform(-80, 80)
            else:
                x = random.uniform(0, SCREEN_WIDTH)
                y = -20
                vx = random.uniform(-100, 100)
                vy = random.uniform(350, 550)
            self.meteors.append(Meteor(
                x=x, y=y, vx=vx, vy=vy,
                radius=random.uniform(6, 10),
                trail=[], max_trail=12, hit_countries=set()
            ))
        logger.info("🌠 Meteor Shower triggered! Goal now %s", self.likes_goal)

    def add_likes(self, count: int) -> None:
        """
        Add likes to the retention bar (Meteor Shower goal).
        Call this from real LIKE events (TikTok) or from simulation (e.g. key L).
        When current_likes >= likes_goal, triggers Meteor Shower and resets.

        Args:
            count: Number of likes to add (positive integer).
        """
        if count <= 0:
            return
        cap = max(self.likes_goal * 2, self.likes_goal + 500)
        self.current_likes = min(self.current_likes + count, cap)
        logger.debug(f"👍 Likes +{count} → {self.current_likes}/{self.likes_goal}")
        if self.current_likes >= self.likes_goal:
            self._trigger_meteor_shower()

    def _update_meteors(self, dt: float) -> None:
        """Update meteor positions, trails, and flag collisions (boost on touch)."""
        from .config import FLAG_RADIUS
        to_remove = []
        for m in self.meteors:
            m.x += m.vx * dt
            m.y += m.vy * dt
            m.trail.append((m.x, m.y, 255))
            if len(m.trail) > m.max_trail:
                m.trail.pop(0)
            for i, (_, _, a) in enumerate(m.trail):
                m.trail[i] = (m.trail[i][0], m.trail[i][1], max(0, a - 22))
            m.trail = [(tx, ty, aa) for (tx, ty, aa) in m.trail if aa > 10]

            # Collision with flags: boost country with random diamonds
            for country, racer in self.physics_world.get_racers().items():
                if country in m.hit_countries:
                    continue
                fx = float(racer.body.position.x)
                fy = float(racer.body.position.y)
                dist = math.hypot(m.x - fx, m.y - fy)
                if dist < (FLAG_RADIUS + m.radius + 8):
                    m.hit_countries.add(country)
                    boost = random.randint(15, 45)
                    self.physics_world.apply_gift_impulse(
                        country=country, gift_name="Meteor", diamond_count=boost
                    )
                    self.emit_explosion(
                        pos=(fx, fy), color=racer.color, count=6, power=0.6
                    )
                    self.spawn_floating_text(
                        f"+{boost}", fx, fy, COLOR_TEXT_POSITIVE
                    )
            # Remove when off screen
            if m.x < -50 or m.x > SCREEN_WIDTH + 50 or m.y < -50 or m.y > SCREEN_HEIGHT + 50:
                to_remove.append(m)
        for m in to_remove:
            self.meteors.remove(m)

    def _render_meteors(self) -> None:
        """Draw meteors and their trails (bright head, fading trail)."""
        for m in self.meteors:
            for (tx, ty, alpha) in m.trail:
                if alpha < 20:
                    continue
                k = alpha / 255.0
                r, g, b = int(255 * k), int(200 * k), int(150 * k)
                pygame.draw.circle(
                    self.render_surface,
                    (r, g, b),
                    (int(tx), int(ty)),
                    max(1, int(m.radius * 0.6)),
                )
            pygame.draw.circle(
                self.render_surface,
                (255, 220, 180),
                (int(m.x), int(m.y)),
                int(m.radius),
            )
            pygame.draw.circle(
                self.render_surface,
                (255, 255, 255),
                (int(m.x), int(m.y)),
                int(m.radius),
                1,
            )

    def _draw_permanent_cta(self, surface: pygame.Surface) -> None:
        """
        Draw permanent CTA banner at bottom center.
        Semi-transparent rect (Alpha 150), neon yellow text, rotates every 8 seconds.
        Positioned above TikTok comments area for maximum visibility.
        Surface is cached and rebuilt only when cta_message_index changes.

        Args:
            surface: Target surface to draw on (typically render_surface).
        """
        from .config import (
            SCREEN_WIDTH,
            COUNTRY_SHORTCUTS,
            GAME_MODE,
            CTA_BANNER_Y,
            CTA_BANNER_HEIGHT,
            CTA_BANNER_WIDTH,
            DISPLAY_FONT_NAMES,
        )

        if GAME_MODE != "COMMENT":
            return

        banner_width = min(SCREEN_WIDTH - 20, CTA_BANNER_WIDTH)
        banner_x = (SCREEN_WIDTH - banner_width) // 2
        banner_y = CTA_BANNER_Y

        # Rebuild banner surface only when the message index changes (every 8s)
        if self._cta_cached_index != self.cta_message_index or self._cta_surface is None:
            # Country to number mapping (inverse of COUNTRY_SHORTCUTS)
            country_to_num = {v: k for k, v in COUNTRY_SHORTCUTS.items() if k.isdigit()}

            # Build Smart CTA message based on current index and race state
            leader = self.physics_world.get_leader_country()
            lb = self.physics_world.get_leaderboard()
            second = lb[1][1] if len(lb) >= 2 else None
            second_num = country_to_num.get(second, "?") if second else "?"

            messages = [
                "ESCRIBE [NÚMERO] PARA AYUDAR A TU PAÍS",
                f"¿Dónde están los de {second or '?'}? ¡Escribe {second_num} para remontar!" if second else "ESCRIBE [NÚMERO] PARA AYUDAR A TU PAÍS",
                f"¡{leader or '?'} está ganando! ¡Detenlo enviando algo helado!" if leader else "ESCRIBE [NÚMERO] PARA AYUDAR A TU PAÍS",
                "¡Escribe el número de tu país para sumar puntos!",
            ]
            text = messages[self.cta_message_index % len(messages)]

            banner_height = CTA_BANNER_HEIGHT
            banner = pygame.Surface((banner_width, banner_height), pygame.SRCALPHA)
            banner.fill((0, 0, 0, 150))
            pygame.draw.rect(banner, (255, 255, 0, 100), (0, 0, banner_width, banner_height), 2, border_radius=6)

            font = _get_font(DISPLAY_FONT_NAMES[0], 21, bold=False)
            neon_yellow = (255, 255, 0)
            words = text.split()
            lines = []
            current = ""
            for w in words:
                test = f"{current} {w}".strip() if current else w
                if font.size(test)[0] <= banner_width - 14:
                    current = test
                else:
                    if current:
                        lines.append(current)
                    current = w
            if current:
                lines.append(current)
            lines = lines[:2]

            line_height = 25
            y_offset = (banner_height - len(lines) * line_height) // 2 + 1
            for line in lines:
                text_surf = self._render_text_enhanced(
                    line, font, neon_yellow,
                    outline_color=(0, 0, 0), outline_width=1,
                )
                rect = text_surf.get_rect(center=(banner_width // 2, y_offset + line_height // 2))
                banner.blit(text_surf, rect)
                y_offset += line_height

            self._cta_surface = banner
            self._cta_cached_index = self.cta_message_index

        surface.blit(self._cta_surface, (banner_x, banner_y))
    
    def _render_race_start_hud(self, alpha: int) -> None:
        """
        Render a fade-out HUD overlay at race start.
        Shows 'RACE STARTED!' message with fade effect.
        
        Args:
            alpha: Transparency value (0-255)
        """
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        # Create overlay surface
        overlay = pygame.Surface((SCREEN_WIDTH, 80), pygame.SRCALPHA)
        
        # Center position
        overlay_y = SCREEN_HEIGHT // 3
        
        # Semi-transparent dark background
        bg_alpha = min(alpha, 180)
        overlay.fill((0, 0, 0, bg_alpha))
        
        # "GO!" text with glow effect
        title_font = _get_font("Arial", 48, bold=True)
        subtitle_font = _get_font("Arial", 16, bold=True)

        # Main title
        title_color = (255, 215, 0)  # Gold
        title_text = "GO!"
        
        title_surf = self._render_text_enhanced(
            title_text,
            title_font,
            title_color,
            outline_color=(0, 0, 0),
            outline_width=3
        )
        
        # Apply alpha
        title_surf.set_alpha(alpha)
        
        # Center text
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 40))
        overlay.blit(title_surf, title_rect)
        
        # Subtitle
        subtitle_text = "Type # or SIGLA to vote!"
        subtitle_surf = self._render_text_with_shadow(
            subtitle_text,
            subtitle_font,
            (200, 200, 200),
            shadow_offset=1
        )
        subtitle_surf.set_alpha(alpha)
        subtitle_rect = subtitle_surf.get_rect(center=(SCREEN_WIDTH // 2, 70))
        overlay.blit(subtitle_surf, subtitle_rect)
        
        self.render_surface.blit(overlay, (0, overlay_y))
    
    def _render_global_ranking(self) -> None:
        """
        Render global ranking panel (Top 3 countries).
        Displays in IDLE state as an elegant panel.
        """
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        # Only render if we have data
        if not self.global_rank_data:
            return
        
        # Panel dimensions and position (top-right corner with margin)
        panel_width = 280
        panel_height = 160
        margin = 20
        panel_x = SCREEN_WIDTH - panel_width - margin
        panel_y = margin
        
        # Background panel with gradient
        panel_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        
        # Gradient background (dark blue to darker)
        for i in range(panel_height):
            ratio = i / panel_height
            r = int(15 + (25 - 15) * ratio)
            g = int(20 + (35 - 20) * ratio)
            b = int(40 + (55 - 40) * ratio)
            pygame.draw.line(panel_surface, (r, g, b, 220), (0, i), (panel_width, i))
        
        # Golden border
        pygame.draw.rect(panel_surface, (255, 215, 0, 200), (0, 0, panel_width, panel_height), 2, border_radius=10)
        
        self.render_surface.blit(panel_surface, (panel_x, panel_y))
        
        # Title: "*** RÉCORDS MUNDIALES ***"
        title_font = _get_font("Arial", 16, bold=True)
        title_text = "*** WORLD RECORDS ***"
        title_surface = self._render_text_enhanced(
            title_text,
            title_font,
            (255, 223, 128),  # Light gold
            outline_color=(0, 0, 0),
            outline_width=2
        )
        title_rect = title_surface.get_rect(center=(panel_x + panel_width // 2, panel_y + 20))
        self.render_surface.blit(title_surface, title_rect)

        # Render Top 3 countries
        entry_font = _get_font("Arial", 14, bold=True)
        medal_font = _get_font("Arial", 16, bold=True)
        
        start_y = panel_y + 50
        line_height = 32
        
        # Medal colors (gold, silver, bronze)
        medal_colors = [
            (255, 215, 0),   # Gold
            (192, 192, 192), # Silver
            (205, 127, 50)   # Bronze
        ]
        
        for i, entry in enumerate(self.global_rank_data[:3]):
            country = entry.get('country', 'Unknown')
            wins = entry.get('total_wins', 0)
            
            y_pos = start_y + i * line_height
            
            # Medal position (1º, 2º, 3º)
            medals = ['1º', '2º', '3º']
            medal = medals[i] if i < 3 else f"{i+1}º"
            medal_color = medal_colors[i] if i < 3 else (200, 200, 200)
            
            # Render medal with color
            medal_surface = medal_font.render(medal, True, medal_color)
            self.render_surface.blit(medal_surface, (panel_x + 15, y_pos))
            
            # Render country name with flag abbreviation
            country_abbrev = self._get_country_abbrev(country)
            entry_text = f"[{country_abbrev}] {country[:8]}: {wins}"
            entry_color = (255, 223, 128) if i == 0 else (220, 220, 220)  # Gold for 1st
            entry_surface = entry_font.render(entry_text, True, entry_color)
            self.render_surface.blit(entry_surface, (panel_x + 55, y_pos + 2))
        
        # Footer: last update time (optional)
        if self.global_rank_last_update > 0:
            footer_font = _get_font("Arial", 9)
            elapsed = time.time() - self.global_rank_last_update
            if elapsed < 60:
                footer_text = "Updated a few seconds ago"
            elif elapsed < 3600:
                footer_text = f"Updated {int(elapsed/60)}m ago"
            else:
                footer_text = f"Updated {int(elapsed/3600)}h ago"
            
            footer_surface = footer_font.render(footer_text, True, (150, 150, 150))
            footer_rect = footer_surface.get_rect(center=(panel_x + panel_width // 2, panel_y + panel_height - 10))
            self.render_surface.blit(footer_surface, footer_rect)
    
    def _render_global_ranking_futuristic(self) -> None:
        """
        Render two side-by-side ranking panels: all-time (left) and today (right).
        """
        from .config import SCREEN_WIDTH

        panel_w = 220
        panel_h = 210
        gap = 10
        total_w = panel_w * 2 + gap
        panel_x_left = (SCREEN_WIDTH - total_w) // 2
        panel_x_right = panel_x_left + panel_w + gap
        panel_y = 20

        glow_intensity = 0.7 + 0.3 * math.sin(self.ranking_3d_animation_time * 2.0)

        neon_colors = [
            (255, 215, 0),    # Gold
            (192, 192, 255),  # Silver
            (255, 150, 100),  # Bronze
            (150, 220, 180),  # 4th
            (180, 180, 255),  # 5th
        ]
        medals = ['1º', '2º', '3º', '4º', '5º']

        panels = [
            {
                "x": panel_x_left,
                "title": "HISTORICO",
                "border_color": (100, 200, 255),   # Cyan
                "title_color": (150, 220, 255),
                "data": self.global_rank_data[:5],
                "wins_key": "total_wins",
            },
            {
                "x": panel_x_right,
                "title": "HOY",
                "border_color": (100, 255, 160),   # Green
                "title_color": (120, 255, 180),
                "data": self.daily_rank_data[:5],
                "wins_key": "wins",
            },
        ]

        title_font = _get_font("Verdana", 13, bold=True)
        entry_font = _get_font("Verdana", 12, bold=True)
        medal_font = _get_font("Verdana", 13, bold=True)
        footer_font = _get_font("Verdana", 9)

        for panel in panels:
            px = panel["x"]
            border_color = panel["border_color"]
            border_alpha = int(220 * glow_intensity)

            # Background
            surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
            for i in range(panel_h):
                ratio = i / panel_h
                alpha = int(230 - 20 * ratio)
                r = int(15 + 5 * (1 - ratio))
                g = int(25 + 10 * (1 - ratio))
                b = int(45 + 15 * (1 - ratio))
                pygame.draw.line(surf, (r, g, b, alpha), (0, i), (panel_w, i))

            # Outer glow layers
            for i in range(3):
                a = int(border_alpha * (0.3 / (i + 1)))
                pygame.draw.rect(surf, (*border_color, a),
                                 (i, i, panel_w - i*2, panel_h - i*2), 2, border_radius=12 - i)

            # Main border
            pygame.draw.rect(surf, (*border_color, border_alpha),
                             (0, 0, panel_w, panel_h), 2, border_radius=12)

            # Top highlight
            highlight_a = int(120 * glow_intensity)
            pygame.draw.rect(surf, (200, 240, 255, highlight_a),
                             (3, 3, panel_w - 6, 6), 0, border_radius=9)

            self.render_surface.blit(surf, (px, panel_y))

            # Title
            title_surf = self._render_text_enhanced(
                panel["title"], title_font, panel["title_color"],
                outline_color=(0, 40, 80), outline_width=2
            )
            title_rect = title_surf.get_rect(center=(px + panel_w // 2, panel_y + 16))
            self.render_surface.blit(title_surf, title_rect)

            # Divider line
            pygame.draw.line(self.render_surface, (*border_color, 160),
                             (px + 8, panel_y + 28), (px + panel_w - 8, panel_y + 28), 1)

            # Entries
            data = panel["data"]
            wins_key = panel["wins_key"]
            start_y = panel_y + 38
            line_h = 30

            if not data:
                if self.global_rank_loading:
                    placeholder_text = "Cargando..."
                    placeholder_color = (180, 220, 255)
                else:
                    placeholder_text = "Sin datos"
                    placeholder_color = (160, 160, 160)
                no_data_surf = footer_font.render(placeholder_text, True, placeholder_color)
                no_data_rect = no_data_surf.get_rect(center=(px + panel_w // 2, panel_y + panel_h // 2))
                self.render_surface.blit(no_data_surf, no_data_rect)
            else:
                for i, entry in enumerate(data):
                    country = entry.get('country', '?')
                    wins = entry.get(wins_key, 0)
                    y_pos = start_y + i * line_h
                    medal_color = neon_colors[i] if i < 5 else (200, 200, 200)
                    medal_text = medals[i] if i < 5 else f"{i+1}º"

                    # Medal glow
                    glow_s = medal_font.render(medal_text, True, medal_color)
                    for off in [(1, 1), (-1, -1)]:
                        self.render_surface.blit(glow_s, (px + 8 + off[0], y_pos + off[1]))
                    self.render_surface.blit(glow_s, (px + 8, y_pos))

                    # Country + wins
                    entry_text = f"{country[:10]}  {wins}W"
                    entry_color = (255, 255, 255) if i == 0 else (210, 235, 255)
                    entry_surf = entry_font.render(entry_text, True, entry_color)
                    self.render_surface.blit(entry_surf, (px + 38, y_pos + 1))

            # Footer
            if self.global_rank_last_update > 0 and panel["wins_key"] == "total_wins":
                elapsed = time.time() - self.global_rank_last_update
                if elapsed < 60:
                    footer_text = "actualizado ahora"
                elif elapsed < 3600:
                    footer_text = f"hace {int(elapsed/60)}m"
                else:
                    footer_text = f"hace {int(elapsed/3600)}h"
                footer_surf = footer_font.render(footer_text, True, (150, 200, 255))
                footer_rect = footer_surf.get_rect(center=(px + panel_w // 2, panel_y + panel_h - 10))
                self.render_surface.blit(footer_surf, footer_rect)
    
    def _render_3d_ranking_visualization(self) -> None:
        """
        Render 3D isometric visualization of country rankings.
        Creates a futuristic "staircase" or "tracks" effect with flags on neon lines.
        """
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        if not self.global_rank_data or len(self.global_rank_data) < 3:
            return
        
        # Center of visualization
        center_x = SCREEN_WIDTH // 2
        center_y = SCREEN_HEIGHT // 2 + 80
        
        # Isometric projection parameters
        track_count = min(8, len(self.global_rank_data))  # Show up to 8 countries
        track_spacing = 35  # Vertical spacing between tracks
        track_length = 400  # Horizontal length of each track
        track_start_x = center_x - track_length // 2
        perspective_factor = 0.3  # How much tracks recede into distance
        
        # Neon track colors (rainbow spectrum)
        neon_colors = [
            (255, 100, 100),   # Red
            (255, 150, 50),    # Orange
            (255, 220, 0),     # Yellow
            (150, 255, 100),   # Green
            (100, 200, 255),   # Cyan
            (150, 100, 255),   # Purple
            (255, 100, 200),   # Pink
            (200, 200, 255)    # Light blue
        ]
        
        # Draw tracks (isometric perspective)
        for i, entry in enumerate(self.global_rank_data[:track_count]):
            country = entry.get('country', 'Unknown')
            wins = entry.get('total_wins', 0)
            
            # Calculate track position (higher rank = higher on screen, closer to viewer)
            track_y = center_y - (i * track_spacing)
            track_width = 8 - (i * 0.5)  # Tracks get thinner as they recede
            track_width = max(3, track_width)
            
            # Perspective: tracks further back are shorter and offset
            perspective_offset = i * perspective_factor * 20
            track_x_start = track_start_x + perspective_offset
            track_x_end = track_start_x + track_length - perspective_offset
            
            # Track color (cycling through neon colors)
            track_color = neon_colors[i % len(neon_colors)]
            
            # Draw track with glow effect
            # Outer glow
            for glow_radius in range(3, 0, -1):
                alpha = 50 // (glow_radius + 1)
                glow_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
                pygame.draw.line(
                    glow_surf,
                    (*track_color, alpha),
                    (track_x_start, track_y),
                    (track_x_end, track_y),
                    int(track_width) + glow_radius * 2
                )
                self.render_surface.blit(glow_surf, (0, 0))
            
            # Main track line
            pygame.draw.line(
                self.render_surface,
                track_color,
                (track_x_start, track_y),
                (track_x_end, track_y),
                int(track_width)
            )
            
            # Flag position on track (based on wins, animated)
            max_wins = max((e.get('total_wins', 0) for e in self.global_rank_data[:track_count]), default=1)
            max_wins = max(max_wins, 1)  # Prevent division by zero
            progress = wins / max_wins
            progress = min(1.0, max(0.0, progress))
            
            # Animated position (subtle movement)
            anim_offset = math.sin(self.ranking_3d_animation_time * 1.5 + i) * 5
            flag_x = track_x_start + (track_length - perspective_offset * 2) * progress + anim_offset
            flag_y = track_y
            
            # Draw flag circle/emblem (simplified - using country abbreviation)
            flag_radius = 20 - (i * 1.5)
            flag_radius = max(12, flag_radius)
            
            # Flag glow
            for glow in range(3):
                glow_alpha = 100 // (glow + 1)
                pygame.draw.circle(
                    self.render_surface,
                    (*track_color, glow_alpha),
                    (int(flag_x), int(flag_y)),
                    int(flag_radius) + glow * 2
                )
            
            # Flag background circle
            pygame.draw.circle(
                self.render_surface,
                (30, 30, 50),
                (int(flag_x), int(flag_y)),
                int(flag_radius)
            )
            pygame.draw.circle(
                self.render_surface,
                track_color,
                (int(flag_x), int(flag_y)),
                int(flag_radius),
                2
            )
            
            # Country abbreviation on flag
            abbrev = self._get_country_abbrev(country)
            flag_font = _get_font("Arial", max(8, int(flag_radius * 0.8)), bold=True)
            abbrev_surf = flag_font.render(abbrev, True, (255, 255, 255))
            abbrev_rect = abbrev_surf.get_rect(center=(int(flag_x), int(flag_y)))
            self.render_surface.blit(abbrev_surf, abbrev_rect)
            
            # Particle effects around flags (sparkles)
            particle_count = 8
            for p in range(particle_count):
                angle = (self.ranking_3d_animation_time * 2.0 + p * (2 * math.pi / particle_count))
                particle_dist = flag_radius + 15 + math.sin(self.ranking_3d_animation_time * 3 + p) * 5
                particle_x = flag_x + math.cos(angle) * particle_dist
                particle_y = flag_y + math.sin(angle) * particle_dist
                
                # Twinkling particles
                twinkle = (math.sin(self.ranking_3d_animation_time * 5 + p) + 1) / 2
                particle_size = int(2 + twinkle * 3)
                particle_alpha = int(150 * twinkle)
                
                particle_surf = pygame.Surface((particle_size * 2, particle_size * 2), pygame.SRCALPHA)
                pygame.draw.circle(
                    particle_surf,
                    (*track_color, particle_alpha),
                    (particle_size, particle_size),
                    particle_size
                )
                self.render_surface.blit(
                    particle_surf,
                    (int(particle_x - particle_size), int(particle_y - particle_size))
                )
        
        # Central arch (finish line / achievement gateway)
        arch_center_x = center_x
        arch_center_y = center_y - (track_count * track_spacing) - 40
        arch_radius = 120
        arch_width = 8
        
        # Animated arch glow
        arch_glow = 0.7 + 0.3 * math.sin(self.ranking_3d_animation_time * 1.5)
        arch_color = (100, 200, 255)  # Cyan
        
        # Draw semi-circular arch (top half)
        for i in range(5):
            alpha = int(200 * arch_glow / (i + 1))
            glow_radius = arch_radius + i * 3
            arch_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            pygame.draw.arc(
                arch_surf,
                (*arch_color, alpha),
                (arch_center_x - glow_radius, arch_center_y - glow_radius, glow_radius * 2, glow_radius * 2),
                0,
                math.pi,
                arch_width + i * 2
            )
            self.render_surface.blit(arch_surf, (0, 0))
    
    def _get_country_abbrev(self, country: str) -> str:
        """
        Get country abbreviation for display.
        
        Args:
            country: Country name (e.g., "Argentina", "Brasil")
            
        Returns:
            Country abbreviation (e.g., "ARG", "BRA")
        """
        abbrev_map = {
            'Argentina': 'ARG',
            'Brasil': 'BRA',
            'Mexico': 'MEX',
            'España': 'ESP',
            'Colombia': 'COL',
            'Chile': 'CHI',
            'Peru': 'PER',
            'Venezuela': 'VEN',
            'Uruguay': 'URU',
        }
        return abbrev_map.get(country, '???')
    
    def _return_to_idle(self) -> None:
        """Return to IDLE state and save winner info."""
        # Stop victory sound when returning to IDLE
        self.audio_manager.stop_victory_sound()

        # Save winner info before reset
        if self.physics_world.winner:
            self.last_winner = self.physics_world.winner
            winner_racer = self.physics_world.racers[self.physics_world.winner]
            self.last_winner_distance = winner_racer.body.position.x - self.physics_world.start_x

        # 3️⃣ RESET AUTOMÁTICO: Llamar reset_race() y limpiar textos flotantes
        self.physics_world.reset_race()  # Ya resetea banderas a RACE_START_X

        # Limpiar textos flotantes
        self.floating_texts.clear()

        # Limpiar partículas también para un reset limpio
        self.particles.clear()
    
        # Clear user assignments
        self.user_country_cache.clear()
        self.country_player_count.clear()
        
        # Clear keyword binding assignments
        self.user_assignments.clear()
        self.users_notified.clear()
        self.last_join_time.clear()
        
        # Change to IDLE state
        self.game_state = 'IDLE'
        self.idle_animation_time = 0.0

        # 👑 Clear captain system
        self.session_points.clear()
        self.current_captains.clear()
        self.captain_change_timer.clear()
        
        # ☁️ Reset cloud sync flag for next race
        self.race_synced = False

        # Invalidate leaderboard cache for next race
        self._leaderboard_cache = None

        # 🎬 Reset winner animation time for next race
        self.winner_animation_time = 0.0
        self.winner_scale_pulse = 1.0
        self.winner_glow_alpha = 0

        # 📍 Reset shortcuts panel position for next race
        self.shortcuts_panel_position = "right"
        
        # 📺 Reset HUD timing for next race
        self.race_start_time = None
        self.ticker_offset = 0.0
        
        # 🔥 Reset combo system
        self.combo_tracker.clear()
        self.combo_counts.clear()
        self.on_fire_countries.clear()
        self.motion_trails.clear()
        self.motion_trail_history.clear()
        self.combo_flashes.clear()
        
        # 🌙 Deactivate lunar gravity if still running
        if self._lunar_active:
            self._deactivate_lunar_gravity()
        self._lunar_overlay_alpha = 0

        # 🏁 Reset final stretch
        self.final_stretch_triggered = False
        self.final_stretch_time = 0.0
        
        # 🏆 Reset victory sequence
        self._reset_victory_sequence()
        
        # Restore original parallax speed and deactivate warp/tension
        if self.background_manager:
            self.background_manager.set_scroll_speed(self.original_parallax_speed)
            self.background_manager.deactivate_warp_mode()
            self.background_manager.deactivate_tension_mode()
        
        # 🎵 Restore normal background music
        self.audio_manager.play_bgm_normal(fade_in_ms=1500)
        
        logger.info("🎮 Game state: IDLE (race reset complete)")
    
    def on_physics_race_reset(self) -> None:
        """
        Reset per-race game state when physics auto-resets (new race, stay RACING).
        Fixes: total counter, victory zoom, final stretch not resetting between races.
        """
        # Stop victory sound when starting a new race
        self.audio_manager.stop_victory_sound()

        self.floating_texts.clear()
        self.particles.clear()
        self.user_country_cache.clear()
        self.country_player_count.clear()
        self.user_assignments.clear()
        self.users_notified.clear()
        self.last_join_time.clear()
        self.session_points.clear()
        self.current_captains.clear()
        self.captain_change_timer.clear()
        self.race_synced = False
        self._leaderboard_cache = None
        self.winner_animation_time = 0.0
        self.winner_scale_pulse = 1.0
        self.winner_glow_alpha = 0
        self.combo_tracker.clear()
        self.combo_counts.clear()
        self.on_fire_countries.clear()
        self.motion_trails.clear()
        self.motion_trail_history.clear()
        self.combo_flashes.clear()
        self.final_stretch_triggered = False
        self.final_stretch_time = 0.0
        self._reset_victory_sequence()
        if self.background_manager and getattr(self, "original_parallax_speed", None) is not None:
            self.background_manager.set_scroll_speed(self.original_parallax_speed)
            self.background_manager.deactivate_warp_mode()
            self.background_manager.deactivate_tension_mode()

        # 🎵 Restore normal background music
        self.audio_manager.play_bgm_normal(fade_in_ms=1500)
        logger.info("🔄 Game state reset for new race (physics auto-reset)")
    
    def _transition_to_racing(self) -> None:
        """
        Transition from IDLE to RACING state.
        Sets up timing for HUD animations and spotlight.
        """
        import time
        # Stop victory sound when starting a new race from IDLE
        self.audio_manager.stop_victory_sound()

        self.game_state = 'RACING'
        self._on_real_activity()  # Reset activity timer at race start
        self.race_start_time = time.time()

        # Initialize spotlight position to first racer
        if self.physics_world.racers:
            first_country = list(self.physics_world.racers.keys())[0]
            racer = self.physics_world.racers[first_country]
            self.spotlight_current_pos = (racer.body.position.x, racer.body.position.y)
            self.spotlight_target_pos = self.spotlight_current_pos

        # Reset CTA banner to first message for new race
        self.cta_last_rotation_time = 0.0
        self.cta_message_index = 0
        
        # Reset combo system
        self.combo_tracker.clear()
        self.combo_counts.clear()
        self.on_fire_countries.clear()
        self.motion_trails.clear()
        self.motion_trail_history.clear()
        self.combo_flashes.clear()
        self.final_stretch_triggered = False
        
        # Store original parallax speed
        if self.background_manager:
            self.original_parallax_speed = self.background_manager.scroll_speed
    
    def register_combo_event(self, country: str) -> int:
        """
        Register a vote/gift for combo tracking.
        
        Args:
            country: Country that received the event
        
        Returns:
            Current combo count for this country
        """
        import time
        current_time = time.time()
        
        # Initialize tracker if needed
        if country not in self.combo_tracker:
            self.combo_tracker[country] = []
        
        # Add new timestamp
        self.combo_tracker[country].append(current_time)
        
        # Clean old timestamps (outside combo window)
        cutoff = current_time - self.combo_window
        self.combo_tracker[country] = [
            t for t in self.combo_tracker[country] if t > cutoff
        ]
        
        # Calculate current combo
        combo_count = len(self.combo_tracker[country])
        old_count = self.combo_counts.get(country, 0)
        self.combo_counts[country] = combo_count
        
        # Check for combo milestone
        if combo_count >= self.combo_threshold and combo_count > old_count:
            self._show_combo_text(country, combo_count)
            # 🔥 Play combo fire sound when combo increases (scaled by level)
            combo_level = min(5, combo_count // 2)  # Scale to 0-5
            self.audio_manager.play_combo_fire_sound(combo_level=combo_level)
            # 🎤 Announce combo (only for milestone combos to avoid spam)
            # Skip TTS during TEST FIRE (F key) to prevent queue flood and crash
            if combo_count % 5 == 0 and not getattr(self, "_test_fire_active", False):
                self.audio_manager.announce_combo(country, combo_level)
        
        # Check for ON FIRE state
        if combo_count >= self.on_fire_threshold:
            if country not in self.on_fire_countries:
                self.on_fire_countries.add(country)
                self._trigger_on_fire(country)
        else:
            if country in self.on_fire_countries:
                self.on_fire_countries.discard(country)
        
        return combo_count
    
    def _show_combo_text(self, country: str, count: int) -> None:
        """
        Display floating combo text above the country's flag.
        Adds elastic pulse effect and flash on milestones.
        
        Args:
            country: Country with combo
            count: Current combo count
        """
        if country not in self.physics_world.racers:
            return
        
        racer = self.physics_world.racers[country]
        x = racer.body.position.x
        y = racer.body.position.y
        
        # Color gradient based on combo level
        if count >= 15:
            color = (255, 50, 50)  # Red for extreme combos
        elif count >= 10:
            color = (255, 100, 0)  # Orange for ON FIRE
        else:
            color = (255, 200, 50)  # Yellow for regular combo
        
        from .config import SCREEN_WIDTH, FLOATING_TEXT_TOP_Y
        combo_text = f"COMBO x{count}!"
        base_font_size = 22 if count % 5 == 0 else 16
        self.floating_texts.append(
            FloatingText(
                text=combo_text,
                x=SCREEN_WIDTH / 2,
                y=FLOATING_TEXT_TOP_Y,
                color=color,
                lifespan=50,
                max_lifespan=50,
                font_size=base_font_size,
                dy=-1.0
            )
        )
        
        # ✨ Add flash effect on milestone combos (5, 10, 15, 20...)
        if count % 5 == 0:
            flash_intensity = min(1.0, 0.5 + (count / 20))  # Brighter for higher combos
            self.combo_flashes.append(
                ComboFlash(
                    country=country,
                    time=0.0,
                    duration=0.3,
                    intensity=flash_intensity
                )
            )
        
        # Shake based on combo level
        if count >= 15:
            self.screen_shaker.impact_shake()
        elif count >= 10:
            self.screen_shaker.micro_shake()
    
    def _trigger_on_fire(self, country: str) -> None:
        """
        Trigger the ON FIRE state for a country.
        
        Args:
            country: Country entering ON FIRE state
        """
        if country not in self.physics_world.racers:
            return
        
        from .config import SCREEN_WIDTH, FLOATING_TEXT_TOP_Y
        # Big announcement at top
        self.floating_texts.append(
            FloatingText(
                text="ON FIRE!",
                x=SCREEN_WIDTH / 2,
                y=FLOATING_TEXT_TOP_Y,
                color=(255, 100, 0),
                lifespan=80,
                max_lifespan=80,
                font_size=20,
                dy=-1.0
            )
        )
        
        # Initialize motion trail history
        if country not in self.motion_trail_history:
            self.motion_trail_history[country] = []
        if country not in self.motion_trails:
            self.motion_trails[country] = []
        
        # Impact shake
        self.screen_shaker.impact_shake()
        
        # 🔥 Play combo fire sound with appropriate level
        combo_level = min(5, self.combo_counts.get(country, 10) // 2)  # Scale to 0-5
        self.audio_manager.play_combo_fire_sound(combo_level=combo_level)
        
        # 🎤 Announce combo achievement (skip during TEST FIRE to avoid TTS flood)
        if not getattr(self, "_test_fire_active", False):
            self.audio_manager.announce_combo(country, combo_level)
        
        logger.info(f"🔥 {country} is ON FIRE!")
    
    def _update_motion_trails(self, dt: float) -> None:
        """
        Update motion trails for all countries.
        Creates neon streak effects using position history.
        
        Args:
            dt: Delta time in seconds
        """
        # Update position history for all racers
        for country, racer in self.physics_world.racers.items():
            x = float(racer.body.position.x)
            y = float(racer.body.position.y)
            
            if country not in self.motion_trail_history:
                self.motion_trail_history[country] = []
            
            # Add current position to history
            history = self.motion_trail_history[country]
            history.append((x, y))
            
            # Limit history length based on ON FIRE status
            max_history = 15 if country in self.on_fire_countries else 8
            while len(history) > max_history:
                history.pop(0)
        
        # Build trail segments from history for ON FIRE countries
        for country in self.on_fire_countries:
            if country not in self.motion_trail_history:
                continue
            if country not in self.physics_world.racers:
                continue
            
            history = self.motion_trail_history[country]
            if len(history) < 2:
                continue
            
            racer = self.physics_world.racers[country]
            base_color = racer.color
            
            # Return old segments to pool, then rebuild
            for seg in self.motion_trails.get(country, []):
                self._motion_trail_segment_pool.append(seg)
            self.motion_trails[country] = []
            
            for i in range(len(history) - 1):
                x1, y1 = history[i]
                x2, y2 = history[i + 1]
                alpha = 255 * (i + 1) / len(history)
                thickness = 1 if i < len(history) // 2 else 2
                if country in self.on_fire_countries:
                    thickness += 1
                if country in self.on_fire_countries and i < len(history) - 3:
                    y1 += random.uniform(-1, 1)
                    y2 += random.uniform(-1, 1)
                
                if self._motion_trail_segment_pool:
                    segment = self._motion_trail_segment_pool.pop()
                    segment.x1, segment.y1 = x1, y1
                    segment.x2, segment.y2 = x2, y2
                    segment.color = base_color
                    segment.alpha = alpha
                    segment.thickness = thickness
                else:
                    segment = MotionTrailSegment(
                        x1=x1, y1=y1, x2=x2, y2=y2,
                        color=base_color, alpha=alpha, thickness=thickness
                    )
                self.motion_trails[country].append(segment)
    
    def _update_combo_flashes(self, dt: float) -> None:
        """Update combo flash effects."""
        alive_flashes = []
        for flash in self.combo_flashes:
            flash.time += dt
            if flash.time < flash.duration:
                alive_flashes.append(flash)
        self.combo_flashes = alive_flashes
    
    def _render_motion_trails(self) -> None:
        """
        Render motion trails using pygame.draw.line for crisp edges.
        Creates neon streak effect with country colors.
        """
        for country, segments in self.motion_trails.items():
            is_on_fire = country in self.on_fire_countries
            
            for segment in segments:
                # Calculate faded color based on alpha
                alpha_ratio = segment.alpha / 255
                
                r = int(segment.color[0] * alpha_ratio)
                g = int(segment.color[1] * alpha_ratio)
                b = int(segment.color[2] * alpha_ratio)
                
                # Draw the main line (crisp)
                pygame.draw.line(
                    self.render_surface,
                    (r, g, b),
                    (int(segment.x1), int(segment.y1)),
                    (int(segment.x2), int(segment.y2)),
                    segment.thickness
                )
                
                # Add glow effect for ON FIRE (draw slightly thicker underneath)
                if is_on_fire and segment.alpha > 100:
                    glow_r = min(255, int(r * 0.5))
                    glow_g = min(255, int(g * 0.5))
                    glow_b = min(255, int(b * 0.5))
                    
                    pygame.draw.line(
                        self.render_surface,
                        (glow_r, glow_g, glow_b),
                        (int(segment.x1), int(segment.y1) - 1),
                        (int(segment.x2), int(segment.y2) - 1),
                        1
                    )
                    pygame.draw.line(
                        self.render_surface,
                        (glow_r, glow_g, glow_b),
                        (int(segment.x1), int(segment.y1) + 1),
                        (int(segment.x2), int(segment.y2) + 1),
                        1
                    )
    
    def _render_combo_flashes(self) -> None:
        """Render flash ring effects on flags into a shared layer then blit once."""
        if not self.combo_flashes or self._flash_layer is None:
            return
        self._flash_layer.fill((0, 0, 0, 0))
        has_any = False
        for flash in self.combo_flashes:
            if flash.country not in self.physics_world.racers:
                continue

            racer = self.physics_world.racers[flash.country]
            x = int(racer.body.position.x)
            y = int(racer.body.position.y)

            # Flash fades out over duration
            progress = flash.time / flash.duration
            alpha = int(255 * (1.0 - progress) * flash.intensity)

            # Expanding ring effect
            radius = int(20 + 30 * progress)

            pygame.draw.circle(
                self._flash_layer,
                (255, 255, 255, alpha),
                (x, y),
                radius,
                3  # Ring, not filled
            )
            has_any = True
        if has_any:
            self.render_surface.blit(self._flash_layer, (0, 0))
    
    def _check_final_stretch(self) -> None:
        """
        Check if leader has reached final stretch (80% of track).
        Triggers announcement and speed boost.
        """
        if self.final_stretch_triggered or self.game_state != 'RACING':
            return
        
        leader_info = self.physics_world.get_leader()
        if not leader_info:
            return
        
        leader_country = leader_info[0]
        if leader_country not in self.physics_world.racers:
            return
        
        racer = self.physics_world.racers[leader_country]
        track_length = self.physics_world.finish_line_x - self.physics_world.start_x
        current_progress = racer.body.position.x - self.physics_world.start_x
        progress_ratio = current_progress / track_length if track_length > 0 else 0
        
        if progress_ratio >= self.final_stretch_threshold:
            self._trigger_final_stretch()
    
    def _trigger_final_stretch(self) -> None:
        """Trigger final stretch announcement and effects."""
        self.final_stretch_triggered = True
        self.final_stretch_time = 0.0
        
        # Boost parallax speed by 50%
        if self.background_manager:
            self.background_manager.set_scroll_speed(self.original_parallax_speed * 1.5)
            # 🚀 Activate WARP MODE for triple speed lines
            self.background_manager.activate_warp_mode()
            # 🔥 Activate TENSION MODE - red/orange theme for intensity
            self.background_manager.activate_tension_mode()
        
        # 🎵 Switch to tension background music
        self.audio_manager.play_bgm_tension(fade_in_ms=1500)
        
        # Impact shake
        self.screen_shaker.big_impact_shake()
        
        # 🏁 Play final stretch sound
        self.audio_manager.play_final_stretch_sound()
        
        # 🎤 Announce final stretch
        leader_info = self.physics_world.get_leader()
        if leader_info:
            leader_country = leader_info[0]
            self.audio_manager.announce_final_stretch(leader_country)
        
        logger.info("🏁 FINAL STRETCH triggered with WARP + TENSION MODE!")

        # 20% chance to trigger Lunar Gravity during Final Stretch
        if not self._lunar_active and random.random() < 0.20:
            self._activate_lunar_gravity()
    
    def _check_race_events(self, dt: float) -> None:
        """
        Check for race events like overtakes and close races for TTS announcements.
        
        Args:
            dt: Delta time since last frame
        """
        import time
        current_time = time.time()
        
        if self.game_state != 'RACING' or self.physics_world.race_finished:
            return
        
        # Get current leaderboard
        leader_info = self.physics_world.get_leader()
        if not leader_info:
            return
        
        current_leader = leader_info[0]
        
        # Track current positions
        current_positions = {}
        for country, racer in self.physics_world.racers.items():
            current_positions[country] = racer.body.position.x
        
        # Check for leader change
        if self._last_leader and self._last_leader != current_leader:
            # Leader changed - this is an overtake!
            if (current_time - self._last_overtake_announcement) >= self._overtake_cooldown:
                self.audio_manager.announce_overtake(current_leader, self._last_leader)
                self._last_overtake_announcement = current_time
                logger.debug(f"🎤 Overtake: {current_leader} overtook {self._last_leader}")
        
        # Check for overtakes (position changes)
        if self._last_positions:
            for country, current_pos in current_positions.items():
                if country in self._last_positions:
                    last_pos = self._last_positions[country]
                    # Check if this country overtook someone
                    for other_country, other_last_pos in self._last_positions.items():
                        if (other_country != country and 
                            other_country in current_positions and
                            last_pos < other_last_pos and  # Was behind
                            current_pos > current_positions[other_country]):  # Now ahead
                            # Overtake detected!
                            if (current_time - self._last_overtake_announcement) >= self._overtake_cooldown:
                                self.audio_manager.announce_overtake(country, other_country)
                                self._last_overtake_announcement = current_time
                                logger.debug(f"🎤 Overtake: {country} overtook {other_country}")
                                break
        
        # Check for close race (top 2 are very close)
        sorted_racers = sorted(
            current_positions.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        if len(sorted_racers) >= 2:
            leader_pos = sorted_racers[0][1]
            second_pos = sorted_racers[1][1]
            gap = leader_pos - second_pos
            
            # Close race if gap is less than 5% of track length
            track_length = self.physics_world.finish_line_x - self.physics_world.start_x
            close_threshold = track_length * 0.05  # 5% of track
            
            if gap < close_threshold and gap > 0:
                if (current_time - self._last_close_race_announcement) >= self._close_race_cooldown:
                    leader_country = sorted_racers[0][0]
                    chaser_country = sorted_racers[1][0]
                    self.audio_manager.announce_close_race(leader_country, chaser_country)
                    self._last_close_race_announcement = current_time
                    logger.debug(f"🎤 Close race: {leader_country} vs {chaser_country}")
        
        # Update tracking
        self._last_leader = current_leader
        self._last_positions = current_positions.copy()
    
    def _render_final_stretch_announcement(self) -> None:
        """Render the FINAL STRETCH announcement with pulsing glow."""
        if not self.final_stretch_triggered:
            return
        
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        # Animation duration: 3 seconds
        if self.final_stretch_time > 3.0:
            return  # Stop showing after 3 seconds
        
        # Pulsing effect
        pulse = 0.5 + 0.5 * math.sin(self.final_stretch_time * 8.0)
        
        # Calculate alpha (fade in then out)
        if self.final_stretch_time < 0.3:
            alpha = int(255 * (self.final_stretch_time / 0.3))
        elif self.final_stretch_time > 2.5:
            alpha = int(255 * (1.0 - (self.final_stretch_time - 2.5) / 0.5))
        else:
            alpha = 255
        
        # Create overlay
        overlay = pygame.Surface((SCREEN_WIDTH, 100), pygame.SRCALPHA)
        
        # Background with pulsing alpha
        bg_alpha = int(150 * pulse)
        overlay.fill((0, 0, 0, bg_alpha))
        
        # Main text with glow
        font = _get_font("Arial", 36, bold=True)

        # Glow effect (multiple layers)
        glow_color = (255, int(100 + 100 * pulse), 0)  # Orange pulsing
        text = "FINAL STRETCH!"
        
        text_surf = self._render_text_enhanced(
            text,
            font,
            glow_color,
            outline_color=(0, 0, 0),
            outline_width=4
        )
        text_surf.set_alpha(alpha)
        
        # Center text
        text_rect = text_surf.get_rect(center=(SCREEN_WIDTH // 2, 50))
        overlay.blit(text_surf, text_rect)
        
        # Position in upper third of screen
        self.render_surface.blit(overlay, (0, SCREEN_HEIGHT // 4))
    
    def _render_stress_test_banner(self) -> None:
        """Draw 'STRESS TEST ACTIVE' banner when manual stress test (K) is running."""
        from .config import SCREEN_WIDTH
        
        overlay = pygame.Surface((SCREEN_WIDTH, 36), pygame.SRCALPHA)
        overlay.fill((180, 0, 0, 200))
        font = _get_font("Arial", 20, bold=True)
        text = font.render("STRESS TEST ACTIVE", True, (255, 255, 255))
        r = text.get_rect(center=(SCREEN_WIDTH // 2, 18))
        overlay.blit(text, r)
        self.render_surface.blit(overlay, (0, 0))
    
    def _render_hype_timer(self, surface: pygame.Surface) -> None:
        """Render the hype timer countdown in the CTA banner slot (Y=36-90)."""
        from .config import SCREEN_WIDTH, CTA_BANNER_Y, CTA_BANNER_HEIGHT, CTA_BANNER_WIDTH

        elapsed = time.time() - self._hype_timer_start
        remaining = max(0.0, HYPE_TIMER_INTERVAL - elapsed)
        mins = int(remaining) // 60
        secs = int(remaining) % 60

        urgency = remaining <= HYPE_TIMER_URGENCY_SECS

        # Blink at 2 Hz when urgent
        if urgency and int(time.time() * 2) % 2 == 0:
            return

        # Color ramp
        if remaining > 30:
            color = (80, 255, 80)
        elif remaining > 10:
            color = (255, 200, 0)
        else:
            color = (255, 40, 40)

        # Pulse scale when urgent
        base_scale = 1.0
        if urgency:
            base_scale = 1.0 + abs(0.12 * math.sin(time.time() * 10))

        # Measure content to size the box tightly
        label_font = pygame.font.SysFont("monospace", 15, bold=True)
        label_surf = label_font.render(HYPE_TIMER_LABEL, True, (220, 220, 255))
        time_font_size = max(22, int(30 * base_scale))
        time_font = pygame.font.SysFont("monospace", time_font_size, bold=True)
        time_surf = time_font.render(f"{mins:01d}:{secs:02d}", True, color)

        # Banner geometry — compact width based on content
        padding = 14
        gap = 10
        banner_w = padding + label_surf.get_width() + gap + time_surf.get_width() + padding
        banner_x = (SCREEN_WIDTH - banner_w) // 2
        banner_y = CTA_BANNER_Y + self._hud_offset
        banner_h = CTA_BANNER_HEIGHT

        # Background
        bg = pygame.Surface((banner_w, banner_h), pygame.SRCALPHA)
        bg.fill((10, 10, 20, 180))
        surface.blit(bg, (banner_x, banner_y))

        # Colored border
        pygame.draw.rect(surface, color, (banner_x, banner_y, banner_w, banner_h),
                         width=2, border_radius=6)

        # Label "SAMBA EN" — left side, vertically centered
        lx = banner_x + padding
        ly = banner_y + (banner_h - label_surf.get_height()) // 2
        surface.blit(label_surf, (lx, ly))

        # Big countdown "M:SS" — right side, vertically centered
        tx = banner_x + banner_w - time_surf.get_width() - padding
        ty = banner_y + (banner_h - time_surf.get_height()) // 2
        surface.blit(time_surf, (tx, ty))

    # ==================== EPIC VICTORY SEQUENCE ====================

    def _trigger_victory_sequence(self, winner_country: str, winner_captain: str) -> None:
        """
        Trigger the epic victory sequence with all effects.
        
        Args:
            winner_country: The winning country
            winner_captain: Username of the captain
        """
        from .config import GAME_MODE
        
        self.victory_sequence_active = True
        self.victory_sequence_time = 0.0
        
        # Set up zoom target (winner position)
        if winner_country in self.physics_world.racers:
            racer = self.physics_world.racers[winner_country]
            self.victory_zoom_center = (racer.body.position.x, racer.body.position.y)
        
        self.victory_zoom_target = 1.12  # Zoom in 12% (subtle)
        self.victory_zoom_level = 1.0
        
        # Store captain info for monetization message
        self.victory_winner_captain = winner_captain
        self.victory_was_gift_mode = (GAME_MODE == "GIFT")
        
        # Activate slow motion
        self.slow_motion_active = True
        
        # Start confetti
        self._spawn_victory_confetti()
        
        # Victory banner scale starts at 0 for entrance animation
        self.victory_banner_scale = 0.0
        
        logger.info(f"🏆 Epic victory sequence triggered for {winner_country} - {winner_captain}")
    
    def _update_victory_sequence(self, dt: float) -> None:
        """
        Update all victory sequence effects.
        
        Args:
            dt: Delta time (original, not slowed)
        """
        self.victory_sequence_time += dt
        
        # 1. ZOOM INTERPOLATION
        zoom_speed = 2.0  # How fast to zoom
        self.victory_zoom_level += (self.victory_zoom_target - self.victory_zoom_level) * zoom_speed * dt
        
        # 2. BANNER SCALE (elastic entrance)
        if self.victory_banner_scale < 1.0:
            t = min(1.0, self.victory_sequence_time / 0.5)  # 0.5s to full scale
            # Elastic overshoot
            self.victory_banner_scale = 1.0 + 0.3 * math.sin(t * math.pi) - 0.3 * t
            if t >= 1.0:
                self.victory_banner_scale = 1.0
        
        # 3. SLOW MOTION DURATION
        if self.victory_sequence_time > self.slow_motion_duration:
            self.slow_motion_active = False
        
        # 4. UPDATE CONFETTI
        self._update_confetti(dt)
        
        # 5. SPAWN MORE CONFETTI (continuous during victory)
        if len(self.confetti_particles) < self.max_confetti and self.victory_sequence_time < 5.0:
            if random.random() < 0.3:  # 30% chance per frame
                self._spawn_confetti_particle()
    
    def _spawn_victory_confetti(self) -> None:
        """Spawn initial burst of confetti particles."""
        from .config import SCREEN_WIDTH
        
        for _ in range(80):  # Initial burst
            self._spawn_confetti_particle()
    
    def _spawn_confetti_particle(self) -> None:
        """Spawn a single confetti particle from the top."""
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        if len(self.confetti_particles) >= self.max_confetti:
            return
        
        colors = [
            (255, 215, 0), (255, 0, 100), (0, 200, 255), (100, 255, 100),
            (255, 100, 0), (200, 100, 255), (255, 255, 255),
        ]
        if self._confetti_pool:
            particle = self._confetti_pool.pop()
            particle.x = random.uniform(0, SCREEN_WIDTH)
            particle.y = random.uniform(-50, -10)
            particle.vx = random.uniform(-30, 30)
            particle.vy = random.uniform(100, 250)
            particle.size = random.uniform(4, 10)
            particle.color = random.choice(colors)
            particle.rotation = random.uniform(0, 360)
            particle.rotation_speed = random.uniform(-300, 300)
            particle.lifetime = random.uniform(3.0, 6.0)
        else:
            particle = ConfettiParticle(
                x=random.uniform(0, SCREEN_WIDTH),
                y=random.uniform(-50, -10),
                vx=random.uniform(-30, 30),
                vy=random.uniform(100, 250),
                size=random.uniform(4, 10),
                color=random.choice(colors),
                rotation=random.uniform(0, 360),
                rotation_speed=random.uniform(-300, 300),
                lifetime=random.uniform(3.0, 6.0)
            )
        self.confetti_particles.append(particle)
    
    def _update_confetti(self, dt: float) -> None:
        """Update confetti particles physics."""
        from .config import SCREEN_HEIGHT
        
        alive = []
        for p in self.confetti_particles:
            # Update position
            p.x += p.vx * dt
            p.y += p.vy * dt
            
            # Add slight horizontal wobble
            p.vx += random.uniform(-50, 50) * dt
            p.vx *= 0.98  # Damping
            
            # Gravity effect
            p.vy += 50 * dt  # Accelerate downward
            
            # Rotation
            p.rotation += p.rotation_speed * dt
            
            # Lifetime
            p.lifetime -= dt
            
            if p.lifetime > 0 and p.y < SCREEN_HEIGHT + 50:
                alive.append(p)
            else:
                self._confetti_pool.append(p)
        self.confetti_particles = alive
    
    def _render_victory_sequence(self) -> None:
        """Render the epic victory sequence overlay."""
        if not self.victory_sequence_active:
            return
        
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT, COUNTRY_ABBREV
        
        # 1. RENDER CONFETTI
        self._render_confetti()
        
        # 2. DESATURATE / FADE NON-WINNERS (visual focus on winner)
        if self.physics_world.winner:
            winner = self.physics_world.winner
            for country, racer in self.physics_world.racers.items():
                if country != winner:
                    # Draw dark overlay on non-winners
                    x = int(racer.body.position.x)
                    y = int(racer.body.position.y)
                    fade_alpha = min(180, int(self.victory_sequence_time * 100))
                    
                    overlay_size = 40
                    overlay = pygame.Surface((overlay_size, overlay_size), pygame.SRCALPHA)
                    overlay.fill((0, 0, 0, fade_alpha))
                    self.render_surface.blit(
                        overlay,
                        (x - overlay_size // 2, y - overlay_size // 2)
                    )
        
        # 3. VICTORY BANNER
        self._render_victory_banner()
        
        # 4. MONETIZATION MESSAGE (GIFT mode only)
        if self.victory_was_gift_mode and self.victory_sequence_time > 1.5:
            self._render_monetization_message()
    
    def _render_confetti(self) -> None:
        """Render all confetti particles with rotation."""
        for p in self.confetti_particles:
            # Calculate alpha based on lifetime
            alpha = min(255, int(255 * (p.lifetime / 3.0)))
            
            # Create rotated square
            size = int(p.size)
            if size < 1:
                continue
            
            # Create square surface
            square = pygame.Surface((size, size), pygame.SRCALPHA)
            square.fill((*p.color, alpha))
            
            # Rotate
            rotated = pygame.transform.rotate(square, p.rotation)
            
            # Get rect for proper positioning
            rect = rotated.get_rect(center=(int(p.x), int(p.y)))
            
            self.render_surface.blit(rotated, rect)
    
    def _render_victory_banner(self) -> None:
        """Render the main victory banner with winner name."""
        if not self.physics_world.winner:
            return
        
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT, COUNTRY_ABBREV
        
        winner = self.physics_world.winner
        abbrev = COUNTRY_ABBREV.get(winner, winner[:3].upper())
        
        # Banner dimensions
        banner_height = 120
        banner_y = SCREEN_HEIGHT // 3 - 60
        
        # Create banner surface
        banner = pygame.Surface((SCREEN_WIDTH, banner_height), pygame.SRCALPHA)
        
        # Semi-transparent dark background
        bg_alpha = min(200, int(self.victory_sequence_time * 300))
        banner.fill((0, 0, 0, bg_alpha))
        
        # Winner text with golden glow
        title_font = _get_font("Arial", 42, bold=True)
        subtitle_font = _get_font("Arial", 20, bold=True)

        # Pulsing gold color
        pulse = 0.5 + 0.5 * math.sin(self.victory_sequence_time * 6.0)
        gold_color = (255, int(200 + 55 * pulse), int(50 * pulse))

        # Main winner text
        winner_text = f"{abbrev} WINS!"

        # Apply scale from entrance animation
        scaled_size = int(42 * self.victory_banner_scale)
        if scaled_size > 8:
            title_font = _get_font("Arial", scaled_size, bold=True)
        
        title_surf = self._render_text_enhanced(
            winner_text,
            title_font,
            gold_color,
            outline_color=(0, 0, 0),
            outline_width=4
        )
        
        title_rect = title_surf.get_rect(center=(SCREEN_WIDTH // 2, 40))
        banner.blit(title_surf, title_rect)
        
        # Captain name (if exists)
        captain = self.victory_winner_captain
        if captain and captain != "Unknown":
            # Check if this is a "king" (gift mode captain)
            if self.victory_was_gift_mode:
                captain_text = f"KING OF THE TRACK: @{captain}"
                captain_color = (255, 215, 0)  # Gold
            else:
                captain_text = f"Top Voter: @{captain}"
                captain_color = (200, 200, 255)  # Light blue
            
            captain_surf = self._render_text_with_shadow(
                captain_text,
                subtitle_font,
                captain_color,
                shadow_offset=2
            )
            captain_rect = captain_surf.get_rect(center=(SCREEN_WIDTH // 2, 85))
            banner.blit(captain_surf, captain_rect)
        
        # Blit banner to main surface
        self.render_surface.blit(banner, (0, banner_y))
    
    def _render_monetization_message(self) -> None:
        """Render the call-to-action for gifts (GIFT mode only)."""


    def _reset_victory_sequence(self) -> None:
        """Reset all victory sequence state."""
        self.victory_sequence_active = False
        self.victory_sequence_time = 0.0
        self.victory_zoom_level = 1.0
        self.victory_zoom_target = 1.0
        self.victory_zoom_center = (0.0, 0.0)
        self.slow_motion_active = False
        self.confetti_particles.clear()
        self.victory_banner_scale = 0.0
        self.victory_winner_captain = None
        self.victory_was_gift_mode = False
    
    async def _sync_and_update_ranking(
        self,
        country: str,
        winner_name: str,
        total_diamonds: int,
        streamer_name: str
    ) -> None:
        """
        Sync race result to cloud and then update global ranking.
        This ensures ranking is refreshed after each successful sync.
        """
        # First, sync the race result
        result = await self.cloud_manager.sync_race_result(
            country=country,
            winner_name=winner_name,
            total_diamonds=total_diamonds,
            streamer_name=streamer_name
        )
        
        # If sync was successful, update the ranking
        if result:
            logger.info(f"☁️ Sync successful, updating ranking...")
            await self._fetch_global_ranking()
    
    async def _fetch_global_ranking(self) -> None:
        """
        Fetch global ranking from Supabase (non-blocking).
        Updates self.global_rank_data with Top 3 countries.
        """
        if self.global_rank_loading:
            return  # Already fetching
        
        self.global_rank_loading = True
        
        try:
            ranking, daily = await asyncio.wait_for(
                asyncio.gather(
                    self.cloud_manager.get_global_ranking(limit=5),
                    self.cloud_manager.get_daily_ranking(limit=5),
                    return_exceptions=True,
                ),
                timeout=10.0,
            )

            if isinstance(ranking, list) and ranking:
                self.global_rank_data = ranking
                self.global_rank_last_update = time.time()
                logger.info(f"🏆 Global ranking updated: {len(ranking)} countries")
            else:
                logger.warning("🏆 No global ranking data returned from Supabase")

            if isinstance(daily, list) and daily:
                self.daily_rank_data = daily
                logger.info(f"📅 Daily ranking updated: {len(daily)} countries")
            else:
                logger.warning("📅 No daily ranking data returned from Supabase")

        except asyncio.TimeoutError:
            logger.error("❌ Ranking fetch timed out after 10s (Supabase unreachable?)")
        except Exception as e:
            logger.error(f"❌ Failed to fetch global ranking: {e}")

        finally:
            self.global_rank_loading = False
    
    def _trigger_ranking_update(self) -> None:
        """
        Trigger an async update of the global ranking.
        Call this after successful race sync.
        """
        if not self.global_rank_loading:
            asyncio.create_task(self._fetch_global_ranking())
    
    def _log_performance_metrics(self) -> None:
        """
        Log performance metrics every 10 seconds.
        Includes: FPS average, entity count, memory usage.
        """
        if not self._fps_samples:
            return
        
        # Calculate average FPS from samples
        avg_fps = sum(self._fps_samples) / len(self._fps_samples)
        
        # Count entities
        entity_count = (
            len(self.particles) +
            len(self.floating_texts) +
            len(self.combo_flashes) +
            sum(len(trails) for trails in self.motion_trails.values()) +
            len(self.confetti_particles) +
            (len(self.physics_world.racers) if self.physics_world else 0)
        )
        
        # Get memory usage
        memory_mb = 0.0
        if PSUTIL_AVAILABLE:
            try:
                process = psutil.Process(os.getpid())
                memory_mb = process.memory_info().rss / (1024 * 1024)  # Convert to MB
            except Exception:
                pass
        
        # Log performance metrics
        if memory_mb > 0:
            logger.info(f"[PERF] FPS Promedio: {avg_fps:.1f} | Entidades: {entity_count} | Uso de Memoria: {memory_mb:.1f} MB")
        else:
            logger.info(f"[PERF] FPS Promedio: {avg_fps:.1f} | Entidades: {entity_count} | Uso de Memoria: N/A")
    
    def _get_user_country_with_autojoin(self, username: str, gift_name: str) -> tuple[str, str]:
        """
        Get user's country with auto-join logic for gifts.
        
        Priority:
        1. Check if user is explicitly assigned via keyword binding
        2. Auto-assign based on gift type if user not assigned
        3. Fall back to original assignment logic
        """
        # Check explicit assignment first
        if username in self.user_assignments:
            return self.user_assignments[username], "keyword_assigned"
        
        # Auto-join logic based on gift type
        gift_country_hints = {
            # Mapear ciertos regalos a países si quieres
            # "Tango": "Argentina",
            # "Samba": "Brasil",
            # etc...
        }
        
        if gift_name in gift_country_hints:
            country = gift_country_hints[gift_name]
            self.user_assignments[username] = country
            logger.info(f"🎁 {username} auto-joined {country} via gift {gift_name}")
            
            # Visual feedback
            racer = self.physics_world.racers[country]
            lane_y = self.physics_world.game_area_top + (racer.lane * self.physics_world.lane_height) + (self.physics_world.lane_height // 2)
            
            self.spawn_floating_text(
                f"@{username} joined!",
                100,
                lane_y,
                (255, 215, 0)
            )
            
            return country, "auto_joined_gift"
        
        # No prior vote — assign randomly
        countries = list(self.physics_world.racers.keys())
        country = random.choice(countries)
        self.user_assignments[username] = country
        logger.info(f"🎲 {username} → {country} (random, no prior vote)")
        return country, "random"

    # ------------------------------------------------------------------
    # 🤖 AUTO-PILOT (CHAOS LOOP)
    # ------------------------------------------------------------------

    def start_autopilot(self) -> None:
        """Create the autopilot asyncio task. Call once the event loop is running."""
        self._autopilot_task = asyncio.create_task(
            self._autopilot_loop(), name="autopilot_chaos"
        )
        logger.info("[AutoPilot] Chaos loop task started")

    async def _autopilot_loop(self) -> None:
        """
        Background task: monitors inactivity and fires chaos actions.
        Uses only await asyncio.sleep() — shares the event loop, zero race conditions.
        Never writes to DB or injects queue events.
        """
        from .config import (
            AUTOPILOT_IDLE_THRESHOLD, AUTOPILOT_INTERVAL_MU, AUTOPILOT_INTERVAL_SIGMA,
            AUTOPILOT_MIN_INTERVAL, AUTOPILOT_MAX_INTERVAL, AUTOPILOT_NEW_RACE_DELAY,
        )
        logger.info("[AutoPilot] Loop running — waiting for idle window")

        while True:
            try:
                await asyncio.sleep(1.0)  # 1-second poll (cheap)

                if not self._autopilot_enabled:
                    continue

                now = time.time()

                # Respect post-real-activity cooldown
                if now < self._autopilot_resume_after:
                    continue

                # Check inactivity threshold
                if now - self.last_activity_time < AUTOPILOT_IDLE_THRESHOLD:
                    continue

                # Activate
                if not self._autopilot_active:
                    self._autopilot_active = True
                    logger.info("[AutoPilot] ACTIVATED after %.0fs of inactivity",
                                now - self.last_activity_time)
                    self.spawn_floating_text("AUTO PILOT", 0, 0, (0, 200, 255))

                # Ensure RACING state
                if self.game_state == 'IDLE':
                    self._transition_to_racing()

                # Wait out victory/reset cycle
                if self.physics_world.race_finished:
                    await asyncio.sleep(AUTOPILOT_NEW_RACE_DELAY)
                    continue

                # Fire one chaos action
                await self._execute_chaos_action()

                # Gaussian sleep until next action
                raw = random.gauss(AUTOPILOT_INTERVAL_MU, AUTOPILOT_INTERVAL_SIGMA)
                interval = max(AUTOPILOT_MIN_INTERVAL, min(AUTOPILOT_MAX_INTERVAL, raw))

                # Sliced sleep: check preemption every 250 ms
                elapsed = 0.0
                while elapsed < interval:
                    await asyncio.sleep(0.25)
                    elapsed += 0.25
                    if not self._autopilot_active:
                        break

            except asyncio.CancelledError:
                self._autopilot_active = False
                logger.info("[AutoPilot] Task cancelled")
                raise
            except Exception as exc:
                logger.exception("[AutoPilot] Error in chaos loop: %s", exc)
                await asyncio.sleep(5.0)  # brief back-off before retry

    async def _execute_chaos_action(self) -> None:
        """Select and run one chaos action from a weighted pool, avoiding recent repeats."""
        if not self._autopilot_active or self.physics_world.race_finished:
            return

        if MOTOGP_MODE:
            POOL = [
                (10, "particles",    self._autopilot_particle_chaos),  # 25 → 10
                (45, "combat",       self._autopilot_combat_event),    # 20 → 45
                (30, "terremoto",    self._autopilot_terremoto),       # 20 → 30
                ( 5, "arcoiris",     self._autopilot_arcoiris),        # 15 → 5
                (10, "tormenta",     self._autopilot_tormenta),
                (10, "destello",     self._autopilot_destello),
                (10, "lunar",        self._autopilot_lunar_event),
            ]
        else:
            POOL = [
                (25, "particles",    self._autopilot_particle_chaos),
                (20, "combat",       self._autopilot_combat_event),
                (20, "terremoto",    self._autopilot_terremoto),
                (15, "arcoiris",     self._autopilot_arcoiris),
                (10, "tormenta",     self._autopilot_tormenta),
                (10, "destello",     self._autopilot_destello),
                (10, "lunar",        self._autopilot_lunar_event),
            ]

        recent = set(self._autopilot_recent_actions)
        available = [(w, n, fn) for w, n, fn in POOL if n not in recent] or POOL

        total = sum(w for w, _, _ in available)
        r = random.uniform(0, total)
        cumulative = 0.0
        chosen_name, chosen_fn = available[-1][1], available[-1][2]
        for w, name, fn in available:
            cumulative += w
            if r <= cumulative:
                chosen_name, chosen_fn = name, fn
                break

        self._autopilot_recent_actions.append(chosen_name)
        logger.debug("[AutoPilot] action: %s", chosen_name)
        try:
            await chosen_fn()
        except Exception as exc:
            logger.exception("[AutoPilot] Error in action '%s': %s", chosen_name, exc)

    async def _autopilot_impulse_burst(self) -> None:
        """Move 2-4 random countries; mix moderate pushes with one large guaranteed push."""
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return
        num = random.randint(2, min(4, len(countries)))
        targets = random.sample(countries, num)
        for country in targets[:-1]:
            if random.random() < 0.30:
                self.physics_world.apply_gift_effect("Pesa", country)
            else:
                d = max(5, min(150, int(abs(random.gauss(30, 25)))))
                self.physics_world.apply_gift_impulse(country, "AutoPilot", d)
        # Final target always gets a big guaranteed push
        big = max(50, min(150, int(abs(random.gauss(80, 20)))))
        self.physics_world.apply_gift_impulse(targets[-1], "AutoPilot", big)

    async def _autopilot_particle_chaos(self) -> None:
        """2-3 particle explosions at random flag positions + screen shake."""
        VIVID = [(255, 80, 0), (0, 220, 255), (255, 0, 200), (80, 255, 60), (255, 220, 0), (180, 0, 255)]
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return
        num = random.randint(2, 3)
        for country in random.sample(countries, min(num, len(countries))):
            racer = self.physics_world.racers[country]
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            count = max(25, min(50, int(random.gauss(35, 8))))
            power = max(1.2, min(2.0, random.gauss(1.5, 0.25)))
            self.emit_explosion(pos=pos, color=random.choice(VIVID), count=count, power=power)
        if num >= 3:
            self.screen_shaker.big_impact_shake()
        else:
            self.screen_shaker.impact_shake()

    async def _autopilot_combat_event(self) -> None:
        """Freeze the current race leader."""
        if self.physics_world.race_finished:
            return
        lb = self.physics_world.get_leaderboard()
        if not lb:
            return
        leader = lb[0][1]
        result = self.physics_world.apply_gift_effect("Helado", leader)
        if result['effect'] == 'freeze':
            self.spawn_floating_text(f"{leader} CONGELADO!", 0, 0, (130, 220, 255))
        self.screen_shaker.impact_shake()

    # ─── HYPE TIMER ────────────────────────────────────────────────────────────

    def _update_hype_timer(self) -> None:
        """Update Hype Timer state each frame — prints host cue and fires disaster."""
        elapsed = time.time() - self._hype_timer_start
        remaining = HYPE_TIMER_INTERVAL - elapsed

        # 30s host cue (once per cycle)
        if remaining <= HYPE_TIMER_HOST_CUE_SECS and not self._hype_cue_printed:
            self._hype_cue_printed = True
            print(f"\n{'='*50}")
            print(f"  ⚡ HYPE CUE: DISASTER IN {int(remaining)}s — START HYPING! ⚡")
            print(f"{'='*50}\n")

        # Zero — trigger disaster once
        if remaining <= 0 and not self._hype_timer_fired:
            self._hype_timer_fired = True
            asyncio.create_task(self._trigger_hype_disaster())

        # Reset for next cycle (1s grace lets task start cleanly)
        if remaining <= -1.0:
            self._hype_timer_start = time.time()
            self._hype_timer_fired = False
            self._hype_cue_printed = False

    async def _trigger_hype_disaster(self) -> None:
        """Periodic guaranteed disaster — bigger than any autopilot action."""
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return

        COLORS = [(255, 50, 50), (255, 200, 0), (255, 100, 255), (0, 200, 255)]

        # Trigger full-screen crimson flash + title card
        self._disaster_flash_alpha = 220.0
        self._disaster_flash_time = 0.0
        self._disaster_title_timer = 2.5

        # 1. Massive screen shake
        self.screen_shaker.shake(intensity=35, duration=2.0, decay=True)

        # 2. All racers explode simultaneously
        for country in countries:
            racer = self.physics_world.racers[country]
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            self.emit_explosion(pos=pos, color=random.choice(COLORS), count=25, power=2.5)

        # 3. Warp + Tension background for 8s
        if self.background_manager:
            self.background_manager.activate_warp_mode()
            self.background_manager.activate_tension_mode()

        # 4. "CAOS TOTAL" floating text
        self.spawn_floating_text("SAMBA", 0, 0, (50, 220, 80))

        await asyncio.sleep(8.0)
        if self.background_manager:
            self.background_manager.deactivate_warp_mode()
            self.background_manager.deactivate_tension_mode()

        # 5. Boost last-2 countries after 1s (stimulate laggards, no setbacks)
        await asyncio.sleep(1.0)
        lb = self.physics_world.get_leaderboard()
        for _, last_country, *_ in lb[-2:]:
            if not self.physics_world.race_finished:
                self.physics_world.apply_gift_impulse(last_country, "SAMBA", 30)
                self.screen_shaker.impact_shake()
                await asyncio.sleep(0.3)

        # 6. Second explosion wave
        await asyncio.sleep(1.5)
        sample = random.sample(countries, min(4, len(countries)))
        for country in sample:
            racer = self.physics_world.racers.get(country)
            if racer:
                pos = (float(racer.body.position.x), float(racer.body.position.y))
                self.emit_explosion(pos=pos, color=(255, 255, 100), count=20, power=1.8)
        self.screen_shaker.shake(intensity=20, duration=0.8, decay=True)

    async def _autopilot_terremoto(self) -> None:
        """Global earthquake: all flags explode simultaneously, 2 random countries get setback."""
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return
        self.screen_shaker.meteor_shake()
        VIVID = [(255, 80, 0), (0, 220, 255), (255, 0, 200), (80, 255, 60), (255, 220, 0)]
        for country in countries:
            racer = self.physics_world.racers[country]
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            self.emit_explosion(pos=pos, color=random.choice(VIVID), count=30, power=1.8)
        self.spawn_floating_text("¡TERREMOTO!", 0, 0, (255, 200, 0))

    async def _autopilot_arcoiris(self) -> None:
        """Rainbow cascade: sequential explosions on each racer in leaderboard order."""
        lb = self.physics_world.get_leaderboard()
        if not lb:
            return
        RAINBOW = [
            (255, 0, 0), (255, 127, 0), (255, 215, 0),
            (0, 200, 60), (0, 180, 255), (100, 0, 255), (255, 0, 200),
        ]
        for i, (_, country, *_rest) in enumerate(lb):
            racer = self.physics_world.racers.get(country)
            if racer is None:
                continue
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            self.emit_explosion(pos=pos, color=RAINBOW[i % len(RAINBOW)], count=28, power=1.6)
            await asyncio.sleep(0.06)
        self.screen_shaker.big_impact_shake()
        self.spawn_floating_text("¡ARCOÍRIS!", 0, 0, (255, 80, 220))

    async def _autopilot_tormenta(self) -> None:
        """Activate warp + tension background modes for 6 seconds."""
        self.background_manager.activate_warp_mode()
        self.background_manager.activate_tension_mode()
        self.screen_shaker.meteor_shake()
        self.spawn_floating_text("¡TORMENTA!", 0, 0, (0, 200, 255))
        await asyncio.sleep(6.0)
        self.background_manager.deactivate_warp_mode()
        self.background_manager.deactivate_tension_mode()

    async def _autopilot_destello(self) -> None:
        """Stroboscopic flashes on 5 random racers in quick succession."""
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return
        FLASH = [
            (255, 255, 255), (200, 220, 255), (180, 180, 255),
            (220, 255, 220), (255, 220, 200),
        ]
        targets = random.choices(countries, k=5)
        for country in targets:
            racer = self.physics_world.racers.get(country)
            if racer is None:
                continue
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            self.emit_explosion(pos=pos, color=random.choice(FLASH), count=20, power=1.4)
            self.screen_shaker.impact_shake()
            await asyncio.sleep(0.10)
        self.spawn_floating_text("¡DESTELLO!", 0, 0, (220, 220, 255))

    async def _autopilot_lunar_event(self) -> None:
        """Activate Lunar Gravity with randomized duration/amplitude."""
        if self._lunar_active:
            return
        duration  = max(8.0,  min(20.0, random.gauss(14.0, 3.0)))
        amplitude = max(6.0,  min(12.0, random.gauss(9.0,  1.5)))
        self._activate_lunar_gravity(duration=duration, amplitude=amplitude)

    async def _autopilot_on_fire_event(self) -> None:
        """Trigger neon ON FIRE trails on a random country."""
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return
        country = random.choice(countries)
        self._trigger_on_fire(country)
        self.spawn_floating_text(f"{country.upper()} ON FIRE!", 0, 0, (255, 120, 0))