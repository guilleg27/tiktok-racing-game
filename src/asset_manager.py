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
        Remove a solid background color using the corner pixel as reference.
        
        Args:
            surface: Surface to clean.
        
        Returns:
            Surface with background pixels made transparent.
        """
        width, height = surface.get_size()
        bg_color = surface.get_at((0, 0))[:3]
        tolerance = 10
        
        cleaned = surface.copy()
        for x in range(width):
            for y in range(height):
                r, g, b, a = cleaned.get_at((x, y))
                if (
                    abs(r - bg_color[0]) <= tolerance
                    and abs(g - bg_color[1]) <= tolerance
                    and abs(b - bg_color[2]) <= tolerance
                ):
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
    
    
"""Audio Manager - Maneja la reproducción de sonidos y música."""

import pygame
import logging
from pathlib import Path
from typing import Optional, Dict
import threading
import time

from .config import (
    SOUND_BGM, SOUND_SMALL_GIFT, SOUND_BIG_GIFT, SOUND_VICTORY, SOUND_FREEZE,
    VOL_BGM, VOL_SFX, GIFT_DIAMOND_VALUES
)

logger = logging.getLogger(__name__)


class AudioManager:
    """
    Gestiona la carga, cache y reproducción de audio.
    Inicializa pygame.mixer con parámetros de baja latencia.
    """
    
    def __init__(self, assets_path: str = "assets/audio"):
        # Aplicar resource_path ANTES de crear el Path  
        resolved_path = resource_path(assets_path)
        self.assets_path = Path(resolved_path)
        self._sound_cache: Dict[str, pygame.mixer.Sound] = {}
        self._missing_sounds: set = set()
        self._bgm_channel: Optional[pygame.mixer.Channel] = None
        self._initialized = False
        
        # Ensure audio directory exists (solo en desarrollo)
        try:
            self.assets_path.mkdir(parents=True, exist_ok=True)
        except:
            pass  # En ejecutable empaquetado, la carpeta ya existe
    
        self._init_mixer()
        self._preload_sounds()
    
    def _init_mixer(self) -> None:
        """
        Inicializa pygame.mixer con parámetros compatibles con Windows/macOS/Linux.
        Usa configuración genérica para evitar conflictos con drivers de audio exclusivos.
        """
        import platform
        
        try:
            # Configuración específica por sistema operativo
            if platform.system() == "Windows":
                # Windows: usar driver DirectSound (más compatible)
                # Evitar conflictos con drivers WASAPI exclusivos
                import os
                os.environ.setdefault('SDL_AUDIODRIVER', 'directsound')
                
                # Buffer más grande en Windows para estabilidad
                buffer_size = 1024
            else:
                # macOS/Linux: buffer pequeño para baja latencia
                buffer_size = 512
            
            # Pre-inicializar con parámetros seguros
            pygame.mixer.pre_init(
                frequency=44100,      # Alta calidad
                size=-16,             # 16-bit signed (más compatible)
                channels=2,           # Stereo
                buffer=buffer_size    # Ajustado por SO
            )
            
            # Inicializar mixer
            pygame.mixer.init()
            
            # Establecer canales de sonido para reproducción concurrente
            pygame.mixer.set_num_channels(8)
            
            self._initialized = True
            logger.info(f"🔊 Audio initialized: {platform.system()}, buffer={buffer_size}")
            
        except pygame.error as e:
            logger.warning(f"Primary audio init failed: {e}, trying fallback...")
            
            # Fallback: inicialización mínima sin pre_init
            try:
                pygame.mixer.quit()  # Limpiar cualquier estado previo
                pygame.mixer.init()  # Usar valores por defecto del sistema
                pygame.mixer.set_num_channels(4)  # Menos canales como fallback
                self._initialized = True
                logger.info("🔊 Audio initialized with fallback settings")
            except Exception as e2:
                logger.error(f"Audio initialization failed completely: {e2}")
                self._initialized = False
                
        except Exception as e:
            logger.error(f"Failed to initialize audio mixer: {e}")
            self._initialized = False
    
    def _preload_sounds(self) -> None:
        """Precarga todos los sonidos definidos en config.py."""
        if not self._initialized:
            logger.warning("Audio mixer not initialized, skipping sound preload")
            return
        
        # Define sound files to load
        sound_files = {
            'bgm': SOUND_BGM,
            'small_gift': SOUND_SMALL_GIFT,
            'big_gift': SOUND_BIG_GIFT,
            'victory': SOUND_VICTORY,
            'freeze': SOUND_FREEZE
        }
        
        loaded_count = 0
        for sound_name, sound_path in sound_files.items():
            try:
                full_path = Path(resource_path(sound_path))
                
                if not full_path.exists():
                    logger.warning(f"Audio file not found: {sound_path}")
                    self._missing_sounds.add(sound_name)
                    continue
                
                # Load sound
                sound = pygame.mixer.Sound(str(full_path))
                self._sound_cache[sound_name] = sound
                loaded_count += 1
                
                logger.debug(f"Loaded audio: {sound_name} from {sound_path}")
                
            except Exception as e:
                logger.error(f"Failed to load {sound_path}: {e}")
                self._missing_sounds.add(sound_name)
        
        logger.info(f"Audio Manager: Preloaded {loaded_count}/{len(sound_files)} audio files")
    
    def play_bgm(self) -> None:
        """Reproduce música de fondo en loop infinito."""
        if not self._initialized or 'bgm' not in self._sound_cache:
            logger.debug("BGM not available or audio not initialized")
            return
        
        try:
            # Stop current BGM if playing
            if self._bgm_channel and self._bgm_channel.get_busy():
                self._bgm_channel.stop()
            
            # Play BGM on a specific channel with loop
            bgm_sound = self._sound_cache['bgm']
            bgm_sound.set_volume(VOL_BGM)
            self._bgm_channel = bgm_sound.play(-1)  # -1 = infinite loop
            
            logger.info("Background music started")
            
        except Exception as e:
            logger.error(f"Failed to play BGM: {e}")
    
    def play_sfx(self, sound_type: str, gift_name: Optional[str] = None, diamond_count: Optional[int] = None) -> None:
        """
        Reproduce un efecto de sonido en un canal libre.
        
        Args:
            sound_type: Tipo de sonido ('small', 'big', 'victory')
            gift_name: Nombre del regalo (para determinar si es pequeño o grande)
            diamond_count: Valor en diamantes (para determinar si es pequeño o grande)
        """
        if not self._initialized:
            logger.debug("Audio not initialized, skipping SFX")
            return
        
        # Determine which sound to play
        sound_key = None
        
        if sound_type == 'victory':
            sound_key = 'victory'
        elif sound_type in ['small', 'big']:
            sound_key = f'{sound_type}_gift'
        else:
            # Auto-determine based on gift value
            if gift_name and diamond_count is None:
                diamond_count = GIFT_DIAMOND_VALUES.get(gift_name, 1)
        
            if diamond_count and diamond_count >= 10:
                sound_key = 'big_gift'
            else:
                sound_key = 'small_gift'
    
        # ADD DEBUG LOGGING HERE
        logger.info(f"🔊 SFX: {gift_name} ({diamond_count}💎) → {sound_key}")
    
        if sound_key not in self._sound_cache:
            if sound_key not in self._missing_sounds:
                logger.debug(f"Sound not available: {sound_key}")
            return
        
        try:
            # Play sound on any available channel
            sound = self._sound_cache[sound_key]
            sound.set_volume(VOL_SFX)
            sound.play()
            
            logger.info(f"✅ Played SFX: {sound_key} (volume: {VOL_SFX})")
            
        except Exception as e:
            logger.error(f"Failed to play SFX {sound_key}: {e}")
    
    def play_freeze_sfx(self) -> None:
        """
        Reproduce el sonido de efecto freeze cuando se congela un país.
        """
        if not self._initialized:
            logger.debug("Audio not initialized, skipping freeze SFX")
            return
        
        if 'freeze' not in self._sound_cache:
            if 'freeze' not in self._missing_sounds:
                logger.debug("Freeze sound (freeze_sfx.wav) not available")
            return
        
        try:
            # Play freeze sound on any available channel
            sound = self._sound_cache['freeze']
            sound.set_volume(VOL_SFX)
            sound.play()
            
            logger.info(f"✅ Played freeze SFX: jump (volume: {VOL_SFX})")
            
        except Exception as e:
            logger.error(f"Failed to play freeze SFX: {e}")
    
    def lower_bgm_volume(self, duration: float = 2.0) -> None:
        """
        Baja momentáneamente el volumen de la música de fondo y lo restaura.
        
        Args:
            duration: Duración en segundos para mantener el volumen bajo
        """
        if not self._bgm_channel or not self._bgm_channel.get_busy():
            return
        
        if 'bgm' not in self._sound_cache:
            return
        
        try:
            bgm_sound = self._sound_cache['bgm']
            original_volume = VOL_BGM
            lowered_volume = original_volume * 0.3  # 30% of original
            
            # Lower volume immediately
            bgm_sound.set_volume(lowered_volume)
            logger.debug(f"BGM volume lowered to {lowered_volume:.2f} for {duration}s")
            
            # Schedule volume restoration using a simple timer approach
            import pygame
            
            def restore_volume():
                try:
                    if 'bgm' in self._sound_cache:
                        self._sound_cache['bgm'].set_volume(original_volume)
                        logger.debug(f"BGM volume restored to {original_volume:.2f}")
                except Exception as e:
                    logger.error(f"Failed to restore BGM volume: {e}")
            
            # Use pygame's timer to restore volume after duration
            pygame.time.set_timer(pygame.USEREVENT + 1, int(duration * 1000))
            
            # We'll need to handle this event in the game loop
            self._volume_restore_callback = restore_volume
            
        except Exception as e:
            logger.error(f"Failed to lower BGM volume: {e}")
    
    def stop_bgm(self) -> None:
        """Detiene la música de fondo."""
        if self._bgm_channel and self._bgm_channel.get_busy():
            self._bgm_channel.stop()
            logger.info("Background music stopped")
    
    def is_bgm_playing(self) -> bool:
        """Verifica si la música de fondo está reproduciéndose."""
        return bool(self._bgm_channel and self._bgm_channel.get_busy())
    
    @property
    def loaded_sounds_count(self) -> int:
        """Número de sonidos cargados exitosamente."""
        return len(self._sound_cache)
    
    @property
    def missing_sounds(self) -> set:
        """Conjunto de sonidos que no se pudieron cargar."""
        return self._missing_sounds.copy()