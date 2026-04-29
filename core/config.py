"""Shared configuration constants — used by all variants of the racing bot."""

import os

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

# Font settings - Roboto for bold display, fallbacks for compatibility
DISPLAY_FONT_NAMES = ["Roboto", "Arial Black", "Verdana", "Arial"]
FONT_SIZE = 18
FONT_SIZE_SMALL = 12
FONT_SIZE_MEDIUM = 14
LINE_HEIGHT = 18
PADDING = 10

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
PHYSICS_STEPS = 3   # horizontal-only race with Lerp movement needs no more than 3 substeps
# Fixed timestep for physics (Hz). Independent of render FPS for consistent simulation.
PHYSICS_FIXED_HZ = 60

# Ball physics - more organic movement
BALL_FRICTION = 0.4
BALL_ELASTICITY = 0.85

# Wall physics
WALL_FRICTION = 0.3
WALL_ELASTICITY = 0.7

LANE_HEIGHT = 50  # Max px per lane; track is centered vertically when this caps the computed value

# Race Configuration - Safe zone for TikTok Live layout
SAFE_ZONE_LEFT_MARGIN = 0.20   # 20% - flags must not touch left edge (TikTok comments)
SAFE_ZONE_FINISH_RATIO = 0.90  # 90% - finish line avoids Share/Like buttons on right
RACE_OFFSET_X = int(SCREEN_WIDTH * SAFE_ZONE_LEFT_MARGIN)   # Start after comments zone
RACE_FINISH_X = int(SCREEN_WIDTH * SAFE_ZONE_FINISH_RATIO)  # Meta avoids right-side buttons
RACE_START_X = RACE_OFFSET_X
FLAG_RADIUS = 8

# Race countries (used for flag sprites)
RACE_COUNTRIES = [
    "Argentina", "Brasil", "Mexico", "Colombia",
    "Chile", "Peru", "Venezuela", "Uruguay",
]

# Country shortcuts for COMMENT mode (siglas + números)
COUNTRY_SHORTCUTS = {
    # Argentina
    "1": "Argentina", "arg": "Argentina", "argentina": "Argentina",

    # Brasil
    "2": "Brasil", "bra": "Brasil", "brasil": "Brasil", "brazil": "Brasil",

    # Mexico
    "3": "Mexico", "mex": "Mexico", "mexico": "Mexico", "méxico": "Mexico",

    # Colombia
    "4": "Colombia", "col": "Colombia", "colombia": "Colombia",

    # Chile
    "5": "Chile", "chi": "Chile", "chile": "Chile",

    # Peru
    "6": "Peru", "per": "Peru", "peru": "Peru", "perú": "Peru",

    # Venezuela
    "7": "Venezuela", "ven": "Venezuela", "venezuela": "Venezuela", "vzla": "Venezuela",

    # Uruguay
    "8": "Uruguay", "uru": "Uruguay", "uruguay": "Uruguay",
    "uy": "Uruguay",
}

# Country abbreviations for display (3 letters)
COUNTRY_ABBREV = {
    "Argentina": "ARG",
    "Brasil": "BRA",
    "Mexico": "MEX",
    "Colombia": "COL",
    "Chile": "CHI",
    "Peru": "PER",
    "Venezuela": "VEN",
    "Uruguay": "URU",
}

# Comment mode settings
COMMENT_POINTS_PER_MESSAGE = 1  # Points awarded per valid comment
COMMENT_DISTANCE_MULTIPLIER = 0.33  # Distance scale for comment votes vs gifts (lower = harder race)
COMMENT_COOLDOWN = 1.0  # Seconds between valid comments from same user

# Combo system
# combo_window is intentionally wider than TikTok Live's typical 2–4 s latency so
# two gifts sent back-to-back always register as a combo.
COMBO_WINDOW = 5.0      # seconds — rolling window for combo counting
COMBO_THRESHOLD = 3     # minimum gifts in window to trigger "COMBO!" display
ON_FIRE_THRESHOLD = 10  # minimum gifts in window to trigger "ON FIRE" state

# ---------------------------------------------------------------------------
# Auto-Pilot (Chaos Loop) — visual activity during stream inactivity
# Never injects fake events or writes to DB — direct physics/visual calls only
# ---------------------------------------------------------------------------
AUTOPILOT_ENABLED              = True
AUTOPILOT_IDLE_THRESHOLD       = 45.0   # Seconds of silence before activation
AUTOPILOT_COOLDOWN_AFTER_REAL  = 20.0   # Pause after real viewer activity (s)
AUTOPILOT_INTERVAL_MU          = 5.0    # Gaussian mean for action interval (s)
AUTOPILOT_INTERVAL_SIGMA       = 1.5    # Gaussian std-dev for action interval (s)
AUTOPILOT_MIN_INTERVAL         = 3.0    # Minimum seconds between chaos actions
AUTOPILOT_MAX_INTERVAL         = 9.0    # Maximum seconds between chaos actions
AUTOPILOT_NEW_RACE_DELAY       = 7.0    # Wait before new race after autopilot victory

# ─── HYPE TIMER (Disaster Countdown) ────────────────────────────────────────
HYPE_TIMER_ENABLED          = True
HYPE_TIMER_INTERVAL         = 120.0   # seconds between disasters (2 min)
HYPE_TIMER_URGENCY_SECS     = 10.0    # below this → red/flashing
HYPE_TIMER_HOST_CUE_SECS    = 30.0   # console cue for streamer
HYPE_TIMER_LABEL            = "DESASTRE EN"
HYPE_DISASTER_TITLE         = "🚨 ¡DESASTRE MÁXIMO!"

# Background colors - Elegant TikTok-style gradient
GRADIENT_TOP = (25, 30, 60)       # Azul medianoche
GRADIENT_BOTTOM = (10, 10, 20)    # Casi negro con toque azul
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
    "Colombia": (255, 205, 0),         # Yellow
    "Chile": (0, 57, 166),             # Blue
    "Peru": (212, 0, 0),               # Red
    "Venezuela": (255, 221, 0),        # Yellow
    # Default fallback
    "default": (255, 255, 255),
}

# Gift diamond values (approximate) for sizing
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

    # 500+ diamond gifts
    "Galaxy": 500, "Galaxia": 500,

    # 1000+ diamond gifts
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
MAX_RETRIES = 15
BASE_DELAY = 3
MAX_DELAY = 120
INITIAL_CONNECT_TIMEOUT = 45  # seconds

# Database
DATABASE_PATH = os.path.join(".", "tiktok_events.db")

# Audio settings
SOUND_BGM = os.path.join("assets", "audio", "bgm.wav")
SOUND_SMALL_GIFT = os.path.join("assets", "audio", "small_gift.wav")
SOUND_BIG_GIFT = os.path.join("assets", "audio", "big_gift.wav")
SOUND_VICTORY = os.path.join("assets", "audio", "victory.wav")
SOUND_FREEZE = os.path.join("assets", "audio", "freeze_sfx.wav")
SOUND_VOTE = os.path.join("assets", "audio", "vote.wav")
SOUND_COMBO_FIRE = os.path.join("assets", "audio", "combo_fire.wav")
SOUND_FINAL_STRETCH = os.path.join("assets", "audio", "final_stretch.wav")
SOUND_COUNTDOWN = os.path.join("assets", "audio", "countdown.wav")

# Audio volume levels
VOL_BGM = 0.3
VOL_SFX = 0.5
VOL_VOTE = 0.4
VOL_COMBO = 0.6
VOL_FINAL_STRETCH = 0.7
VOL_VICTORY = 0.65

# Floating Text Colors (VFX)
COLOR_TEXT_POSITIVE = (0, 255, 0)
COLOR_TEXT_NEGATIVE = (255, 0, 0)
COLOR_TEXT_FREEZE = (0, 200, 255)
COLOR_NEON_CYAN = (0, 255, 255)

# Floating Text Settings
FLOATING_TEXT_TOP_Y = 180
FLOATING_TEXT_SPEED = 1.0
FLOATING_TEXT_LIFESPAN = 90
FLOATING_TEXT_FONT_SIZE = 16

# CTA banner and likes bar layout
CTA_BANNER_Y = 36
CTA_BANNER_HEIGHT = 42
CTA_BANNER_WIDTH = 420
LIKES_BAR_HEIGHT = 12
LIKES_BAR_TOP_GAP = 20
GAME_AREA_TOP = 114
GAME_AREA_BOTTOM = 65

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

    # Uruguay
    'uru': 'Uruguay', 'uruguay': 'Uruguay', 'uy': 'Uruguay',
    '🇺🇾': 'Uruguay',
}

# Anti-spam para joins
JOIN_NOTIFICATION_COOLDOWN = 5.0  # segundos entre notificaciones del mismo user

# Visual Welcome (room join) - retention mechanic
WELCOME_COOLDOWN = 1.5
MAX_SIMULTANEOUS_WELCOMES = 2
WELCOME_TEXT_Y = 380
WELCOME_TEXT_LIFESPAN = 120
WELCOME_FONT_SIZE = 16

# Likes goal bar (retention mechanic - Meteor Shower event)
LIKES_GOAL_INITIAL = 500
LIKES_SIMULATED_PER_KEY = 50
METEOR_COUNT = 10
METEOR_BOOST_MIN = 3
METEOR_BOOST_MAX = 8

# TTS (Text-to-Speech) voice announcer
TTS_ENABLED = False

# ---------------------------------------------------------------------------
# Follower Wall
# ---------------------------------------------------------------------------
FOLLOWER_BANNER_LIFESPAN  = 150
FOLLOWER_BANNER_Y         = 410
FOLLOWER_BANNER_WIDTH     = 340
FOLLOWER_BANNER_HEIGHT    = 64

# ---------------------------------------------------------------------------
# Hype Mode
# ---------------------------------------------------------------------------
HYPE_THRESHOLD_CPM = 30
HYPE_COOLDOWN_DURATION = 120.0
HYPE_PHYSICS_MULTIPLIER = 1.15

HYPE_NEON_COLORS = [
    (255, 0, 120),    # neon pink
    (0, 120, 255),    # electric blue
    (0, 255, 220),    # cyan
    (180, 0, 255),    # violet
]
HYPE_OVERLAY_ALPHA = 18
HYPE_COLOR_CYCLE_SPEED = 0.5

# ---------------------------------------------------------------------------
# Blackout Mode
# ---------------------------------------------------------------------------
BLACKOUT_INITIAL_ALPHA      = 190
BLACKOUT_MAX_ALPHA          = 240
BLACKOUT_INCREASE_PER_SEC   = 2
BLACKOUT_RECHARGE_DECREASE  = 35
BLACKOUT_HYPE_INTERVAL      = 30.0
BLACKOUT_HYPE_CHANCE        = 0.05
BLACKOUT_ENABLED            = False

# ---------------------------------------------------------------------------
# MotoGP variant flags (overridden by variants/motos/config.py via bootstrap)
# ---------------------------------------------------------------------------
MOTOGP_MODE             = False
MOTOGP_LITE_PARTICLES   = False
MOTOGP_GIFT_COUNTRY_MAP: dict = {}
COMBAT_FORCE_MULTIPLIER = 1.0

# Path to racer sprites (flags for countries, motorcycles for motos)
RACER_ASSETS_PATH = "assets/flags"
