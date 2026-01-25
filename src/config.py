"""Configuration constants for the TikTok Live Bot."""

# Screen settings - Optimized for vertical streaming
SCREEN_WIDTH = 460
SCREEN_HEIGHT = 820

# Window margins (outer frame around the game area)
GAME_MARGIN = 40

# Auto stress test for performance testing  
AUTO_STRESS_TEST = False
STRESS_TEST_INTERVAL = 0.5

# Game Mode Selection
# Options: "GIFT" (traditional gift-based racing) or "COMMENT" (chat-based racing)
GAME_MODE = "COMMENT"  # Change to "GIFT" for traditional mode

# Game settings
FPS = 60
MAX_MESSAGES = 15
MAX_BALLS = 50

# Font settings - MEJORADOS para mejor legibilidad
FONT_SIZE = 16           # Header y texto principal (era 14)
FONT_SIZE_SMALL = 12     # Mensajes y detalles (era 11)
FONT_SIZE_MEDIUM = 14    # NUEVO - Para textos intermedios
LINE_HEIGHT = 18         # Espaciado entre líneas (era 16)
PADDING = 10             # Padding general

# Ball/Flag size settings
BALL_MIN_RADIUS = 6
BALL_MAX_RADIUS = 50

# Wall thickness
WALL_THICKNESS = 20

# Fixed window mode (no scaling needed)
DEBUG_MODE = False
ACTUAL_WIDTH = SCREEN_WIDTH + (GAME_MARGIN * 2)
ACTUAL_HEIGHT = SCREEN_HEIGHT + (GAME_MARGIN * 2)

# Physics settings (Pymunk)
GRAVITY = (0, 900)
PHYSICS_STEPS = 10

# Ball physics - more organic movement
BALL_FRICTION = 0.4
BALL_ELASTICITY = 0.85

# Wall physics
WALL_FRICTION = 0.3
WALL_ELASTICITY = 0.7

# Race Configuration - Posiciones optimizadas
RACE_START_X = 50        # Inicio de los carriles
RACE_FINISH_X = 400      # Línea de meta
FLAG_RADIUS = 12         # Flag radius (reduced to 12 for better fit in lanes)

# Race countries (used for flag sprites)
RACE_COUNTRIES = [
    "Argentina", "Brasil", "Mexico", "España",
    "Colombia", "Chile", "Peru", "Venezuela",
    "USA", "Indonesia", "Russia", "Italy",
]

# Country shortcuts for COMMENT mode (siglas + números)
COUNTRY_SHORTCUTS = {
    # Argentina
    "1": "Argentina", "arg": "Argentina", "argentina": "Argentina",
    
    # Brasil
    "2": "Brasil", "bra": "Brasil", "brasil": "Brasil", "brazil": "Brasil",
    
    # Mexico
    "3": "Mexico", "mex": "Mexico", "mexico": "Mexico", "méxico": "Mexico",
    
    # España
    "4": "España", "esp": "España", "españa": "España", "spain": "España",
    
    # Colombia
    "5": "Colombia", "col": "Colombia", "colombia": "Colombia",
    
    # Chile
    "6": "Chile", "chi": "Chile", "chile": "Chile",
    
    # Peru
    "7": "Peru", "per": "Peru", "peru": "Peru", "perú": "Peru",
    
    # Venezuela
    "8": "Venezuela", "ven": "Venezuela", "venezuela": "Venezuela", "vzla": "Venezuela",
    
    # USA
    "9": "USA", "usa": "USA", "us": "USA", "america": "USA",
    
    # Indonesia
    "10": "Indonesia", "idn": "Indonesia", "indonesia": "Indonesia", "indo": "Indonesia",
    
    # Russia
    "11": "Russia", "rus": "Russia", "russia": "Russia", "ru": "Russia",
    
    # Italy
    "12": "Italy", "ita": "Italy", "italy": "Italy", "italia": "Italy",
}

# Country abbreviations for display (3 letters)
COUNTRY_ABBREV = {
    "Argentina": "ARG",
    "Brasil": "BRA",
    "Mexico": "MEX",
    "España": "ESP",
    "Colombia": "COL",
    "Chile": "CHI",
    "Peru": "PER",
    "Venezuela": "VEN",
    "USA": "USA",
    "Indonesia": "IDN",
    "Russia": "RUS",
    "Italy": "ITA",
}

# Comment mode settings
COMMENT_POINTS_PER_MESSAGE = 1  # Points awarded per valid comment
COMMENT_COOLDOWN = 1.0  # Seconds between valid comments from same user

# Background colors - Elegant TikTok-style gradient
GRADIENT_TOP = (25, 30, 60)      # Azul medianoche
GRADIENT_BOTTOM = (10, 10, 20)   # Casi negro con toque azul
COLOR_LANE_LINE = (80, 100, 140, 80)  # Líneas azuladas visibles pero sutiles

# Outer background (window margin)
OUTER_GRADIENT_TOP = (70, 80, 110)
OUTER_GRADIENT_BOTTOM = (45, 50, 80)

# UI Colors
COLOR_BACKGROUND = (0, 0, 0)                # Black background (fallback)
COLOR_TEXT_GIFT = (255, 215, 0)            # Gold for gifts
COLOR_TEXT_SYSTEM = (200, 200, 200)        # Light gray for system messages

# Status colors
COLOR_STATUS_CONNECTED = (0, 255, 0)       # Green for connected status
COLOR_STATUS_DISCONNECTED = (255, 0, 0)    # Red for disconnected status
COLOR_STATUS_RECONNECTING = (255, 165, 0)  # Orange for reconnecting status

# Gift name to color mapping (Spanish and English names)
GIFT_COLORS = {
    # Common gifts - Spanish
    "Rosa": (255, 105, 180),           # Pink
    "rosa": (255, 105, 180),
    "Rose": (255, 105, 180),
    
    "Corazón": (255, 0, 80),           # Red
    "corazón": (255, 0, 80),
    "Heart": (255, 0, 80),
    
    "Café": (139, 90, 43),             # Brown
    "café": (139, 90, 43),
    "Coffee": (139, 90, 43),
    
    "TikTok": (0, 242, 234),           # Cyan TikTok brand
    "tiktok": (0, 242, 234),
    
    "GG": (0, 255, 127),               # Bright green
    "gg": (0, 255, 127),
    
    # More common gifts
    "Ice Cream Cone": (255, 218, 185),  # Peach
    "Helado": (255, 218, 185),
    
    "Finger Heart": (255, 105, 180),    # Pink
    "Corazón con dedos": (255, 105, 180),
    
    "Drama Queen": (148, 0, 211),       # Purple
    "Reina del drama": (148, 0, 211),
    
    "Perfume": (255, 182, 193),         # Light pink
    
    "Weights": (169, 169, 169),         # Gray
    "Pesas": (169, 169, 169),
    
    "Love you": (255, 20, 147),         # Deep pink
    "Te amo": (255, 20, 147),
    
    "Sun Cream": (255, 250, 205),       # Lemon
    "Protector solar": (255, 250, 205),
    
    "Mirror": (192, 192, 192),          # Silver
    "Espejo": (192, 192, 192),
    
    "Cap": (100, 149, 237),             # Cornflower blue
    "Gorra": (100, 149, 237),
    
    "Doughnut": (255, 192, 203),        # Pink
    "Dona": (255, 192, 203),
    
    "Galaxy": (75, 0, 130),             # Indigo
    "Galaxia": (75, 0, 130),
    
    "Lion": (255, 165, 0),              # Orange
    "León": (255, 165, 0),
    
    "Universe": (25, 25, 112),          # Midnight blue
    "Universo": (25, 25, 112),
    
    # Country colors (for flags)
    "Argentina": (116, 172, 223),       # Light blue
    "Brasil": (0, 156, 59),             # Green
    "Mexico": (0, 102, 51),             # Dark green
    "España": (200, 20, 20),           # Red
    "Colombia": (255, 205, 0),         # Yellow
    "Chile": (0, 57, 166),             # Blue
    "Peru": (212, 0, 0),               # Red
    "Venezuela": (255, 221, 0),        # Yellow
    "USA": (0, 50, 150),               # Blue (USA flag)
    "Indonesia": (200, 0, 0),          # Red (Indonesia flag)
    "Russia": (0, 50, 150),            # Blue (Russia flag)
    "Italy": (0, 150, 0),              # Green (Italy flag)
    
    # Default fallback
    "default": (255, 255, 255),
}

# Gift diamond values (approximate) for sizing
# Higher value = bigger ball
GIFT_DIAMOND_VALUES = {
    # 1 diamond gifts
    "Rosa": 1, "Rose": 1, "rosa": 1,
    "GG": 1, "gg": 1,
    "Ice Cream Cone": 1, "Helado": 1,
    
    # 5 diamond gifts
    "Finger Heart": 5, "Corazón con dedos": 5,
    "Corazón": 5, "Heart": 5,
    "Coffee": 5, "Café": 5,
    
    # 10 diamond gifts
    "Perfume": 10,
    "Weights": 10, "Pesas": 10,
    
    # 25+ diamond gifts
    "Drama Queen": 25, "Reina del drama": 25,
    "Love you": 25, "Te amo": 25,
    
    # 50+ diamond gifts
    "TikTok": 50, "tiktok": 50,
    "Cap": 50, "Gorra": 50,
    "Doughnut": 50, "Dona": 50,
    
    # 100+ diamond gifts
    "Lion": 100, "León": 100,
    
    # 500+ diamond gifts (big balls!)
    "Galaxy": 500, "Galaxia": 500,
    
    # 1000+ diamond gifts (huge!)
    "Universe": 1000, "Universo": 1000,
}

# Gift name mapping (English -> Spanish for sprites)
GIFT_NAME_MAPPING = {
    # Básicos (1-5 💎)
    "Rose": "Rosa",
    "TikTok": "TikTok",
    "Heart": "Corazon",
    "GG": "GG",
    "Ice Cream Cone": "Helado",
    
    # Medios (5-50 💎)
    "Finger Heart": "CorazonDedos",
    "Coffee": "Cafe",
    "Doughnut": "Dona",
    "Hand Hearts": "CorazonManos",
    "Sunglasses": "Lentes",
    "Cap": "Gorra",
    "Mirror": "Espejo",
    "Perfume": "Perfume",
    
    # Altos (50-500 💎)
    "Drama Queen": "ReinaDrama",
    "Love you": "TeAmo",
    "Weights": "Pesas",
    "Sun Cream": "ProtectorSolar",
    "Galaxy": "Galaxia",
    "Planet": "Planeta",
    
    # Premium (500+ 💎)
    "Lion": "Leon",
    "Whale": "Ballena",
    "Dragon": "Dragon",
    "Phoenix": "Fenix",
    "Universe": "Universo",
    "Castle": "Castillo",
}

# Reconnection settings
MAX_RETRIES = 15         # Aumentado de 5 a 15 reintentos
BASE_DELAY = 3           # Aumentado de 2 a 3 segundos
MAX_DELAY = 120          # Aumentado de 60 a 120 segundos
INITIAL_CONNECT_TIMEOUT = 45  # Tiempo de espera inicial (segundos)

# Database
import os
DATABASE_PATH = os.path.join(".", "tiktok_events.db")

# Audio settings - Usar os.path.join para compatibilidad Windows/macOS/Linux
SOUND_BGM = os.path.join("assets", "audio", "bgm.wav")
SOUND_SMALL_GIFT = os.path.join("assets", "audio", "small_gift.wav")
SOUND_BIG_GIFT = os.path.join("assets", "audio", "big_gift.wav")
SOUND_VICTORY = os.path.join("assets", "audio", "victory.wav")
SOUND_FREEZE = os.path.join("assets", "audio", "freeze_sfx.wav")

# NEW: Event-specific sound effects
SOUND_VOTE = os.path.join("assets", "audio", "vote.wav")           # Click/coin for votes
SOUND_COMBO_FIRE = os.path.join("assets", "audio", "combo_fire.wav")  # Ignition for combos
SOUND_FINAL_STRETCH = os.path.join("assets", "audio", "final_stretch.wav")  # Race siren
SOUND_COUNTDOWN = os.path.join("assets", "audio", "countdown.wav")  # Countdown beeps

# Audio volume levels
VOL_BGM = 0.3      
VOL_SFX = 0.5

# NEW: Event-specific volume levels
VOL_VOTE = 0.4           # Slightly lower for vote clicks (high frequency)
VOL_COMBO = 0.6          # Slightly higher for combo emphasis
VOL_FINAL_STRETCH = 0.7  # Louder for dramatic final stretch
VOL_VICTORY = 0.65       # Victory fanfare volume

# Floating Text Colors (VFX)
COLOR_TEXT_POSITIVE = (0, 255, 0)      # Verde brillante
COLOR_TEXT_NEGATIVE = (255, 0, 0)      # Rojo brillante
COLOR_TEXT_FREEZE = (0, 200, 255)      # Celeste hielo

# Floating Text Settings
FLOATING_TEXT_SPEED = 2.0              # Velocidad hacia arriba (pixels/frame)
FLOATING_TEXT_LIFESPAN = 60            # Duración en frames (1 segundo a 60 FPS)
FLOATING_TEXT_FONT_SIZE = 16           # Tamaño de fuente para efectos

# Game area margins (para no tapar banderas con UI)
GAME_AREA_TOP = 35       # Debajo del header
GAME_AREA_BOTTOM = 65    # Encima de la leyenda de combate

# Keyword Binding para equipos
COUNTRY_KEYWORDS = {
    # Argentina
    'arg': 'Argentina', 'argentina': 'Argentina', 'arge': 'Argentina',
    'messi': 'Argentina', '🇦🇷': 'Argentina',
    
    # Brasil
    'bra': 'Brasil', 'brasil': 'Brasil', 'brazil': 'Brasil',
    'br': 'Brasil', 'neymar': 'Brasil', '🇧🇷': 'Brasil',
    
    # México
    'mex': 'Mexico', 'mexico': 'Mexico', 'mx': 'Mexico',
    'méx': 'Mexico', 'méxico': 'Mexico', '🇲🇽': 'Mexico',
    
    # España
    'esp': 'España', 'españa': 'España', 'spain': 'España',
    'es': 'España', '🇪🇸': 'España',
    
    # Colombia
    'col': 'Colombia', 'colombia': 'Colombia', 'co': 'Colombia',
    '🇨🇴': 'Colombia',
    
    # Chile
    'chi': 'Chile', 'chile': 'Chile', 'cl': 'Chile',
    '🇨🇱': 'Chile',
    
    # Perú
    'per': 'Peru', 'peru': 'Peru', 'perú': 'Peru',
    'pe': 'Peru', '🇵🇪': 'Peru',
    
    # Venezuela
    'ven': 'Venezuela', 'venezuela': 'Venezuela', 've': 'Venezuela',
    'vzla': 'Venezuela', '🇻🇪': 'Venezuela',
    
    # USA
    'usa': 'USA', 'united states': 'USA', 'us': 'USA',
    'america': 'USA', '🇺🇸': 'USA',
    
    # Indonesia
    'ind': 'Indonesia', 'indonesia': 'Indonesia', 'id': 'Indonesia',
    '🇮🇩': 'Indonesia',
    
    # Russia
    'rus': 'Russia', 'russia': 'Russia', 'ru': 'Russia',
    'russian': 'Russia', '🇷🇺': 'Russia',
    
    # Italy
    'ita': 'Italy', 'italy': 'Italy', 'it': 'Italy',
    'italia': 'Italy', '🇮🇹': 'Italy',
}

# Anti-spam para joins
JOIN_NOTIFICATION_COOLDOWN = 5.0  # segundos entre notificaciones del mismo user