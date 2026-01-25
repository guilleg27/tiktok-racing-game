"""Game Engine - Consumer that renders TikTok events using Pygame + Pymunk."""

import asyncio
import logging
from typing import Optional
import math
import random
import time
from .cloud_manager import CloudManager
from dataclasses import dataclass

import pygame
import pymunk

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
    # Floating Text (NEW)
    COLOR_TEXT_POSITIVE,
    COLOR_TEXT_NEGATIVE,
    COLOR_TEXT_FREEZE,
    FLOATING_TEXT_SPEED,
    FLOATING_TEXT_LIFESPAN,
    FLOATING_TEXT_FONT_SIZE,
)
from .events import EventType, ConnectionState, GameEvent
from .physics_world import PhysicsWorld
from .database import Database
from .asset_manager import AssetManager, AudioManager
from .camera import ScreenShaker
from .background_manager import BackgroundManager

logger = logging.getLogger(__name__)


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
        
        # 🎯 ELASTIC PULSE: Scale up then down in first 10 frames
        life_progress = 1.0 - (self.lifespan / self.max_lifespan) if self.max_lifespan > 0 else 1.0
        
        if life_progress < 0.15:  # First 15% of life
            # Elastic overshoot: grows to 1.3x then settles to 1.0x
            t = life_progress / 0.15  # Normalize to 0-1
            # Elastic formula: overshoot then bounce back
            scale = 1.0 + 0.4 * math.sin(t * math.pi) * (1 - t * 0.5)
        else:
            scale = 1.0
        
        # Calculate actual font size with pulse
        actual_font_size = max(8, int(self.font_size * scale))
        
        # Create font con BOLD para mejor legibilidad
        try:
            font = pygame.font.SysFont("Arial", actual_font_size, bold=True)
        except:
            font = pygame.font.Font(None, actual_font_size)
    
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
            "🇻🇪": "Venezuela",
            "🇺🇸": "USA",
            "🇮🇩": "Indonesia",
            "🇷🇺": "Russia",
            "🇮🇹": "Italy"
        }
        
        # Asset Manager
        self.asset_manager = AssetManager()
        
        # Audio Manager
        self.audio_manager = AudioManager()
        
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
        
        self.header_height = 30          # era 70, ahora 70 * 0.42 ≈ 30
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
        
        # 🏆 Global Ranking Panel
        self.global_rank_data: list[dict] = []  # Top 3 countries by wins
        self.global_rank_last_update = 0.0  # Timestamp of last update
        self.global_rank_loading = False  # Flag to prevent multiple fetches
        
        # 3D Visualization animation state
        self.ranking_3d_animation_time = 0.0  # For animated effects
        
        # Victory flash effect (white screen flash on win)
        self.victory_flash_alpha = 0.0  # 0.0 = no flash, 255.0 = full white
        self.victory_flash_duration = 0.3  # Seconds to fade out
        self.victory_flash_time = 0.0  # Time elapsed since flash started
        
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
        
        # 🔥 COMBO SYSTEM
        self.combo_tracker: dict[str, list[float]] = {}  # {country: [timestamps]}
        self.combo_counts: dict[str, int] = {}  # {country: current_combo_count}
        self.combo_window = 3.0  # seconds to count as combo
        self.combo_threshold = 5  # minimum for "COMBO!" display
        self.on_fire_threshold = 10  # threshold for "ON FIRE" state
        self.on_fire_countries: set[str] = set()  # countries currently on fire
        
        # 🌈 MOTION TRAILS (replaces fire_particles for crisp neon effect)
        self.motion_trails: dict[str, list[MotionTrailSegment]] = {}  # {country: [segments]}
        self.motion_trail_history: dict[str, list[tuple[float, float]]] = {}  # Position history
        self.max_trail_segments = 20  # Max segments per country
        self.trail_segment_lifetime = 0.3  # Seconds before fade
        
        # ✨ COMBO FLASHES (flash effect on combo level up)
        self.combo_flashes: list[ComboFlash] = []
        
        # 🏁 FINAL STRETCH system
        self.final_stretch_triggered = False
        self.final_stretch_threshold = 0.80  # 80% of track
        self.final_stretch_time = 0.0  # animation timer
        self.original_parallax_speed = 50.0  # store original speed
    
    def init_pygame(self) -> None:
        """Initialize Pygame with centered window and gradient background."""
        import os
        
        try:
            logger.info("🔧 Starting pygame init...")
            
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
            
            pygame.display.set_caption("TikTokGameWindow")
            logger.info("🔧 Caption set")
            
            # Use fixed window size
            self.screen = pygame.display.set_mode((ACTUAL_WIDTH, ACTUAL_HEIGHT))
            logger.info("🔧 Display mode set")
            
            # Render to inner game surface, then blit with margin
            self.render_surface = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
            self.display_scale = 1.0
            self.clock = pygame.time.Clock()
            logger.info("🔧 Clock created")
            
            # Try to load better fonts with fallback chain
            font_names = ["Verdana", "Arial Black", "Arial"]
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
        """Render flag emojis as sprites for countries without PNG sprites."""
        import platform
        
        emoji_map = {
            "Argentina": "🇦🇷", "Brasil": "🇧🇷", "Mexico": "🇲🇽",
            "España": "🇪🇸", "Colombia": "🇨🇴", "Chile": "🇨🇱",
            "Peru": "🇵🇪", "Venezuela": "🇻🇪", "Uruguay": "🇺🇾",
            "Ecuador": "🇪🇨"
        }
        
        # Fuente de emojis según el sistema operativo
        if platform.system() == "Darwin":  # macOS
            emoji_font_name = "Apple Color Emoji"
        elif platform.system() == "Windows":
            emoji_font_name = "Segoe UI Emoji"
        else:  # Linux
            emoji_font_name = "Noto Color Emoji"
        
        for country, racer in self.physics_world.racers.items():
            # Skip if already has sprite
            if racer.sprite is not None:
                continue
            
            # Try to render emoji
            if country in emoji_map:
                try:
                    font = pygame.font.SysFont(emoji_font_name, 40)
                    surf = font.render(emoji_map[country], True, (255, 255, 255))
                    racer.sprite = surf
                    logger.info(f"🚩 Rendered emoji for {country}")
                except Exception as e:
                    logger.warning(f"Could not render emoji {emoji_map[country]}: {e}")
    
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
        Render trail particles behind flags.
        Creates smooth color trails showing flag movement.
        """
        for country, trail_particles in self.particle_manager.trail_particles.items():
            for particle in trail_particles:
                if particle.alpha <= 0 or particle.size <= 0:
                    continue
                
                # Create surface for trail particle with alpha
                size = max(int(particle.size * 2), 2)
                trail_surf = pygame.Surface((size, size), pygame.SRCALPHA)
                
                # Draw particle with alpha
                color_with_alpha = (*particle.color, particle.alpha)
                pygame.draw.circle(
                    trail_surf,
                    color_with_alpha,
                    (size // 2, size // 2),
                    max(int(particle.size), 1)
                )
                
                # Blit to render surface
                blit_x = int(particle.pos[0] - size // 2)
                blit_y = int(particle.pos[1] - size // 2)
                self.render_surface.blit(trail_surf, (blit_x, blit_y))
    
    def _render_particles(self) -> None:
        """
        Render particles with optimized direct circle drawing.
        Uses pygame.draw.circle directly on surface for maximum speed.
        """
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
            
            # Create color with alpha
            color_with_alpha = (*particle.color, opacity)
            
            # Optimized: Direct circle draw with alpha
            # Create minimal surface for particle
            size = radius * 2
            particle_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(particle_surf, color_with_alpha, (radius, radius), radius)
            
            # Blit to render surface (safe conversions)
            blit_x = self._safe_int(particle.pos.x - radius, 0)
            blit_y = self._safe_int(particle.pos.y - radius, 0)
            self.render_surface.blit(particle_surf, (blit_x, blit_y))
    
    def _render_floating_texts(self) -> None:
        """Render all floating texts for visual feedback."""
        for text in self.floating_texts:
            text.draw(self.render_surface)
    
    async def process_events(self) -> None:
        """Process all available events from the queue."""
        while True:
            try:
                event = self.queue.get_nowait()
                await self._handle_event(event)
            except asyncio.QueueEmpty:
                break
    
    async def _handle_event(self, event: GameEvent) -> None:
        """Handle a single event from the queue."""
        if event.type == EventType.QUIT:
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
            # TRANSICIÓN: IDLE -> RACING al primer regalo
            if self.game_state == 'IDLE':
                self._transition_to_racing()
                logger.info("🏁 Game state: RACING (first gift received!)")
        
            gift_count = event.extra.get("count", 1) if event.extra else 1
            diamond_count = event.extra.get("diamond_count", 1) if event.extra else 1
            gift_name = event.content
            username = self.sanitize_username(event.username)
            
            # SMART COUNTRY ASSIGNMENT
            country, assignment_type = self._get_user_country_with_autojoin(username, gift_name)
            
            # 🏆 CAPTAIN SYSTEM: Track points
            self._update_captain_points(username, country, diamond_count)
            
            # 🔥 COMBO SYSTEM: Register this gift (count each gift_count as separate)
            for _ in range(min(gift_count, 5)):  # Cap at 5 to prevent abuse
                self.register_combo_event(country)

            logger.info(f"🎁 REGALO: {username} ({assignment_type}) → {country} | regalo: {gift_name}")
            
            # Apply impulse to country's flag
            success = self.physics_world.apply_gift_impulse(
                country=country,
                gift_name=gift_name,
                diamond_count=diamond_count
            )
            
            if success:
                # Play appropriate sound effect
                self.audio_manager.play_sfx(
                    sound_type='auto',
                    gift_name=gift_name,
                    diamond_count=diamond_count
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
                
                # Emit floating text feedback (respect global limit)
                self.floating_texts.append(
                    FloatingText(
                        text=f"{gift_name} x{gift_count}",
                        x=pos[0],
                        y=pos[1] - 30,
                        color=(255, 255, 255),
                        lifespan=40,
                        max_lifespan=40,
                        font_size=20
                    )
                )
                if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
                    self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]
            
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
                    self.audio_manager.play_freeze_sfx()
                    
                    # 🎥 Trigger screen shake for impact
                    self.screen_shaker.impact_shake()
                    
                    # Spawn floating text on the frozen target
                    target_racer = self.physics_world.racers[target]
                    self.spawn_floating_text(
                        "FREEZE!", 
                        target_racer.body.position.x, 
                        target_racer.body.position.y,
                        COLOR_TEXT_FREEZE
                    )
                    
                    # Emit freeze particles (blue ice effect)
                    self.emit_explosion(
                        pos=(target_racer.body.position.x, target_racer.body.position.y),
                        color=(100, 200, 255),  # Azul hielo
                        count=30,
                        power=1.0,
                        diamond_count=0
                    )
            
            # Handle setback/pesa effect
            elif combat_result['effect'] == 'setback':
                target = combat_result.get('target')
                if target in self.physics_world.racers:
                    # 🎥 Trigger screen shake for attack impact
                    self.screen_shaker.impact_shake()
            
            if self.database:
                await self.database.save_event_to_db(
                    user=username,
                    gift_name=gift_name,
                    diamond_count=diamond_count,
                    gift_count=gift_count,
                    streamer=self.streamer_name
                )
            
            # Message with assignment indicator
            assignment_indicator = {
                "cached": "✓",
                "flag": "🚩",
                "balanced": "⚖️"
            }.get(assignment_type, "")
            
            message = f"{assignment_indicator} {username} → {country}: {gift_name} x{gift_count} ({diamond_count}💎)"
            self.messages.append((message, event.type))
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]
    
        elif event.type == EventType.JOIN:
            await self._handle_join_event(event)
        
        elif event.type == EventType.VOTE:
            await self._handle_vote_event(event)
    
    async def _handle_join_event(self, event: GameEvent) -> None:
        """Handle user joining a team via keyword."""
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
        
        # Update last vote time
        if not hasattr(self, '_last_vote_time'):
            self._last_vote_time = {}
        self._last_vote_time[username] = current_time
        
        # 🎥 Register vote for burst detection (micro-shake on vote bursts)
        self.screen_shaker.register_vote()
        
        # Update user assignment
        self.user_assignments[username] = country
        
        # 🔥 COMBO SYSTEM: Register this vote
        self.register_combo_event(country)
        
        # 🏆 CAPTAIN SYSTEM: Track points
        self._update_captain_points(username, country, COMMENT_POINTS_PER_MESSAGE)
        
        logger.info(f"🗳️ VOTE: {username} → {country} ({shortcut_used})")
        
        # Apply movement to country's flag
        success = self.physics_world.apply_gift_impulse(
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
            
            # Optional: floating text feedback (limited)
            if len(self.floating_texts) < self.MAX_FLOATING_TEXTS // 2:
                self.floating_texts.append(
                    FloatingText(
                        text=f"+{COMMENT_POINTS_PER_MESSAGE}",
                        x=pos[0],
                        y=pos[1] - 20,
                        color=(0, 200, 255),  # Neon blue for votes
                        lifespan=30,
                        max_lifespan=30,
                        font_size=14,
                        dy=-2.5  # Faster jump
                    )
                )
        
        # Add message to feed
        message = event.format_message()
        self.messages.append((message, event.type))
        if len(self.messages) > MAX_MESSAGES:
            self.messages = self.messages[-MAX_MESSAGES:]
    
    def handle_pygame_events(self) -> None:
        """Process Pygame input events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.running = False
                elif event.key == pygame.K_c or event.key == pygame.K_r:
                    self._return_to_idle()  # Usar nuevo método
                    logger.info("Race reset to IDLE!")
                elif event.key == pygame.K_t:  # Test mode
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
                    diamonds = random.randint(1, 10)
                    
                    self.physics_world.apply_gift_impulse(
                        country=country,
                        gift_name="Test Gift",
                        diamond_count=diamonds
                    )
                    
                    logger.info(f"TEST: {country} received {diamonds}💎")
                    
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
                        import time
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
                        import time
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
                        import time
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
                        result = self.physics_world.apply_gift_effect("Helado", country)
                        logger.info(f"TEST HELADO: freezing leader")
                        
                        # Spawn floating text on the frozen target
                        if result['effect'] == 'freeze':
                            target = result['target']
                            if target in self.physics_world.racers:
                                racer = self.physics_world.racers[target]
                                self.spawn_floating_text(
                                    "FREEZE!", 
                                    racer.body.position.x, 
                                    racer.body.position.y,
                                    COLOR_TEXT_FREEZE
                                )
    
                elif event.key == pygame.K_j:  # J = Test JoinEvent
                    # Generate random test join
                    import time
                    
                    # Random username with timestamp to make it unique
                    test_usernames = [
                        "TestUser", "Viewer", "Fan", "Supporter", "Player", 
                        "Streamer", "Watcher", "Usuario", "Espectador"
                    ]
                    base_username = random.choice(test_usernames)
                    unique_username = f"{base_username}{int(time.time() * 1000) % 1000}"
                    
                    # Random country
                    countries = list(self.physics_world.racers.keys())
                    random_country = random.choice(countries)
                    
                    # Random keyword that would trigger this country
                    from .config import COUNTRY_KEYWORDS
                    # Find a keyword for this country
                    matching_keywords = [k for k, v in COUNTRY_KEYWORDS.items() if v == random_country]
                    keyword_used = random.choice(matching_keywords) if matching_keywords else random_country.lower()
                    
                    # Create fake JoinEvent and put it in queue
                    join_event = GameEvent(
                        type=EventType.JOIN,
                        username=unique_username,
                        content=random_country,
                        extra={
                            "keyword": keyword_used,
                            "original_message": f"¡Vamos {keyword_used}!"
                        }
                    )
                    
                    # Add to queue for processing
                    try:
                        self.queue.put_nowait(join_event)
                        logger.info(f"TEST JOIN: {unique_username} → {random_country} (keyword: {keyword_used})")
                    except Exception as e:
                        logger.error(f"Error adding test join to queue: {e}")

                elif event.key == pygame.K_k:  # K = Test Captain Points
                    # Add random points to random user in random country
                    import time
                    
                    countries = list(self.physics_world.racers.keys())
                    test_country = random.choice(countries)
                    
                    test_user = f"User{int(time.time() * 1000) % 100}"
                    test_points = random.randint(50, 500)
                    
                    self._update_captain_points(test_user, test_country, test_points)
                    logger.info(f"TEST CAPTAIN: {test_user} → {test_country} (+{test_points}💎)")
                
                elif event.key == pygame.K_f:  # F = Test FIRE (rapid combo)
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")
                    
                    # Simulate 12 rapid votes to trigger ON FIRE
                    countries = list(self.physics_world.racers.keys())
                    test_country = random.choice(countries)
                    
                    for _ in range(12):
                        self.register_combo_event(test_country)
                        # Also apply movement
                        self.physics_world.apply_gift_impulse(
                            country=test_country,
                            gift_name="ComboTest",
                            diamond_count=1
                        )
                    
                    logger.info(f"🔥 TEST FIRE: {test_country} - triggered ON FIRE state!")
                
                elif event.key == pygame.K_g:  # G = Test Final Stretch
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏁 Game state: RACING (test mode)")
                    
                    # Force trigger final stretch
                    if not self.final_stretch_triggered:
                        self._trigger_final_stretch()
                        logger.info("🏁 TEST: Final Stretch triggered!")
                
                elif event.key == pygame.K_v:  # V = Test Victory Sequence
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self._transition_to_racing()
                        logger.info("🏆 Game state: RACING (test mode)")
                    
                    # Force trigger victory
                    test_countries = list(self.physics_world.racers.keys())
                    if test_countries:
                        winner = random.choice(test_countries)
                        self.physics_world.winner = winner
                        self.physics_world.race_finished = True
                        captain = self.current_captains.get(winner, "TestKing")
                        self._trigger_victory_sequence(winner, captain)
                        logger.info(f"🏆 TEST VICTORY: {winner} wins! Captain: {captain}")

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
        
        racer = self.physics_world.racers[country]
        x = racer.body.position.x
        y = racer.body.position.y
        
        # 👑 GOLDEN CROWN floating text for new captain (larger, longer)
        crown_text = f"👑 {new_captain}"
        self.floating_texts.append(
            FloatingText(
                text=crown_text,
                x=x,
                y=y - 15,
                color=(255, 215, 0),  # Gold
                lifespan=80,
                max_lifespan=80,
                font_size=18,  # Larger for emphasis
                dy=-2.5  # Faster upward movement
            )
        )
        
        # Secondary "NEW CAPTAIN" text with neon effect
        self.floating_texts.append(
            FloatingText(
                text="NEW CAPTAIN!",
                x=x,
                y=y - 35,
                color=(255, 255, 100),  # Bright yellow
                lifespan=60,
                max_lifespan=60,
                font_size=14,
                dy=-2.0
            )
        )
        
        # 🎥 Trigger screen shake for impact
        self.screen_shaker.micro_shake()
        
        # Set timer for captain highlight effect
        self.captain_change_timer[country] = 90  # 1.5 seconds at 60fps

    def update(self, dt: float) -> None:
        """Update physics and particles."""
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

        self.physics_world.update(dt)
        self.update_particles(dt)
        self.update_floating_texts()
        
        # 🌌 Update parallax background
        if self.background_manager:
            self.background_manager.update(dt)
        
        # 🎥 Update screen shaker
        self.screen_shaker.update(dt)
        
        # 🌟 Update leader glow animation
        self.leader_glow_time += dt
        
        # 📜 Update ticker scroll
        self.ticker_offset += self.ticker_speed * dt
        
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
            
            # 🌈 Update motion trails for ON FIRE countries
            self._update_motion_trails(dt)
            
            # Update combo flashes
            self._update_combo_flashes(dt)
            
            # 🏁 Check for final stretch
            self._check_final_stretch()
            
            # Update final stretch animation timer
            if self.final_stretch_triggered:
                self.final_stretch_time += dt
        
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
        
        # FPS monitoring (if stress test enabled)
        if AUTO_STRESS_TEST:
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
    
    def render(self) -> None:
        """Render all visual elements."""
        from .config import GAME_MARGIN
        
        # Draw outer background (window margin)
        self.screen.blit(self.outer_background, (0, 0))
        
        # 🌌 Render parallax background FIRST (behind everything)
        if self.background_manager:
            self.background_manager.render(self.render_surface)
        else:
            # Fallback to static gradient if no background manager
            self.render_surface.blit(self.gradient_background, (0, 0))
        
        self._render_balls()
        self._render_trails()  # Render trails before particles (behind)
        self._render_motion_trails()  # 🌈 Neon motion trails for ON FIRE state
        self._render_particles()
        self._render_floating_texts()
        self._render_combo_flashes()  # ✨ Flash effects on combo level up
        self._render_header()
        self._render_legend()
        self._render_leaderboard()
        
        # 🏁 Render FINAL STRETCH announcement
        self._render_final_stretch_announcement()
        
        # Render shortcuts panel in COMMENT mode (solo durante RACING)
        from .config import GAME_MODE
        import time as time_module
        
        if GAME_MODE == "COMMENT" and self.game_state == 'RACING':
            # Always show ticker at bottom
            self._render_shortcuts_panel()
            
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
        
        # 🎬 Apply subtle camera zoom during victory sequence
        # Note: Instead of cropping (which can cut off content), we scale the whole
        # surface slightly and center it, creating a subtle "push in" effect
        if self.victory_sequence_active and self.victory_zoom_level > 1.01:
            zoom = min(self.victory_zoom_level, 1.15)  # Cap at 15% zoom to avoid cutting too much
            
            # Scale up the surface
            scaled_width = int(SCREEN_WIDTH * zoom)
            scaled_height = int(SCREEN_HEIGHT * zoom)
            
            scaled_surface = pygame.transform.smoothscale(
                self.render_surface, 
                (scaled_width, scaled_height)
            )
            
            # Center the scaled surface (this creates a zoom-in effect)
            offset_x = (scaled_width - SCREEN_WIDTH) // 2
            offset_y = (scaled_height - SCREEN_HEIGHT) // 2
            
            # Blit with offset to center
            self.screen.blit(scaled_surface, (blit_x - offset_x, blit_y - offset_y))
        else:
            self.screen.blit(self.render_surface, (blit_x, blit_y))
        
        pygame.display.flip()
    
    def _render_balls(self) -> None:
        """Render all flag racers with winner spotlight and leader glow."""
        # Draw lanes
        self._render_lanes()
        
        # Draw finish line
        self._render_finish_line()
        
        # Get winner and current leader
        winner = self.physics_world.winner if self.physics_world.race_finished else None
        leader_info = self.physics_world.get_leader()
        current_leader = leader_info[0] if leader_info else None
        
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
        x, y = racer.body.position
        radius = racer.shape.radius
        angle = racer.body.angle
        
        # Sanitize position values
        x = float(x) if math.isfinite(x) else self.physics_world.start_x
        y = float(y) if math.isfinite(y) else (racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2)
        radius = float(radius) if math.isfinite(radius) else 30
        
        # 🔥 ON FIRE jitter effect
        if racer.country in self.on_fire_countries:
            jitter_x = random.uniform(-2, 2)
            jitter_y = random.uniform(-2, 2)
            x += jitter_x
            y += jitter_y
        
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
        
        # Draw country abbreviation (ARG, BRA, MEX, etc.) to the left of the flag
        ix = self._safe_int(x, self.physics_world.start_x)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        
        # Get country abbreviation
        country_abbrev = self._get_country_abbrev(racer.country)
        
        # Position abbreviation to the left of the flag
        abbrev_x = ix - radius - 25  # 25px to the left of flag edge
        abbrev_y = iy
        
        # Render abbreviation with enhanced text
        abbrev_font = pygame.font.SysFont("Arial", 11, bold=True)
        abbrev_surface = self._render_text_enhanced(
            country_abbrev,
            abbrev_font,
            (255, 255, 255),
            outline_color=(0, 0, 0),
            outline_width=1
        )
        abbrev_rect = abbrev_surface.get_rect(center=(abbrev_x, abbrev_y))
        self.render_surface.blit(abbrev_surface, abbrev_rect)

        # 👑 CAPTAIN LABEL
        self._render_captain_label(racer, ix, iy)

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
            # Get points for display
            points = self.session_points.get(country, {}).get(captain, 0)
            captain_text = f"@{captain} - ({points})"
            
            # Special highlight if just became captain
            if country in self.captain_change_timer:
                color = (255, 255, 0)  # Bright yellow for new captain
                font_size = 15
            else:
                # Improved legibility: light gray/off-white for better contrast
                color = (204, 204, 204)  # #CCCCCC - Light gray for better readability
                font_size = 12
            
            # Render with enhanced text (outline) - 1px outline for better legibility
            try:
                captain_font = pygame.font.SysFont("Arial", font_size, bold=True)
                captain_surface = self._render_text_enhanced(
                    captain_text,
                    captain_font,
                    color,
                    outline_color=(0, 0, 0),
                    outline_width=1  # 1px outline as requested
                )
                
                captain_rect = captain_surface.get_rect(center=(flag_x, label_y))
                self.render_surface.blit(captain_surface, captain_rect)
                
            except Exception as e:
                logger.debug(f"Error rendering captain label: {e}")
        else:
            # No captain yet - optional "No Captain" text
            if self.game_state == 'RACING':  # Only show during active race
                try:
                    no_captain_font = pygame.font.SysFont("Arial", 9, bold=True)
                    # Improved legibility: brighter color and better position
                    no_captain_surface = self._render_text_enhanced(
                        "No Captain",
                        no_captain_font,
                        (220, 220, 220),  # Brighter gray for better visibility
                        outline_color=(0, 0, 0),
                        outline_width=2  # Thicker outline for better visibility
                    )
                    
                    # Position to the right of the flag, aligned with captain text position
                    no_captain_x = flag_x + 30  # To the right of flag
                    no_captain_rect = no_captain_surface.get_rect(center=(no_captain_x, label_y))
                    self.render_surface.blit(no_captain_surface, no_captain_rect)
                    
                except Exception:
                    pass  # Skip if font fails

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

    def _render_header(self) -> None:
        """Render header with leader info and drop shadow for visibility."""
        header_surface = pygame.Surface((SCREEN_WIDTH, self.header_height), pygame.SRCALPHA)
        header_surface.fill((20, 20, 20, 200))  # Slightly more transparent
        self.render_surface.blit(header_surface, (0, 0))
        
        # Leader info (centrado en el header)
        leader_info = self.physics_world.get_leader()
        leader_text = f"🏆 1st: {leader_info[0]}" if leader_info else "🏆 1st: ---"
        
        # 🎯 EFECTO POP cuando cambia el líder
        if self.leader_pop_timer > 0:
            # Escala 1.1x durante el pop
            pop_scale = 1.1
            pop_font = pygame.font.SysFont("Arial", int(FONT_SIZE * pop_scale), bold=True)
            count_surface = self._render_text_with_shadow(
                leader_text, pop_font, (255, 255, 0), shadow_offset=2
            )
        else:
            count_surface = self._render_text_with_shadow(
                leader_text, self.font, (255, 255, 255), shadow_offset=2
            )
        
        # Centrar el texto en el header
        text_rect = count_surface.get_rect()
        text_rect.right = SCREEN_WIDTH - 10
        text_rect.centery = self.header_height // 2
        self.render_surface.blit(count_surface, text_rect)
    
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
    
    def _render_lanes(self) -> None:
        """Draw subtle lane separators."""
        from .config import COLOR_LANE_LINE
        
        lane_height = self.physics_world.lane_height
        game_area_top = self.physics_world.game_area_top
        
        # Create surface with alpha for subtle lines
        lane_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        
        for i in range(1, self.physics_world.num_lanes):
            y = game_area_top + (i * lane_height)
            pygame.draw.line(lane_surf, COLOR_LANE_LINE, (0, y), (SCREEN_WIDTH, y), 1)
        
        self.render_surface.blit(lane_surf, (0, 0))
    
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
        
        raw_radius = winner_racer.shape.radius * self.winner_scale_pulse
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

        # Radial light rays
        num_rays = 8
        ray_length = 80
        for i in range(num_rays):
            angle = (self.winner_animation_time * 2.0 + i * (2 * math.pi / num_rays))
            start_x = x + math.cos(angle) * radius
            start_y = y + math.sin(angle) * radius
            end_x = x + math.cos(angle) * (radius + ray_length)
            end_y = y + math.sin(angle) * (radius + ray_length)
            ray_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
            alpha = max(0, self.winner_glow_alpha - 80)
            pygame.draw.line(
                ray_surf, 
                (255, 223, 0, alpha), 
                (self._safe_int(start_x), self._safe_int(start_y)), 
                (self._safe_int(end_x), self._safe_int(end_y)), 
                3
            )
            self.render_surface.blit(ray_surf, (0, 0))

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

    def _render_leaderboard(self) -> None:
        """Render leaderboard overlay when race finished."""
        if not self.physics_world.race_finished:
            return

        # Render 3D ranking visualization behind the final classification
        # Uses global Supabase ranking to create futuristic tracks
        if self.global_rank_data:
            self._render_3d_ranking_visualization()

        # Dim background behind the final classification panel
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 140))
        self.render_surface.blit(overlay, (0, 0))

        leaderboard = self.physics_world.get_leaderboard()
        # Limit to first 10 entries only
        leaderboard = leaderboard[:10]
        
        # Reduced table width and added side margins
        side_margin = 20  # Margin on each side of screen
        left_margin = 15  # Additional left margin for text visibility
        table_w, table_h = SCREEN_WIDTH - (side_margin * 2), 420  # Full width minus margins
        table_x = side_margin  # Start with margin from left
        table_y = SCREEN_HEIGHT - table_h - 60

        # Adjusted internal margins for better content fit
        bar_margin_left = 90 + left_margin  # Increased left margin for text visibility
        bar_margin_right = 80  # Increased from 20 to prevent cutoff
        bar_h = 10
        bar_w = table_w - bar_margin_left - bar_margin_right
        bar_x = bar_margin_left

        surf = pygame.Surface((table_w, table_h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (5, 5, 10, 255), (0, 0, table_w, table_h), border_radius=10)
        pygame.draw.rect(surf, (255, 215, 0, 180), (0, 0, table_w, table_h), 2, border_radius=10)
        
        header_font = pygame.font.SysFont("Arial", 18, bold=True)
        hdr = header_font.render("FINAL CLASSIFICATION", True, (255, 215, 0))
        surf.blit(hdr, (15 + left_margin, 10))  # Add left margin to header

        row_font = pygame.font.SysFont("Arial", 14, bold=True)
        start_y = 45
        row_h = 35
        max_distance = max(1, self.physics_world.finish_line_x - self.physics_world.start_x)

        # Medallas como texto (no emojis)
        medal_text = {1: "[1st]", 2: "[2nd]", 3: "[3rd]"}
        medal_colors = {1: (255, 215, 0), 2: (192, 192, 192), 3: (205, 127, 50)}

        for idx, (position, country, distance, medal) in enumerate(leaderboard):
            y = start_y + idx * row_h
            
            # Row background
            if position == 1:
                bg = (50, 40, 20, 140)
            elif position == 2:
                bg = (40, 40, 40, 100)
            elif position == 3:
                bg = (45, 35, 25, 100)
            else:
                bg = (20, 20, 20, 70)
            
            # Add left margin to row background
            pygame.draw.rect(surf, bg, (10 + left_margin, y - 5, table_w - 20 - left_margin, row_h - 4), border_radius=6)

            # Position con medalla de color - with left margin
            position_x = 25 + left_margin
            if position <= 3:
                # Dibujar círculo de medalla
                medal_color = medal_colors[position]
                pygame.draw.circle(surf, medal_color, (position_x, y + 8), 10)
                pygame.draw.circle(surf, (255, 255, 255), (position_x, y + 8), 10, 1)
                pos_s = row_font.render(f"{position}", True, (0, 0, 0))
                surf.blit(pos_s, (position_x - 4, y))
            else:
                pos_s = row_font.render(f"{position}", True, (200, 200, 200))
                surf.blit(pos_s, (position_x - 5, y))
        
            # Country name (sin medal emoji) - with left margin
            country_x = 45 + left_margin
            country_s = row_font.render(country, True, (255, 255, 255))
            # Truncate long country names to fit
            max_country_width = bar_x - country_x - 10  # Space between country name and bar start
            if country_s.get_width() > max_country_width:
                # Truncate country name if too long
                truncated = country[:12] + "..." if len(country) > 12 else country
                country_s = row_font.render(truncated, True, (255, 255, 255))
            surf.blit(country_s, (country_x, y))

            # Distance en diamantes (sin emoji) - positioned with margin
            dist_val = distance if (isinstance(distance, (int, float)) and math.isfinite(distance)) else 0.0
            diamonds_approx = self._safe_int(dist_val / 0.8, 0)
            dist_txt = f"{diamonds_approx}d"
            dist_s = row_font.render(dist_txt, True, (255, 215, 100))
            # Position with right margin to prevent cutoff
            dist_x = table_w - bar_margin_right - 5  # 5px padding from bar margin
            surf.blit(dist_s, (dist_x, y))

            # Progress bar
            prog = (dist_val / max_distance) if max_distance > 0 else 0.0
            prog = min(max(prog, 0.0), 1.0)
            filled = self._safe_int(bar_w * prog, 0)
            
            pygame.draw.rect(surf, (50, 50, 50), (bar_x, y + 20, bar_w, bar_h), border_radius=5)
            
            if filled > 0:
                bar_color = medal_colors.get(position, (80, 180, 80))
                pygame.draw.rect(surf, bar_color, (bar_x, y + 20, filled, bar_h), border_radius=5)

        # Overlay
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.render_surface.blit(overlay, (0, 0))

        self.render_surface.blit(surf, (table_x, table_y))

    def _render_legend(self) -> None:
        """Render the combat legend at the bottom of the screen."""
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        legend_height = 60
        legend_y = SCREEN_HEIGHT - legend_height
        padding = 10
        
        # Background MÁS OSCURO para mejor contraste
        legend_surface = pygame.Surface((SCREEN_WIDTH, legend_height), pygame.SRCALPHA)
        legend_surface.fill((0, 0, 0, 240))
        pygame.draw.line(legend_surface, (255, 215, 0, 255), (0, 0), (SCREEN_WIDTH, 0), 3)
        self.render_surface.blit(legend_surface, (0, legend_y))
        
        # Title
        title_font = pygame.font.SysFont("Arial", 15, bold=True)
        title_enhanced = self._render_text_enhanced(
            "COMBAT POWERS",
            title_font,
            (255, 235, 50),
            outline_color=(0, 0, 0),
            outline_width=3
        )
        self.render_surface.blit(title_enhanced, (padding, legend_y + 2))
        
        # Combat items
        items = [
            ("rosa", "+5m", "Rose", (255, 120, 180)),
            ("pesa", "Stops Leader", "Weight", (180, 180, 180)),
            ("hielo", "Freeze 3s", "Ice Cream", (120, 220, 255)),
        ]
        
        item_width = (SCREEN_WIDTH - 2 * padding) // len(items)
        text_font = pygame.font.SysFont("Arial", 12, bold=True)  # Un poco más pequeño
        small_font = pygame.font.SysFont("Arial", 9)
        
        for i, (icon_type, effect, gift_name, color) in enumerate(items):
            x = padding + i * item_width
            y = legend_y + 28  # Bajado un poco más
            
            # Posición del icono (más a la izquierda)
            icon_x = x + 12
            icon_y = y + 5
            
            # Intentar cargar icono PNG
            icon = self.asset_manager.get_combat_icon(icon_type)
            
            if icon:
                # Renderizar PNG centrado
                icon_rect = icon.get_rect(center=(icon_x, icon_y))
                self.render_surface.blit(icon, icon_rect)
            else:
                # Fallback: formas dibujadas
                if icon_type == "rosa":
                    pygame.draw.circle(self.render_surface, color, (icon_x, icon_y), 8)
                    pygame.draw.circle(self.render_surface, (255, 255, 255), (icon_x, icon_y), 8, 2)
                elif icon_type == "pesa":
                    pygame.draw.rect(self.render_surface, color, (icon_x - 7, icon_y - 7, 14, 14))
                    pygame.draw.rect(self.render_surface, (255, 255, 255), (icon_x - 7, icon_y - 7, 14, 14), 2)
                elif icon_type == "hielo":
                    points = [(icon_x, icon_y - 8), (icon_x + 8, icon_y), (icon_x, icon_y + 8), (icon_x - 8, icon_y)]
                    pygame.draw.polygon(self.render_surface, color, points)
                    pygame.draw.polygon(self.render_surface, (255, 255, 255), points, 2)
            
            # Texto del efecto MÁS SEPARADO del icono
            effect_enhanced = self._render_text_enhanced(
                effect,
                text_font,
                (255, 255, 255),  # Blanco puro
                outline_color=(0, 0, 0),
                outline_width=2
            )
            # Aumentar separación: x + 30 (era 24)
            self.render_surface.blit(effect_enhanced, (x + 32, y - 4))
            
            # Nombre del regalo
            name_text = small_font.render(f"({gift_name})", True, (200, 200, 200))
            self.render_surface.blit(name_text, (x + 32, y + 12))
        
        # Frozen indicator
        if self.physics_world.frozen_countries:
            frozen_parts = []
            for c, t in self.physics_world.frozen_countries.items():
                frozen_parts.append(f"{c}: {t:.1f}s")
            frozen_text = " | ".join(frozen_parts)
            
            frozen_font = pygame.font.SysFont("Arial", 11, bold=True)
            frozen_enhanced = self._render_text_enhanced(
                f"FROZEN: {frozen_text}",
                frozen_font,
                (150, 230, 255),
                outline_color=(0, 0, 0),
                outline_width=2
            )
            self.render_surface.blit(frozen_enhanced, (padding, legend_y + 45))
    
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
            success = self.physics_world.apply_gift_impulse(
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
    
    def _get_emoji_font(self, size: int) -> pygame.font.Font:
        """Get a font that supports emoji rendering."""
        try:
            # macOS
            return pygame.font.SysFont("Apple Color Emoji", size)
        except:
            try:
                # Windows
                return pygame.font.SysFont("Segoe UI Emoji", size)
            except:
                # Fallback
                return pygame.font.SysFont("Arial", size)

    def _render_text_with_emoji(
        self, 
        text: str, 
        size: int, 
        color: tuple, 
        bold: bool = False
    ) -> pygame.Surface:
        """
        Render text that may contain emojis.
        Splits text into emoji and non-emoji parts for proper rendering.
        """
        import re
        
        # Simple approach: use emoji font for everything if text contains emoji
        emoji_pattern = re.compile(
            "["
            "\U0001F1E0-\U0001F1FF"  # flags
            "\U0001F300-\U0001F5FF"  # symbols & pictographs
            "\U0001F600-\U0001F64F"  # emoticons
            "\U0001F680-\U0001F6FF"  # transport & map
            "\U0001F700-\U0001F77F"  # alchemical
            "\U0001F780-\U0001F7FF"  # geometric
            "\U0001F800-\U0001F8FF"  # supplemental arrows
            "\U0001F900-\U0001F9FF"  # supplemental symbols
            "\U0001FA00-\U0001FA6F"  # chess symbols
            "\U0001FA70-\U0001FAFF"  # symbols extended
            "\U00002702-\U000027B0"  # dingbats
            "\U0001F004-\U0001F0CF"  # playing cards
            "]+"
        )
        
        has_emoji = emoji_pattern.search(text) is not None
        
        if has_emoji:
            font = self._get_emoji_font(size)
        else:
            font = pygame.font.SysFont("Arial", size, bold=bold)
        
        return font.render(text, True, color)
    
    def spawn_floating_text(
        self, 
        text: str, 
        x: float, 
        y: float, 
        color: tuple[int, int, int]
    ) -> None:
        """Spawn a floating text effect at the given position."""
        from .config import FLOATING_TEXT_SPEED, FLOATING_TEXT_LIFESPAN, FLOATING_TEXT_FONT_SIZE
    
        floating_text = FloatingText(
            text=text,
            x=x,
            y=y,
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
        
        # Central message box - MÁS GRANDE en COMMENT mode para incluir lista
        if GAME_MODE == "COMMENT":
            box_width = 320
            box_height = 420
        else:
            box_width = 380
            box_height = 200
        
        box_x = (SCREEN_WIDTH - box_width) // 2
        box_y = (SCREEN_HEIGHT - box_height) // 2
        
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
        title_font = pygame.font.SysFont("Arial", 22, bold=True)
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
        
        # Aplicar escala de "respiración" a la superficie
        scaled_width = int(title_surface.get_width() * breathe_scale)
        scaled_height = int(title_surface.get_height() * breathe_scale)
        title_surface = pygame.transform.smoothscale(title_surface, (scaled_width, scaled_height))
        
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
            subtitle_font = pygame.font.SysFont("Arial", 14, bold=True)
            subtitle_text = "Type # or SIGLA to start:"
            subtitle_surface = subtitle_font.render(subtitle_text, True, (200, 200, 200))
            subtitle_rect = subtitle_surface.get_rect(center=(box_x + box_width // 2, box_y + 70))
            self.render_surface.blit(subtitle_surface, subtitle_rect)
            
            # Lista de países (2 columnas para compactar)
            item_font = pygame.font.SysFont("Arial", 12, bold=True)
            y_offset = box_y + 95
            line_height = 24
            col_width = box_width // 2
            
            for i, country in enumerate(self.physics_world.countries, start=1):
                abbrev = COUNTRY_ABBREV.get(country, country[:3].upper())
                color = self.physics_world.racers[country].color
                
                # Determinar columna (izquierda o derecha)
                col = 0 if i <= 6 else 1
                row = (i - 1) % 6
                
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
            subtitle_font = pygame.font.SysFont("Arial", 20, bold=True)
            subtitle_text = "TO START!"
            subtitle_surface = self._render_text_enhanced(
                subtitle_text,
                subtitle_font,
                (255, 255, 100),
                outline_color=(0, 0, 0),
                outline_width=3
            )
            
            # Aplicar escala de "respiración"
            scaled_width = int(subtitle_surface.get_width() * breathe_scale)
            scaled_height = int(subtitle_surface.get_height() * breathe_scale)
            subtitle_surface = pygame.transform.smoothscale(subtitle_surface, (scaled_width, scaled_height))
            
            # Apply pulsating alpha
            subtitle_alpha_surface = pygame.Surface(subtitle_surface.get_size(), pygame.SRCALPHA)
            subtitle_alpha_surface.fill((255, 255, 255, pulse_alpha))
            subtitle_surface = subtitle_surface.copy()
            subtitle_surface.blit(subtitle_alpha_surface, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            
            subtitle_rect = subtitle_surface.get_rect(center=(box_x + box_width // 2, box_y + 95))
            self.render_surface.blit(subtitle_surface, subtitle_rect)

        # Last winner info (if exists) - sin efecto de respiración
        if self.last_winner:
            winner_font = pygame.font.SysFont("Arial", 14, bold=True)
            winner_text = f"Last winner: {self.last_winner}"
            winner_surface = self._render_text_enhanced(
                winner_text,
                winner_font,
                (100, 255, 150),
                outline_color=(0, 0, 0),
                outline_width=2
            )
            winner_rect = winner_surface.get_rect(center=(box_x + box_width // 2, box_y + 140))
            self.render_surface.blit(winner_surface, winner_rect)
            
            # Distance info
            diamonds_approx = self._safe_int(self.last_winner_distance / 0.8, 0)
            distance_text = f"Distance: {diamonds_approx} diamonds"
            distance_surface = winner_font.render(distance_text, True, (200, 200, 200))
            distance_rect = distance_surface.get_rect(center=(box_x + box_width // 2, box_y + 165))
            self.render_surface.blit(distance_surface, distance_rect)
        
        # 🏆 Render Global Ranking Panel (futuristic style) only
        # 3D tracks visualization is reserved for post-race screens
        self._render_global_ranking_futuristic()
    
    def _render_shortcuts_panel(self) -> None:
        """
        Render shortcuts as a modern scrolling ticker at the bottom.
        Semi-transparent, non-intrusive, and always visible during racing.
        """
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT, COUNTRY_ABBREV
        
        # Ticker dimensions
        ticker_height = 28
        ticker_y = SCREEN_HEIGHT - ticker_height
        
        # Semi-transparent background
        ticker_bg = pygame.Surface((SCREEN_WIDTH, ticker_height), pygame.SRCALPHA)
        ticker_bg.fill((0, 0, 0, 180))  # Dark with 70% opacity
        self.render_surface.blit(ticker_bg, (0, ticker_y))
        
        # Build ticker content string with colors
        item_font = pygame.font.SysFont("Arial", 12, bold=True)
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
        title_font = pygame.font.SysFont("Arial", 48, bold=True)
        subtitle_font = pygame.font.SysFont("Arial", 16, bold=True)
        
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
        title_font = pygame.font.SysFont("Arial", 16, bold=True)
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
        entry_font = pygame.font.SysFont("Arial", 14, bold=True)
        medal_font = pygame.font.SysFont("Arial", 16, bold=True)
        
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
            footer_font = pygame.font.SysFont("Arial", 9)
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
        Render futuristic holographic-style global ranking panel.
        Features: Glowing cyan borders, particle effects, animated glow.
        """
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        if not self.global_rank_data:
            return
        
        # Panel dimensions (centered at top)
        panel_width = 450
        panel_height = 180
        panel_x = (SCREEN_WIDTH - panel_width) // 2
        panel_y = 20
        
        # Create panel surface with alpha for glassmorphism
        panel_surface = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
        
        # Animated glow intensity
        glow_intensity = 0.7 + 0.3 * math.sin(self.ranking_3d_animation_time * 2.0)
        
        # Glassmorphism: Semi-transparent background with blur effect simulation
        # Base glass color (dark with slight blue tint)
        glass_base = (15, 25, 45, 180)  # Semi-transparent dark blue
        
        # Draw glass background with gradient
        for i in range(panel_height):
            ratio = i / panel_height
            # Subtle gradient from slightly lighter to darker
            alpha = int(180 - 20 * ratio)  # Fade from top to bottom
            r = int(15 + 5 * (1 - ratio))
            g = int(25 + 10 * (1 - ratio))
            b = int(45 + 15 * (1 - ratio))
            pygame.draw.line(panel_surface, (r, g, b, alpha), (0, i), (panel_width, i))
        
        # Glassmorphism border: Bright, glowing border with multiple layers
        border_color_base = (100, 200, 255)  # Cyan
        border_alpha = int(220 * glow_intensity)
        
        # Outer glow layers (creates depth)
        for i in range(4):
            alpha = int(border_alpha * (0.3 / (i + 1)))
            pygame.draw.rect(
                panel_surface, 
                (*border_color_base, alpha), 
                (i, i, panel_width - i*2, panel_height - i*2), 
                2, 
                border_radius=15 - i
            )
        
        # Main bright border (glass edge effect)
        pygame.draw.rect(
            panel_surface, 
            (*border_color_base, border_alpha), 
            (0, 0, panel_width, panel_height), 
            3, 
            border_radius=15
        )
        
        # Inner highlight (top edge light reflection)
        highlight_alpha = int(150 * glow_intensity)
        pygame.draw.rect(
            panel_surface, 
            (200, 240, 255, highlight_alpha), 
            (4, 4, panel_width - 8, 8), 
            0, 
            border_radius=11
        )
        
        # Subtle inner border for depth
        pygame.draw.rect(
            panel_surface, 
            (150, 220, 255, 80), 
            (3, 3, panel_width - 6, panel_height - 6), 
            1, 
            border_radius=12
        )
        
        # Blit glassmorphic panel
        self.render_surface.blit(panel_surface, (panel_x, panel_y))
        
        # Title with glow effect - using improved font
        font_names = ["Verdana", "Arial Black", "Arial"]
        title_font = None
        for font_name in font_names:
            try:
                title_font = pygame.font.SysFont(font_name, 20, bold=True)
                break
            except:
                continue
        if title_font is None:
            title_font = pygame.font.Font(None, 20)
        
        title_text = "* WORLD RECORDS *"
        
        # Title with cyan glow
        title_color = (150, 220, 255)  # Bright cyan
        title_surface = self._render_text_enhanced(
            title_text,
            title_font,
            title_color,
            outline_color=(0, 50, 100),
            outline_width=3
        )
        title_rect = title_surface.get_rect(center=(panel_x + panel_width // 2, panel_y + 25))
        self.render_surface.blit(title_surface, title_rect)
        
        # Render Top 3 with enhanced styling - using improved fonts
        font_names = ["Verdana", "Arial Black", "Arial"]
        entry_font = None
        medal_font = None
        for font_name in font_names:
            try:
                if entry_font is None:
                    entry_font = pygame.font.SysFont(font_name, 16, bold=True)
                if medal_font is None:
                    medal_font = pygame.font.SysFont(font_name, 18, bold=True)
                if entry_font and medal_font:
                    break
            except:
                continue
        if entry_font is None:
            entry_font = pygame.font.Font(None, 16)
        if medal_font is None:
            medal_font = pygame.font.Font(None, 18)
        
        start_y = panel_y + 65
        line_height = 35
        
        # Neon colors for medals
        neon_colors = [
            (255, 215, 0),      # Gold (bright)
            (192, 192, 255),    # Silver (with blue tint)
            (255, 150, 100)     # Bronze (with orange tint)
        ]
        
        for i, entry in enumerate(self.global_rank_data[:3]):
            country = entry.get('country', 'Unknown')
            wins = entry.get('total_wins', 0)
            
            y_pos = start_y + i * line_height
            
            # Medal with glow
            medals = ['1º', '2º', '3º']
            medal = medals[i] if i < 3 else f"{i+1}º"
            medal_color = neon_colors[i] if i < 3 else (200, 200, 200)
            
            # Glow effect for medal
            glow_surf = medal_font.render(medal, True, (*medal_color, 100))
            for offset in [(1, 1), (-1, -1), (1, -1), (-1, 1)]:
                self.render_surface.blit(glow_surf, (panel_x + 25 + offset[0], y_pos + offset[1]))
            
            medal_surface = medal_font.render(medal, True, medal_color)
            self.render_surface.blit(medal_surface, (panel_x + 25, y_pos))
            
            # Country entry with abbreviation
            country_abbrev = self._get_country_abbrev(country)
            entry_text = f"[{country_abbrev}] {country[:12]}: {wins}"
            entry_color = (255, 255, 255) if i == 0 else (220, 240, 255)  # White for 1st, cyan-tinted for others
            entry_surface = entry_font.render(entry_text, True, entry_color)
            self.render_surface.blit(entry_surface, (panel_x + 70, y_pos + 2))
        
        # Footer with update time - using improved font
        if self.global_rank_last_update > 0:
            font_names = ["Verdana", "Arial Black", "Arial"]
            footer_font = None
            for font_name in font_names:
                try:
                    footer_font = pygame.font.SysFont(font_name, 10)
                    break
                except:
                    continue
            if footer_font is None:
                footer_font = pygame.font.Font(None, 10)
            elapsed = time.time() - self.global_rank_last_update
            if elapsed < 60:
                footer_text = "Updated a few seconds ago"
            elif elapsed < 3600:
                footer_text = f"Updated {int(elapsed/60)}m ago"
            else:
                footer_text = f"Updated {int(elapsed/3600)}h ago"
            
            footer_surface = footer_font.render(footer_text, True, (150, 200, 255))
            footer_rect = footer_surface.get_rect(center=(panel_x + panel_width // 2, panel_y + panel_height - 15))
            self.render_surface.blit(footer_surface, footer_rect)
    
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
            flag_font = pygame.font.SysFont("Arial", int(flag_radius * 0.8), bold=True)
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
            'USA': 'USA',
            'Indonesia': 'IDN',
            'Russia': 'RUS',
            'Italy': 'ITA'
        }
        return abbrev_map.get(country, '???')
    
    def _return_to_idle(self) -> None:
        """Return to IDLE state and save winner info."""
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
        
        # 🏁 Reset final stretch
        self.final_stretch_triggered = False
        self.final_stretch_time = 0.0
        
        # 🏆 Reset victory sequence
        self._reset_victory_sequence()
        
        # Restore original parallax speed and deactivate warp
        if self.background_manager:
            self.background_manager.set_scroll_speed(self.original_parallax_speed)
            self.background_manager.deactivate_warp_mode()
        
        logger.info("🎮 Game state: IDLE (race reset complete)")
    
    def _transition_to_racing(self) -> None:
        """
        Transition from IDLE to RACING state.
        Sets up timing for HUD animations and spotlight.
        """
        import time
        self.game_state = 'RACING'
        self.race_start_time = time.time()
        
        # Initialize spotlight position to first racer
        if self.physics_world.racers:
            first_country = list(self.physics_world.racers.keys())[0]
            racer = self.physics_world.racers[first_country]
            self.spotlight_current_pos = (racer.body.position.x, racer.body.position.y)
            self.spotlight_target_pos = self.spotlight_current_pos
        
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
        
        combo_text = f"COMBO x{count}!"
        
        # Determine font size with elastic pulse effect (grows then shrinks)
        # Larger size for milestone combos
        if count % 5 == 0:  # Milestones: 5, 10, 15, 20...
            base_font_size = 22
        else:
            base_font_size = 16
        
        self.floating_texts.append(
            FloatingText(
                text=combo_text,
                x=x,
                y=y - 40,
                color=color,
                lifespan=50,
                max_lifespan=50,
                font_size=base_font_size,
                dy=-3.0  # Fast upward
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
        
        racer = self.physics_world.racers[country]
        x = racer.body.position.x
        y = racer.body.position.y
        
        # Big announcement
        self.floating_texts.append(
            FloatingText(
                text="🔥 ON FIRE! 🔥",
                x=x,
                y=y - 50,
                color=(255, 100, 0),
                lifespan=80,
                max_lifespan=80,
                font_size=20,
                dy=-2.0
            )
        )
        
        # Initialize motion trail history
        if country not in self.motion_trail_history:
            self.motion_trail_history[country] = []
        if country not in self.motion_trails:
            self.motion_trails[country] = []
        
        # Impact shake
        self.screen_shaker.impact_shake()
        
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
            
            # Clear old segments and rebuild
            self.motion_trails[country] = []
            
            for i in range(len(history) - 1):
                x1, y1 = history[i]
                x2, y2 = history[i + 1]
                
                # Alpha fades towards the back
                alpha = 255 * (i + 1) / len(history)
                
                # Thickness increases towards the flag (front)
                thickness = 1 if i < len(history) // 2 else 2
                if country in self.on_fire_countries:
                    thickness += 1  # Thicker when ON FIRE
                
                # Apply jitter to older segments for vibration effect
                if country in self.on_fire_countries and i < len(history) - 3:
                    y1 += random.uniform(-1, 1)
                    y2 += random.uniform(-1, 1)
                
                segment = MotionTrailSegment(
                    x1=x1, y1=y1,
                    x2=x2, y2=y2,
                    color=base_color,
                    alpha=alpha,
                    thickness=thickness
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
        """Render flash effects on flags when combo levels up."""
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
            
            # Create flash surface
            flash_surf = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(
                flash_surf,
                (255, 255, 255, alpha),
                (radius, radius),
                radius,
                3  # Ring, not filled
            )
            
            self.render_surface.blit(
                flash_surf,
                (x - radius, y - radius)
            )
    
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
        
        # Impact shake
        self.screen_shaker.big_impact_shake()
        
        logger.info("🏁 FINAL STRETCH triggered with WARP MODE!")
    
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
        font = pygame.font.SysFont("Arial", 36, bold=True)
        
        # Glow effect (multiple layers)
        glow_color = (255, int(100 + 100 * pulse), 0)  # Orange pulsing
        text = "🏁 FINAL STRETCH! 🏁"
        
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
        
        # Festive colors
        colors = [
            (255, 215, 0),    # Gold
            (255, 0, 100),    # Pink
            (0, 200, 255),    # Cyan
            (100, 255, 100),  # Green
            (255, 100, 0),    # Orange
            (200, 100, 255),  # Purple
            (255, 255, 255),  # White
        ]
        
        particle = ConfettiParticle(
            x=random.uniform(0, SCREEN_WIDTH),
            y=random.uniform(-50, -10),  # Start above screen
            vx=random.uniform(-30, 30),
            vy=random.uniform(100, 250),  # Fall speed
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
            
            # Keep if still alive and on screen
            if p.lifetime > 0 and p.y < SCREEN_HEIGHT + 50:
                alive.append(p)
        
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
        title_font = pygame.font.SysFont("Arial", 42, bold=True)
        subtitle_font = pygame.font.SysFont("Arial", 20, bold=True)
        
        # Pulsing gold color
        pulse = 0.5 + 0.5 * math.sin(self.victory_sequence_time * 6.0)
        gold_color = (255, int(200 + 55 * pulse), int(50 * pulse))
        
        # Main winner text
        winner_text = f"🏆 {abbrev} WINS! 🏆"
        
        # Apply scale from entrance animation
        scaled_size = int(42 * self.victory_banner_scale)
        if scaled_size > 8:
            title_font = pygame.font.SysFont("Arial", scaled_size, bold=True)
        
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
                captain_text = f"👑 KING OF THE TRACK: {captain} 👑"
                captain_color = (255, 215, 0)  # Gold
            else:
                captain_text = f"Top Voter: {captain}"
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
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        # Only show after banner has appeared
        if self.victory_sequence_time < 2.0:
            return
        
        # Fade in
        fade_in = min(1.0, (self.victory_sequence_time - 2.0) / 0.5)
        alpha = int(255 * fade_in)
        
        # CTA text
        cta_font = pygame.font.SysFont("Arial", 16, bold=True)
        cta_text = "🎁 Send a GIFT to claim YOUR crown next race! 🎁"
        
        cta_surf = self._render_text_with_shadow(
            cta_text,
            cta_font,
            (255, 200, 100),
            shadow_offset=2
        )
        cta_surf.set_alpha(alpha)
        
        # Position at bottom of victory banner area
        cta_rect = cta_surf.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 3 + 80))
        self.render_surface.blit(cta_surf, cta_rect)
    
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
            ranking = await self.cloud_manager.get_global_ranking(limit=3)
            
            if ranking:
                self.global_rank_data = ranking
                self.global_rank_last_update = time.time()
                logger.info(f"🏆 Global ranking updated: {len(ranking)} countries")
            else:
                logger.debug("🏆 No global ranking data available")
        
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
        
        # Fall back to original logic
        return self.assign_country_to_user(username)