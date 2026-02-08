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