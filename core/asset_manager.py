"""Asset Manager - Precarga y cachea imágenes de regalos."""

import os
import pygame
import logging
from pathlib import Path
from typing import Optional, Dict, Tuple

from .config import GIFT_NAME_MAPPING, RACE_COUNTRIES
from .resources import resource_path

logger = logging.getLogger(__name__)


class AssetManager:
    """
    Gestiona la carga y cache de assets (imágenes de regalos).
    All surfaces are converted at load time for zero per-frame conversion cost.
    Scaled sprites are cached by (name, size) to avoid scaling in the render loop.
    """
    
    def __init__(self, assets_path: str = "assets/gifts"):
        # Aplicar resource_path ANTES de crear el Path
        resolved_path = resource_path(assets_path)
        self.assets_path = Path(resolved_path)
        self._cache: Dict[str, pygame.Surface] = {}
        self._scale_cache: Dict[Tuple[str, int], pygame.Surface] = {}
        self._missing_assets: set = set()
        
        # Ensure assets directory exists (solo en desarrollo)
        try:
            self.assets_path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass  # En ejecutable empaquetado, la carpeta ya existe
        
        self._preload_assets()
    
    def _preload_assets(self) -> None:
        """Preload all PNG images; convert to display format immediately to avoid per-frame conversion."""
        if not self.assets_path.exists():
            logger.warning(f"Assets directory not found: {self.assets_path}")
            return
        
        loaded_count = 0
        for img_path in self.assets_path.glob("*.png"):
            try:
                surface = pygame.image.load(str(img_path))
                gift_name = img_path.stem
                # Store raw loaded surface. Conversion happens in _scale_sprite (after display
                # is initialized) so we avoid "cannot convert without pygame.display" at import time.
                self._cache[gift_name] = surface
                loaded_count += 1
                logger.debug(f"Loaded asset: {gift_name}")
            except Exception as e:
                logger.error(f"Failed to load {img_path}: {e}")
        
        logger.info(f"Asset Manager: Preloaded {loaded_count} gift sprites")
    
    def get_sprite(self, gift_name: str, size: int) -> Optional[pygame.Surface]:
        """
        Returns a sprite scaled to the given size. Uses a cache keyed by (name, size)
        so scaling is done once per (gift_name, size), not in the render loop.
        
        Args:
            gift_name: Gift or country name (English or Spanish).
            size: Desired diameter in pixels.
            
        Returns:
            Scaled surface or None if not found.
        """
        translated_name = GIFT_NAME_MAPPING.get(gift_name, gift_name)
        cache_key: Optional[Tuple[str, int]] = None
        source: Optional[pygame.Surface] = None
        apply_bg = False
        
        if translated_name in self._cache:
            cache_key = (translated_name, size)
            source = self._cache[translated_name]
            apply_bg = self._is_country_name(translated_name)
        elif gift_name in self._cache:
            cache_key = (gift_name, size)
            source = self._cache[gift_name]
            apply_bg = self._is_country_name(gift_name)
        else:
            for cached_name in self._cache:
                if cached_name.lower() == gift_name.lower():
                    cache_key = (cached_name, size)
                    source = self._cache[cached_name]
                    apply_bg = self._is_country_name(cached_name)
                    break
                if cached_name.lower() == translated_name.lower():
                    cache_key = (cached_name, size)
                    source = self._cache[cached_name]
                    apply_bg = self._is_country_name(cached_name)
                    break
        
        if source is None or cache_key is None:
            if gift_name not in self._missing_assets:
                self._missing_assets.add(gift_name)
                logger.debug(f"Asset not found: {gift_name} (translated: {translated_name})")
            return None
        
        if cache_key in self._scale_cache:
            return self._scale_cache[cache_key]
        
        scaled = self._scale_sprite(source, size, apply_bg_remove=apply_bg)
        if scaled is not None:
            self._scale_cache[cache_key] = scaled
        return scaled
    
    def get_sprite_for_racer(self, gift_name: str, target_height: int) -> Optional[pygame.Surface]:
        """Scale sprite to target_height preserving aspect ratio, no background removal.
        Used for motorcycle sprites in MOTOGP_MODE where images are non-square and
        may contain dark areas that the standard background removal would incorrectly strip.

        Args:
            gift_name: Country name matching the asset file.
            target_height: Desired height in pixels; width computed from source aspect ratio.

        Returns:
            Scaled surface or None if asset not found.
        """
        translated_name = GIFT_NAME_MAPPING.get(gift_name, gift_name)
        source: Optional[pygame.Surface] = None

        if translated_name in self._cache:
            source = self._cache[translated_name]
        elif gift_name in self._cache:
            source = self._cache[gift_name]
        else:
            for cached_name in self._cache:
                if cached_name.lower() in (gift_name.lower(), translated_name.lower()):
                    source = self._cache[cached_name]
                    break

        if source is None:
            return None

        orig_w, orig_h = source.get_size()
        if orig_h == 0:
            return None

        target_w = max(1, int(orig_w * target_height / orig_h))
        scaled = pygame.transform.smoothscale(source, (target_w, target_height))  # scale first, BG intact
        cleaned = self._remove_light_background(scaled)  # remove BG after scaling to avoid halo fringe
        try:
            return cleaned.convert_alpha()
        except Exception:
            return cleaned

    def _remove_light_background(self, surface: pygame.Surface) -> pygame.Surface:
        """Flood-fill background removal starting from image borders.
        Only removes pixels reachable from the border — interior motorcycle
        pixels are never touched even if they match the background color.
        """
        from collections import deque
        width, height = surface.get_size()

        # --- Step 1: detect dominant border color ---
        step = max(1, (width + height) // 150)
        border_samples = []
        for x in range(0, width, step):
            for cy in (0, height - 1):
                r, g, b, a = surface.get_at((x, cy))
                if a > 0:
                    border_samples.append((r, g, b))
        for y in range(0, height, step):
            for cx in (0, width - 1):
                r, g, b, a = surface.get_at((cx, y))
                if a > 0:
                    border_samples.append((r, g, b))

        if len(border_samples) < 5:
            return surface

        cluster_tol = 30
        best_color = None
        best_count = 0
        for candidate in border_samples:
            matching = [
                c for c in border_samples
                if abs(c[0] - candidate[0]) <= cluster_tol and
                   abs(c[1] - candidate[1]) <= cluster_tol and
                   abs(c[2] - candidate[2]) <= cluster_tol
            ]
            if len(matching) > best_count:
                best_count = len(matching)
                best_color = tuple(
                    sum(c[i] for c in matching) // len(matching) for i in range(3)
                )

        if best_color is None or best_count < len(border_samples) * 0.4:
            return surface

        # --- Step 2: BFS flood fill from all 4 border edges ---
        removal_tol = 50
        cleaned = surface.copy()
        visited: set[tuple[int, int]] = set()
        queue: deque[tuple[int, int]] = deque()

        def matches_bg(r: int, g: int, b: int, a: int) -> bool:
            return (a > 0 and
                    abs(r - best_color[0]) <= removal_tol and
                    abs(g - best_color[1]) <= removal_tol and
                    abs(b - best_color[2]) <= removal_tol)

        cleaned.lock()
        for x in range(width):
            for cy in (0, height - 1):
                if (x, cy) not in visited:
                    r, g, b, a = cleaned.get_at((x, cy))
                    if matches_bg(r, g, b, a):
                        visited.add((x, cy))
                        queue.append((x, cy))
        for y in range(height):
            for cx in (0, width - 1):
                if (cx, y) not in visited:
                    r, g, b, a = cleaned.get_at((cx, y))
                    if matches_bg(r, g, b, a):
                        visited.add((cx, y))
                        queue.append((cx, y))

        while queue:
            cx, cy = queue.popleft()
            r, g, b, _ = cleaned.get_at((cx, cy))
            cleaned.set_at((cx, cy), (r, g, b, 0))
            for nx, ny in ((cx + 1, cy), (cx - 1, cy), (cx, cy + 1), (cx, cy - 1)):
                if 0 <= nx < width and 0 <= ny < height and (nx, ny) not in visited:
                    r2, g2, b2, a2 = cleaned.get_at((nx, ny))
                    if matches_bg(r2, g2, b2, a2):
                        visited.add((nx, ny))
                        queue.append((nx, ny))

        cleaned.unlock()
        return cleaned

    def _normalize_name(self, name: str) -> str:
        """Normaliza el nombre para búsqueda."""
        # Remove accents, spaces, lowercase
        normalized = name.lower().replace(" ", "").replace("_", "")
        return normalized
    
    def _scale_sprite(
        self,
        surface: pygame.Surface,
        size: int,
        apply_bg_remove: bool = False,
    ) -> pygame.Surface:
        """Scale sprite to (size*2, size*2). Uses scale() not smoothscale() for performance (no scaling in render loop)."""
        w = size * 2
        scaled = pygame.transform.scale(surface, (w, w))
        try:
            scaled = scaled.convert_alpha()
        except Exception:
            pass
        if apply_bg_remove:
            return self._remove_background_color(scaled)
        return scaled

    def _is_country_name(self, name: str) -> bool:
        """
        Check if a sprite name matches a racing country.

        Args:
            name: Sprite name to validate.

        Returns:
            True if the name belongs to a racing country.
        """
        return name.lower() in {country.lower() for country in RACE_COUNTRIES}

    def _remove_background_color(self, surface: pygame.Surface) -> pygame.Surface:
        """
        Remove background color from flag sprites.
        Samples multiple corner pixels and removes matching colors.
        Also removes common dark backgrounds.
        
        Args:
            surface: Surface to clean.
        
        Returns:
            Surface with background pixels made transparent.
        """
        width, height = surface.get_size()
        
        # Sample corners to find likely background colors
        corners = [
            (0, 0), (width - 1, 0),
            (0, height - 1), (width - 1, height - 1)
        ]
        
        bg_colors = set()
        for cx, cy in corners:
            try:
                color = surface.get_at((cx, cy))[:3]
                bg_colors.add(color)
            except:
                pass
        
        # Also add common dark backgrounds that might appear
        bg_colors.add((0, 0, 0))        # Pure black
        bg_colors.add((1, 1, 1))        # Near black
        bg_colors.add((30, 35, 55))     # Dark blue-ish (matches game bg)
        bg_colors.add((25, 30, 50))     # Variant
        bg_colors.add((20, 25, 45))     # Variant
        
        tolerance = 25  # Increased tolerance for better matching
        
        cleaned = surface.copy()
        for x in range(width):
            for y in range(height):
                r, g, b, a = cleaned.get_at((x, y))
                
                # Skip already transparent pixels
                if a == 0:
                    continue
                
                # Check against all known background colors
                should_remove = False
                for bg_color in bg_colors:
                    if (
                        abs(r - bg_color[0]) <= tolerance
                        and abs(g - bg_color[1]) <= tolerance
                        and abs(b - bg_color[2]) <= tolerance
                    ):
                        should_remove = True
                        break
                
                # Also remove very dark pixels near edges (common background)
                edge_margin = 3
                is_near_edge = (x < edge_margin or x >= width - edge_margin or 
                               y < edge_margin or y >= height - edge_margin)
                is_very_dark = (r < 40 and g < 45 and b < 60)
                
                if should_remove or (is_near_edge and is_very_dark):
                    cleaned.set_at((x, y), (r, g, b, 0))
        
        return cleaned
    
    def reload(self) -> None:
        """Reload all assets and clear scale cache (for hot-reload during development)."""
        self._cache.clear()
        self._scale_cache.clear()
        self._missing_assets.clear()
        self._preload_assets()
    
    @property
    def loaded_count(self) -> int:
        """Número de assets cargados."""
        return len(self._cache)
    
    @property
    def available_gifts(self) -> list[str]:
        """Lista de regalos con sprites disponibles."""
        return sorted(self._cache.keys())