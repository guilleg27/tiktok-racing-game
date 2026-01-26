"""Asset Manager - Precarga y cachea imágenes de regalos."""

import os
import pygame
import logging
from pathlib import Path
from typing import Optional, Dict

from .config import GIFT_NAME_MAPPING, RACE_COUNTRIES
from .resources import resource_path

logger = logging.getLogger(__name__)


class AssetManager:
    """
    Gestiona la carga y cache de assets (imágenes de regalos).
    """
    
    def __init__(self, assets_path: str = "assets/gifts"):
        # Aplicar resource_path ANTES de crear el Path
        resolved_path = resource_path(assets_path)
        self.assets_path = Path(resolved_path)
        self._cache: Dict[str, pygame.Surface] = {}
        self._missing_assets: set = set()
        self.combat_icons = {}  # ← NUEVO: Inicializar diccionario de íconos de combate
        
        # Ensure assets directory exists (solo en desarrollo)
        try:
            self.assets_path.mkdir(parents=True, exist_ok=True)
        except:
            pass  # En ejecutable empaquetado, la carpeta ya existe
        
        self._preload_assets()
        self._load_combat_icons()  # ← NUEVO: Cargar íconos de combate
    
    def _preload_assets(self) -> None:
        """Precarga todas las imágenes PNG encontradas en assets/gifts/."""
        if not self.assets_path.exists():
            logger.warning(f"Assets directory not found: {self.assets_path}")
            return
        
        loaded_count = 0
        for img_path in self.assets_path.glob("*.png"):
            try:
                # Load image WITHOUT convert_alpha (no requiere display)
                surface = pygame.image.load(str(img_path))
                
                # Use filename (without extension) as key
                gift_name = img_path.stem
                self._cache[gift_name] = surface
                loaded_count += 1
                
                logger.debug(f"Loaded asset: {gift_name}")
                
            except Exception as e:
                logger.error(f"Failed to load {img_path}: {e}")
        
        logger.info(f"Asset Manager: Preloaded {loaded_count} gift sprites")
    
    def get_sprite(self, gift_name: str, size: int) -> Optional[pygame.Surface]:
        """
        Obtiene el sprite de un regalo escalado al tamaño especificado.
        
        Args:
            gift_name: Nombre del regalo (puede estar en inglés o español)
            size: Diámetro deseado en píxeles
            
        Returns:
            Surface escalado o None si no existe
        """
        # ← NUEVO: Traducir nombre si viene en inglés
        translated_name = GIFT_NAME_MAPPING.get(gift_name, gift_name)
        
        # Try translated name first
        if translated_name in self._cache:
            return self._scale_sprite(
                self._cache[translated_name],
                size,
                apply_bg_remove=self._is_country_name(translated_name)
            )
        
        # Try original name
        if gift_name in self._cache:
            return self._scale_sprite(
                self._cache[gift_name],
                size,
                apply_bg_remove=self._is_country_name(gift_name)
            )
        
        # Try case-insensitive search
        for cached_name in self._cache.keys():
            if cached_name.lower() == gift_name.lower():
                return self._scale_sprite(
                    self._cache[cached_name],
                    size,
                    apply_bg_remove=self._is_country_name(cached_name)
                )
            if cached_name.lower() == translated_name.lower():
                return self._scale_sprite(
                    self._cache[cached_name],
                    size,
                    apply_bg_remove=self._is_country_name(cached_name)
                )
        
        # Log missing asset only once
        if gift_name not in self._missing_assets:
            self._missing_assets.add(gift_name)
            logger.debug(f"Asset not found: {gift_name} (translated: {translated_name})")
        
        return None
    
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
        """Escala un sprite manteniendo aspect ratio."""
        # Create square canvas
        scaled = pygame.transform.smoothscale(surface, (size * 2, size * 2))
        # Ahora sí convert_alpha (después de que display esté inicializado)
        try:
            scaled = scaled.convert_alpha()
        except:
            pass  # Fallback si aún no hay display

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
        """Recarga todos los assets (útil para hot-reload durante desarrollo)."""
        self._cache.clear()
        self._missing_assets.clear()
        self._preload_assets()
        self._load_combat_icons()  # ← NUEVO: Recargar íconos de combate
    
    def _load_combat_icons(self) -> None:
        """Load combat power icons from assets/icons/."""
        # Usar resource_path para compatibilidad con PyInstaller
        icons_path = resource_path(os.path.join("assets", "icons"))
        icons_dir = Path(icons_path)
        
        if not icons_dir.exists():
            logger.warning(f"Icons directory not found: {icons_dir}")
            return
        
        # Mapeo: nombre interno -> nombre de archivo
        icon_files = {
            "rosa": "rose.png",
            "pesa": "weight.png",
            "hielo": "ice-cream.png"
        }
        
        for icon_name, file_name in icon_files.items():
            icon_path = icons_dir / file_name
            
            if icon_path.exists():
                try:
                    icon = pygame.image.load(str(icon_path))
                    icon = pygame.transform.scale(icon, (20, 20))
                    self.combat_icons[icon_name] = icon
                    logger.info(f"✅ Loaded combat icon: {file_name} -> {icon_name}")
                except Exception as e:
                    logger.error(f"Failed to load icon {icon_path}: {e}")
            else:
                logger.warning(f"Icon not found: {icon_path}")
        
        logger.info(f"🎨 Loaded {len(self.combat_icons)} combat icons")
    
    def get_combat_icon(self, icon_name: str) -> Optional[pygame.Surface]:
        """Get a combat icon by name."""
        return self.combat_icons.get(icon_name)
    
    @property
    def loaded_count(self) -> int:
        """Número de assets cargados."""
        return len(self._cache)
    
    @property
    def available_gifts(self) -> list[str]:
        """Lista de regalos con sprites disponibles."""
        return sorted(self._cache.keys())