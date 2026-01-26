"""Parallax Background System with Speed Lines and crisp star field."""

import pygame
import random
import math
import logging
from dataclasses import dataclass
from typing import Optional
from pathlib import Path

from .resources import resource_path

logger = logging.getLogger(__name__)


@dataclass
class Star:
    """
    Represents a single star in the procedural star field.
    
    Attributes:
        x, y: Position on screen
        size: Star radius in pixels
        speed: Horizontal movement speed (pixels per second)
        brightness: Base brightness (0.0 - 1.0)
        twinkle_offset: Phase offset for twinkle animation
        layer: Parallax layer (0=back, 1=mid, 2=front)
    """
    x: float
    y: float
    size: float
    speed: float
    brightness: float
    twinkle_offset: float
    layer: int


@dataclass
class SpeedLine:
    """
    Represents a horizontal speed line for motion effect.
    Creates crisp, sharp lines that convey velocity.
    
    Attributes:
        x, y: Position (left edge of line)
        length: Line length in pixels (20-100)
        speed: Movement speed (pixels per second)
        color: RGB color tuple
        alpha: Transparency (0-255)
        thickness: Line thickness (1-2 pixels)
    """
    x: float
    y: float
    length: float
    speed: float
    color: tuple[int, int, int]
    alpha: int
    thickness: int


class BackgroundManager:
    """
    Manages parallax scrolling background with crisp visuals.
    
    Features:
    - Multi-layer star field with sharp rendering
    - Speed Lines system for motion effect
    - Final Stretch "Warp Speed" mode
    - No blurry nebulas - all crisp edges
    """
    
    def __init__(self, width: int, height: int):
        """
        Initialize the background manager.
        
        Args:
            width: Screen width in pixels
            height: Screen height in pixels
        """
        self.width = width
        self.height = height
        
        # Background layers
        self.background_image: Optional[pygame.Surface] = None
        self.has_image_bg = False
        
        # Procedural star field
        self.stars: list[Star] = []
        
        # Speed Lines system
        self.speed_lines: list[SpeedLine] = []
        self.max_speed_lines = 30  # Normal mode
        self.speed_line_spawn_rate = 0.1  # Seconds between spawns
        self.last_speed_line_spawn = 0.0
        
        # Scroll state
        self.scroll_offset = 0.0
        self.scroll_speed = 50.0  # pixels per second (base speed)
        
        # Animation time
        self.time = 0.0
        
        # Final Stretch / Warp mode
        self.warp_mode = False
        self.warp_speed_lines_max = 100  # Triple for warp
        
        # Tension mode (after crossing final stretch line - red/orange theme)
        self.tension_mode = False
        
        # Pre-rendered static background (dark gradient, no nebulas)
        self.static_bg: Optional[pygame.Surface] = None
        self.tension_bg: Optional[pygame.Surface] = None
        
        # Try to load image, fallback to procedural
        self._try_load_background_image()
        if not self.has_image_bg:
            self._generate_star_field()
        
        # Create static background (clean gradient, NO nebulas)
        self._create_static_background()
        # Pre-create tension background (red/orange theme)
        self._create_tension_background()
        
        # Pre-generate some speed lines
        self._init_speed_lines()
        
        logger.info(f"🌌 BackgroundManager initialized ({'image' if self.has_image_bg else 'procedural'}) with Speed Lines")
    
    def _try_load_background_image(self) -> None:
        """Attempt to load a background image from assets."""
        bg_paths = [
            "assets/backgrounds/space.png",
            "assets/backgrounds/cyberpunk.png",
            "assets/backgrounds/bg.png",
            "assets/bg.png",
        ]
        
        for path in bg_paths:
            try:
                full_path = resource_path(path)
                if Path(full_path).exists():
                    self.background_image = pygame.image.load(full_path)
                    # Scale to fit height, tile horizontally
                    scale_factor = self.height / self.background_image.get_height()
                    new_width = int(self.background_image.get_width() * scale_factor)
                    self.background_image = pygame.transform.smoothscale(
                        self.background_image, 
                        (new_width, self.height)
                    )
                    self.has_image_bg = True
                    logger.info(f"✅ Loaded background image: {path}")
                    return
            except Exception as e:
                logger.debug(f"Could not load {path}: {e}")
        
        logger.info("🌟 No background image found, using procedural star field")
    
    def _generate_star_field(self) -> None:
        """Generate a multi-layer procedural star field with crisp stars."""
        # Layer configuration: (count, size_range, speed_multiplier, brightness_range)
        layers = [
            (60, (1, 1), 0.2, (0.2, 0.4)),     # Back layer: tiny dots, very slow
            (40, (1, 2), 0.5, (0.4, 0.6)),     # Mid layer: small dots
            (25, (2, 3), 0.8, (0.6, 0.9)),     # Front layer: slightly larger
        ]
        
        self.stars.clear()
        
        for layer_idx, (count, size_range, speed_mult, brightness_range) in enumerate(layers):
            for _ in range(count):
                star = Star(
                    x=random.uniform(0, self.width),
                    y=random.uniform(0, self.height),
                    size=random.randint(*size_range),  # Integer for crisp rendering
                    speed=self.scroll_speed * speed_mult,
                    brightness=random.uniform(*brightness_range),
                    twinkle_offset=random.uniform(0, 2 * math.pi),
                    layer=layer_idx
                )
                self.stars.append(star)
        
        logger.info(f"⭐ Generated {len(self.stars)} crisp stars across 3 layers")
    
    def _create_static_background(self) -> None:
        """Create a clean static background gradient (no nebulas)."""
        self.static_bg = pygame.Surface((self.width, self.height))
        
        # Deep space gradient (top to bottom) - clean, no alpha blending
        for y in range(self.height):
            ratio = y / self.height
            # Dark blue to almost black
            r = int(8 + 12 * (1 - ratio))
            g = int(10 + 15 * (1 - ratio))
            b = int(25 + 25 * (1 - ratio))
            pygame.draw.line(self.static_bg, (r, g, b), (0, y), (self.width, y))
    
    def _create_tension_background(self) -> None:
        """Create tension background with red/orange theme for high-stakes moments."""
        try:
            self.tension_bg = pygame.Surface((self.width, self.height))
            
            # Red/orange gradient (top to bottom) - intense, dramatic
            for y in range(self.height):
                ratio = y / self.height
                # Dark red/orange to deep red-black
                r = int(25 + 30 * (1 - ratio))
                g = int(5 + 10 * (1 - ratio))
                b = int(5 + 8 * (1 - ratio))
                pygame.draw.line(self.tension_bg, (r, g, b), (0, y), (self.width, y))
        except Exception as e:
            logger.error(f"Failed to create tension background: {e}")
            self.tension_bg = None
    
    def _init_speed_lines(self) -> None:
        """Pre-generate initial speed lines."""
        for _ in range(15):
            self._spawn_speed_line(random_x=True)
    
    def _spawn_speed_line(self, random_x: bool = False) -> None:
        """
        Spawn a new speed line.
        
        Args:
            random_x: If True, spawn anywhere. If False, spawn at right edge.
        """
        max_lines = self.warp_speed_lines_max if self.warp_mode else self.max_speed_lines
        
        if len(self.speed_lines) >= max_lines:
            return
        
        # Position
        x = random.uniform(0, self.width) if random_x else self.width + 10
        y = random.uniform(0, self.height)
        
        # Length (20-100 pixels)
        length = random.uniform(20, 100)
        
        # Speed (faster than stars, varies by layer effect)
        base_speed = self.scroll_speed * random.uniform(3.0, 6.0)
        if self.warp_mode:
            base_speed *= 2.0  # Double speed in warp
        
        # Colors: red/orange in tension mode, white/blue otherwise
        if self.tension_mode:
            color_choices = [
                (255, 100, 80),     # Bright red-orange
                (255, 150, 100),   # Orange-red
                (255, 80, 60),      # Deep red
                (255, 120, 90),     # Warm red-orange
            ]
        else:
            color_choices = [
                (255, 255, 255),    # Pure white
                (220, 230, 255),    # Light blue-white
                (240, 240, 255),    # Very light blue
                (255, 255, 240),    # Warm white
            ]
        color = random.choice(color_choices)
        
        # Alpha (subtle, not too bright)
        if self.tension_mode:
            alpha = random.randint(100, 200)  # Brighter in tension
        elif self.warp_mode:
            alpha = random.randint(80, 180)  # Brighter in warp
        else:
            alpha = random.randint(40, 120)
        
        # Thickness (1-2 pixels for crisp look)
        thickness = random.choice([1, 1, 1, 2])  # Mostly 1px
        
        self.speed_lines.append(SpeedLine(
            x=x, y=y, length=length, speed=base_speed,
            color=color, alpha=alpha, thickness=thickness
        ))
    
    def activate_warp_mode(self) -> None:
        """Activate warp speed mode (Final Stretch)."""
        if not self.warp_mode:
            self.warp_mode = True
            # Spawn extra speed lines immediately
            for _ in range(50):
                self._spawn_speed_line(random_x=True)
            logger.info("🚀 WARP MODE activated!")
    
    def deactivate_warp_mode(self) -> None:
        """Deactivate warp speed mode."""
        self.warp_mode = False
    
    def activate_tension_mode(self) -> None:
        """Activate tension mode (red/orange theme after crossing final stretch line)."""
        if not self.tension_mode:
            self.tension_mode = True
            # Spawn more intense speed lines
            for _ in range(30):
                self._spawn_speed_line(random_x=True)
            logger.info("🔥 TENSION MODE activated - red/orange theme!")
    
    def deactivate_tension_mode(self) -> None:
        """Deactivate tension mode."""
        self.tension_mode = False
    
    def update(self, dt: float) -> None:
        """
        Update background animation state.
        
        Args:
            dt: Delta time since last frame in seconds
        """
        self.time += dt
        self.scroll_offset += self.scroll_speed * dt
        
        # Wrap scroll offset to prevent float overflow
        if self.has_image_bg and self.background_image:
            if self.scroll_offset >= self.background_image.get_width():
                self.scroll_offset -= self.background_image.get_width()
        else:
            if self.scroll_offset >= self.width:
                self.scroll_offset -= self.width
        
        # Update stars (procedural mode)
        if not self.has_image_bg:
            for star in self.stars:
                star.x -= star.speed * dt
                if star.x < -star.size:
                    star.x = self.width + star.size
                    star.y = random.uniform(0, self.height)
        
        # Update speed lines
        alive_lines = []
        for line in self.speed_lines:
            line.x -= line.speed * dt
            if line.x + line.length > 0:  # Still on screen
                alive_lines.append(line)
        self.speed_lines = alive_lines
        
        # Spawn new speed lines
        self.last_speed_line_spawn += dt
        spawn_rate = 0.03 if self.warp_mode else 0.1
        if self.last_speed_line_spawn >= spawn_rate:
            self.last_speed_line_spawn = 0.0
            spawn_count = 3 if self.warp_mode else 1
            for _ in range(spawn_count):
                self._spawn_speed_line()
    
    def render(self, surface: pygame.Surface) -> None:
        """
        Render the background to the given surface.
        
        Args:
            surface: Target surface to draw on
        """
        if self.has_image_bg:
            self._render_image_background(surface)
        else:
            self._render_procedural_background(surface)
        
        # Always render speed lines on top
        self._render_speed_lines(surface)
    
    def _render_image_background(self, surface: pygame.Surface) -> None:
        """Render scrolling image background with seamless tiling."""
        if not self.background_image:
            return
        
        img_width = self.background_image.get_width()
        offset = int(self.scroll_offset) % img_width
        
        surface.blit(self.background_image, (-offset, 0))
        if offset > 0:
            surface.blit(self.background_image, (img_width - offset, 0))
        if img_width - offset < self.width:
            surface.blit(self.background_image, (2 * img_width - offset, 0))
    
    def _render_procedural_background(self, surface: pygame.Surface) -> None:
        """Render procedural star field with crisp edges."""
        # Draw background: tension (red) or normal (blue)
        try:
            if self.tension_mode and self.tension_bg:
                surface.blit(self.tension_bg, (0, 0))
            elif self.static_bg:
                surface.blit(self.static_bg, (0, 0))
        except Exception as e:
            logger.error(f"Error rendering background gradient: {e}")
            # Fallback: draw a simple dark background
            surface.fill((10, 10, 20))
        
        # Draw stars as crisp points (no glow for sharpness)
        for star in self.stars:
            # Subtle twinkle
            twinkle = 0.8 + 0.2 * math.sin(self.time * 2.0 + star.twinkle_offset)
            brightness = star.brightness * twinkle
            
            # Color based on layer and mode
            if self.tension_mode:
                # Red/orange stars in tension mode
                if star.layer == 0:
                    r = int(255 * brightness)
                    g = int(120 * brightness)
                    b = int(80 * brightness)
                elif star.layer == 1:
                    r = int(255 * brightness)
                    g = int(150 * brightness)
                    b = int(100 * brightness)
                else:
                    r = int(255 * brightness)
                    g = int(180 * brightness)
                    b = int(120 * brightness)
            else:
                # Normal blue/white stars
                if star.layer == 0:
                    r = int(180 * brightness)
                    g = int(190 * brightness)
                    b = int(255 * brightness)
                elif star.layer == 1:
                    r = int(220 * brightness)
                    g = int(220 * brightness)
                    b = int(255 * brightness)
                else:
                    r = int(255 * brightness)
                    g = int(250 * brightness)
                    b = int(245 * brightness)
            
            # Draw star as crisp rectangle (1x1 or 2x2 pixel)
            size = int(star.size)
            if size <= 1:
                # Single pixel - direct set for maximum crispness
                ix, iy = int(star.x), int(star.y)
                if 0 <= ix < self.width and 0 <= iy < self.height:
                    surface.set_at((ix, iy), (r, g, b))
            else:
                # Small rectangle for slightly larger stars
                pygame.draw.rect(
                    surface,
                    (r, g, b),
                    (int(star.x), int(star.y), size, size)
                )
    
    def _render_speed_lines(self, surface: pygame.Surface) -> None:
        """Render speed lines with crisp pygame.draw.line."""
        for line in self.speed_lines:
            # Calculate end position
            x1 = int(line.x)
            y = int(line.y)
            x2 = int(line.x + line.length)
            
            # Skip if completely off screen
            if x2 < 0 or x1 > self.width:
                continue
            
            # Clamp to screen bounds
            x1 = max(0, x1)
            x2 = min(self.width, x2)
            
            # Create color with alpha for subtle effect
            # Since pygame.draw.line doesn't support alpha directly,
            # we use aaline for slightly smoother but still crisp lines
            if line.thickness == 1:
                # Use aaline for 1px with alpha simulation via color
                faded_color = (
                    int(line.color[0] * line.alpha / 255),
                    int(line.color[1] * line.alpha / 255),
                    int(line.color[2] * line.alpha / 255)
                )
                pygame.draw.line(surface, faded_color, (x1, y), (x2, y), 1)
            else:
                # 2px line
                faded_color = (
                    int(line.color[0] * line.alpha / 255),
                    int(line.color[1] * line.alpha / 255),
                    int(line.color[2] * line.alpha / 255)
                )
                pygame.draw.line(surface, faded_color, (x1, y), (x2, y), line.thickness)
    
    def set_scroll_speed(self, speed: float) -> None:
        """
        Set the base scroll speed.
        
        Args:
            speed: New scroll speed in pixels per second
        """
        ratio = speed / self.scroll_speed if self.scroll_speed > 0 else 1.0
        self.scroll_speed = speed
        
        for star in self.stars:
            star.speed *= ratio
    
    def boost_speed(self, multiplier: float, duration: float = 0.0) -> None:
        """
        Temporarily boost scroll speed.
        
        Args:
            multiplier: Speed multiplier
            duration: How long the boost lasts (0 = permanent)
        """
        self.scroll_speed *= multiplier
        for star in self.stars:
            star.speed *= multiplier
