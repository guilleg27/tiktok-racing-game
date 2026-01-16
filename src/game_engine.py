"""Game Engine - Consumer that renders TikTok events using Pygame + Pymunk."""

import asyncio
import logging
from typing import Optional
import math
import random
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
    
    def __init__(
        self, 
        queue: asyncio.Queue, 
        streamer_name: str,
        database: Optional[Database] = None
    ):
        self.queue = queue
        self.streamer_name = streamer_name
        self.database = database
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
        
        # Physics World
        self.physics_world = PhysicsWorld(
            asset_manager=self.asset_manager,
            game_engine=self
        )
        
        # Particle system
        self.particles: list[Particle] = []
        
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
        self.last_winner = None  # Último ganador de la carrera anterior
        self.last_winner_distance = 0.0  # Distancia del último ganador
        
        # Leader change animation (VFX)
        self.last_leader_name = None  # Líder del frame anterior
        self.leader_pop_timer = 0  # Temporizador para efecto "pop" (frames)
    
    def init_pygame(self) -> None:
        """Initialize Pygame with centered window and gradient background."""
        import os
        
        # Center the window on screen
        os.environ['SDL_VIDEO_WINDOW_POS'] = 'center'
        
        pygame.init()
        
        from .config import (
            ACTUAL_WIDTH, ACTUAL_HEIGHT, SCREEN_WIDTH, SCREEN_HEIGHT,
            GRADIENT_TOP, GRADIENT_BOTTOM
        )
        
        pygame.display.set_caption(f"TikTokGameWindow")
        
        # Use fixed size (no scaling needed since ACTUAL = SCREEN now)
        self.screen = pygame.display.set_mode((ACTUAL_WIDTH, ACTUAL_HEIGHT))
        self.render_surface = self.screen
        self.display_scale = 1.0
        self.clock = pygame.time.Clock()
        
        try:
            self.font = pygame.font.SysFont("Arial", FONT_SIZE, bold=True)
            self.font_small = pygame.font.SysFont("Arial", FONT_SIZE_SMALL)
        except Exception:
            self.font = pygame.font.Font(None, FONT_SIZE)
            self.font_small = pygame.font.Font(None, FONT_SIZE_SMALL)
        
        # Create static gradient background (optimización - se crea una sola vez)
        self.gradient_background = self._create_gradient_background()
        
        # NOW render flag emojis (pygame is initialized)
        self._render_flag_emojis()
        
        logger.info(
            f"🎮 Pygame initialized: {ACTUAL_WIDTH}x{ACTUAL_HEIGHT} | "
            f"Gradient: {GRADIENT_TOP} → {GRADIENT_BOTTOM}"
        )
        logger.info(f"📦 Loaded {self.asset_manager.loaded_count} gift sprites")
        
        # Start background music (after pygame is fully initialized)
        self.audio_manager.play_bgm()
        logger.info(f"🎵 Audio Manager: BGM started, {self.audio_manager.loaded_sounds_count} sounds loaded")
    
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
    
    def _render_flag_emojis(self) -> None:
        """Render flag emojis as sprites for countries without PNG sprites."""
        emoji_map = {
            "Argentina": "🇦🇷", "Brasil": "🇧🇷", "Mexico": "🇲🇽",
            "España": "🇪🇸", "Colombia": "🇨🇴", "Chile": "🇨🇱",
            "Peru": "🇵🇪", "Venezuela": "🇻🇪", "Uruguay": "🇺🇾",
            "Ecuador": "🇪🇨"
        }
        
        for country, racer in self.physics_world.racers.items():
            # Skip if already has sprite
            if racer.sprite is not None:
                continue
            
            # Try to render emoji
            if country in emoji_map:
                try:
                    font = pygame.font.SysFont("Apple Color Emoji", 40)  # ← ERA 60, AHORA 40
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
            country, assignment_type = self.assign_country_to_user(username)
            
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
                
                count = 10 + int(diamond_count / 10)
                power = 0.8
                
                self.emit_explosion(
                    pos=pos,
                    color=racer.color,
                    count=count,
                    power=power,
                    diamond_count=diamond_count
                )
                
                # Emit floating text feedback
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
    
    def update(self, dt: float) -> None:
        """Update physics and particles."""
        self.physics_world.update(dt)
        self.update_particles(dt)
        self.update_floating_texts()
        
        # Update idle animation timer
        if self.game_state == 'IDLE':
            self.idle_animation_time += dt
        
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
    
    def render(self) -> None:
        """Render all visual elements."""
        from .config import ACTUAL_WIDTH, ACTUAL_HEIGHT
        
        # Use pre-rendered gradient background
        self.render_surface.blit(self.gradient_background, (0, 0))
        
        self._render_balls()
        self._render_particles()
        self._render_floating_texts()
        self._render_header()
        self._render_legend()
        self._render_leaderboard()
        
        # Render IDLE screen on top if in IDLE state
        if self.game_state == 'IDLE':
            self._render_idle_screen()
    
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
        
        # Draw country name con TEXTO MEJORADO
        ix = self._safe_int(x, self.physics_world.start_x)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        
        # Usar texto mejorado con outline grueso
        text_enhanced = self._render_text_enhanced(
            racer.country,
            self.font_small,
            (255, 255, 255),
            outline_color=(0, 0, 0),
            outline_width=2  # Outline más grueso
        )
        text_rect = text_enhanced.get_rect(center=(ix, iy))
        self.render_surface.blit(text_enhanced, text_rect)

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

        leaderboard = self.physics_world.get_leaderboard()
        table_w, table_h = 420, 420
        table_x = (SCREEN_WIDTH - table_w) // 2
        table_y = SCREEN_HEIGHT - table_h - 60

        bar_margin_left = 100
        bar_margin_right = 20
        bar_h = 10
        bar_w = table_w - bar_margin_left - bar_margin_right
        bar_x = bar_margin_left

        surf = pygame.Surface((table_w, table_h), pygame.SRCALPHA)
        pygame.draw.rect(surf, (5, 5, 10, 255), (0, 0, table_w, table_h), border_radius=10)
        pygame.draw.rect(surf, (255, 215, 0, 180), (0, 0, table_w, table_h), 2, border_radius=10)
        
        header_font = pygame.font.SysFont("Arial", 18, bold=True)
        hdr = header_font.render("CLASIFICACION FINAL", True, (255, 215, 0))
        surf.blit(hdr, (15, 10))

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
            
            pygame.draw.rect(surf, bg, (10, y - 5, table_w - 20, row_h - 4), border_radius=6)

            # Position con medalla de color
            if position <= 3:
                # Dibujar círculo de medalla
                medal_color = medal_colors[position]
                pygame.draw.circle(surf, medal_color, (25, y + 8), 10)
                pygame.draw.circle(surf, (255, 255, 255), (25, y + 8), 10, 1)
                pos_s = row_font.render(f"{position}", True, (0, 0, 0))
                surf.blit(pos_s, (21, y))
            else:
                pos_s = row_font.render(f"{position}", True, (200, 200, 200))
                surf.blit(pos_s, (20, y))
        
            # Country name (sin medal emoji)
            country_s = row_font.render(country, True, (255, 255, 255))
            surf.blit(country_s, (45, y))

            # Distance en diamantes (sin emoji)
            dist_val = distance if (isinstance(distance, (int, float)) and math.isfinite(distance)) else 0.0
            diamonds_approx = self._safe_int(dist_val / 0.8, 0)
            dist_txt = f"{diamonds_approx}d"
            dist_s = row_font.render(dist_txt, True, (255, 215, 100))
            surf.blit(dist_s, (table_w - 70, y))

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
            "PODERES DE COMBATE",
            title_font,
            (255, 235, 50),
            outline_color=(0, 0, 0),
            outline_width=3
        )
        self.render_surface.blit(title_enhanced, (padding, legend_y + 2))
        
        # Combat items
        items = [
            ("rosa", "+5m", "Rosa", (255, 120, 180)),
            ("pesa", "Frena Lider", "Pesa", (180, 180, 180)),
            ("hielo", "Congela 3s", "Helado", (120, 220, 255)),
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
        # Eliminar emojis y caracteres especiales
        sanitized = ''.join(char for char in username if ord(char) < 127)
        
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
        title_text = "¡ENVÍA UNA ROSA"
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
        subtitle_text = "PARA INICIAR!"
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
            winner_text = f"Último ganador: {self.last_winner}"
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
            distance_text = f"Distancia: {diamonds_approx} diamantes"
            distance_surface = winner_font.render(distance_text, True, (200, 200, 200))
            distance_rect = distance_surface.get_rect(center=(box_x + box_width // 2, box_y + 165))
            self.render_surface.blit(distance_surface, distance_rect)
    
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
        
        # Change to IDLE state
        self.game_state = 'IDLE'
        self.idle_animation_time = 0.0
        
        logger.info("🎮 Game state: IDLE (race reset complete)")