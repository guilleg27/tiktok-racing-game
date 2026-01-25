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
                life_ratio = particle.lifetime / self.trail_lifetime
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
        """Render the floating text with fade effect."""
        if self.lifespan <= 0:
            return
        
        # Calculate alpha
        alpha = int(255 * (self.lifespan / self.max_lifespan))
        alpha = max(0, min(255, alpha))
        
        # Create font con BOLD para mejor legibilidad
        try:
            font = pygame.font.SysFont("Arial", self.font_size, bold=True)
        except:
            font = pygame.font.Font(None, self.font_size)
    
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
            life_ratio = particle.lifetime / particle.max_lifetime
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
                self.game_state = 'RACING'
                logger.info("🏁 Game state: RACING (first gift received!)")
        
            gift_count = event.extra.get("count", 1) if event.extra else 1
            diamond_count = event.extra.get("diamond_count", 1) if event.extra else 1
            gift_name = event.content
            username = self.sanitize_username(event.username)
            
            # SMART COUNTRY ASSIGNMENT
            country, assignment_type = self._get_user_country_with_autojoin(username, gift_name)
            
            # 🏆 CAPTAIN SYSTEM: Track points
            self._update_captain_points(username, country, diamond_count)

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
                        self.game_state = 'RACING'
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
                        self.game_state = 'RACING'
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

                elif event.key == pygame.K_1:  # 1 = Test Rosa
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self.game_state = 'RACING'
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
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

                elif event.key == pygame.K_2:  # 2 = Test Pesa (ataca líder)
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self.game_state = 'RACING'
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
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
                    
                elif event.key == pygame.K_3:  # 3 = Test Helado (congela líder)
                    # CAMBIAR A RACING SI ESTÁ EN IDLE
                    if self.game_state == 'IDLE':
                        self.game_state = 'RACING'
                        logger.info("🏁 Game state: RACING (test mode)")
    
                    countries = list(self.physics_world.racers.keys())
                    country = random.choice(countries)
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
        
        Args:
            country: Country that got a new captain
            new_captain: Username of new captain
            old_captain: Username of previous captain (can be empty)
        """
        # Find racer position for floating text
        if country not in self.physics_world.racers:
            return
        
        racer = self.physics_world.racers[country]
        lane_y = self.physics_world.game_area_top + (racer.lane * self.physics_world.lane_height) + (self.physics_world.lane_height // 2)
        
        # Golden floating text for new captain
        self.spawn_floating_text(
            f"NEW CAPTAIN: @{new_captain}!",
            200,  # Mid-lane position
            lane_y,
            (255, 215, 0)  # Gold color
        )
        
        # Set timer for captain highlight effect
        self.captain_change_timer[country] = 90  # 1.5 seconds at 60fps

    def update(self, dt: float) -> None:
        """Update physics and particles."""
        # Update captain change timers
        for country in list(self.captain_change_timer.keys()):
            self.captain_change_timer[country] -= 1
            if self.captain_change_timer[country] <= 0:
                del self.captain_change_timer[country]

        self.physics_world.update(dt)
        self.update_particles(dt)
        self.update_floating_texts()
        
        # Update victory flash effect (fade out) - non-blocking, runs independently
        if self.victory_flash_alpha > 0:
            self.victory_flash_time += dt
            # Fade out over 0.3 seconds
            fade_progress = self.victory_flash_time / self.victory_flash_duration
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
                winner_country = self.physics_world.winner
                winner_captain = self.current_captains.get(winner_country, "Unknown")
                winner_points = self.session_points.get(winner_country, {}).get(winner_captain, 0)
                
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
        
        # Use pre-rendered gradient background in game area
        self.render_surface.blit(self.gradient_background, (0, 0))
        
        self._render_balls()
        self._render_trails()  # Render trails before particles (behind)
        self._render_particles()
        self._render_floating_texts()
        self._render_header()
        self._render_legend()
        self._render_leaderboard()
        
        # Render IDLE screen on top if in IDLE state
        if self.game_state == 'IDLE':
            self._render_idle_screen()
        
        # Render victory flash effect (white screen flash) - on top of everything
        if self.victory_flash_alpha > 0:
            self._render_victory_flash()
    
        # Blit game area into the window with margins
        self.screen.blit(self.render_surface, (GAME_MARGIN, GAME_MARGIN))
        pygame.display.flip()
    
    def _render_balls(self) -> None:
        """Render all flag racers with winner spotlight."""
        # Draw lanes
        self._render_lanes()
        
        # Draw finish line
        self._render_finish_line()
        
        # Render non-winners first (back layer)
        winner = self.physics_world.winner if self.physics_world.race_finished else None
        
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
    
    def _render_racer(self, racer, is_winner: bool = False) -> None:
        """Render a single racer flag."""
        x, y = racer.body.position
        radius = racer.shape.radius
        angle = racer.body.angle
        
        # Sanitize position values
        x = float(x) if math.isfinite(x) else self.physics_world.start_x
        y = float(y) if math.isfinite(y) else (racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2)
        radius = float(radius) if math.isfinite(radius) else 30
        
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
        """Render header with connection status."""
        header_surface = pygame.Surface((SCREEN_WIDTH, self.header_height), pygame.SRCALPHA)
        header_surface.fill((20, 20, 20, 230))
        self.render_surface.blit(header_surface, (0, 0))
        
        status_color = self._get_status_color()
        circle_x = PADDING + 6
        circle_y = self.header_height // 2
        pygame.draw.circle(self.render_surface, status_color, (circle_x, circle_y), 7)
        
        title = f"@{self.streamer_name}"
        title_surface = self.font.render(title, True, (255, 255, 255))
        self.render_surface.blit(title_surface, (circle_x + 20, circle_y - 10))
        
        status_text = self._get_status_text()
        status_surface = self.font_small.render(status_text, True, status_color)
        self.render_surface.blit(status_surface, (circle_x + 20, circle_y + 4))
        
        # Leader info (solo posición y país)
        leader_info = self.physics_world.get_leader()
        leader_text = f"1st: {leader_info[0]}" if leader_info else "1st: ---"
        
        # 🎯 EFECTO POP cuando cambia el líder
        if self.leader_pop_timer > 0:
            # Escala 1.1x durante el pop
            pop_scale = 1.1
            pop_font = pygame.font.SysFont("Arial", int(FONT_SIZE * pop_scale), bold=True)
            count_surface = pop_font.render(leader_text, True, (255, 255, 0))  # Amarillo brillante
        else:
            count_surface = self.font.render(leader_text, True, (255, 255, 255))
        
        # Centrar el texto (considerando el cambio de tamaño)
        text_rect = count_surface.get_rect()
        text_rect.right = SCREEN_WIDTH - 10
        text_rect.centery = circle_y
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
    
    def _render_idle_screen(self) -> None:
        """Render the IDLE state screen with animated prompt."""
        from .config import SCREEN_WIDTH, SCREEN_HEIGHT
        
        # 1️⃣ OVERLAY OSCURO (alpha=150 como solicitado)
        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))  # ← Cambiado de 180 a 150
        self.render_surface.blit(overlay, (0, 0))
        
        # Central message box
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

        # Main title - renderizar primero a tamaño base
        title_font = pygame.font.SysFont("Arial", 24, bold=True)
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
        
        title_rect = title_surface.get_rect(center=(box_x + box_width // 2, box_y + 60))
        self.render_surface.blit(title_surface, title_rect)

        # Subtitle con mismo efecto de respiración
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
        logger.info("🎮 Game state: IDLE (race reset complete)")

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
        
        logger.info("🎮 Game state: IDLE (race reset complete)")
    
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