"""MotoGP Special Edition — overrides and additions over core/config.py."""

from core.config import *  # noqa: F401, F403
from core.config import GIFT_DIAMOND_VALUES as _BASE_GIFT_MAP

# ── DIVERGED overrides ──────────────────────────────────────────────────────
FPS = 30  # CPU headroom for Live Studio
FLAG_RADIUS = 10
LANE_HEIGHT = 28
MOTOGP_SPRITE_HEIGHT = 22  # px — sprite size independent of lane spacing

GRADIENT_TOP = (100, 105, 125)        # Azul pizarra claro
GRADIENT_BOTTOM = (75, 78, 95)        # Azul pizarra medio
OUTER_GRADIENT_TOP = (135, 140, 160)
OUTER_GRADIENT_BOTTOM = (105, 108, 128)

# ── GIFT_DIAMOND_VALUES: base + motos-specific changes ──────────────────────
GIFT_DIAMOND_VALUES = {
    **_BASE_GIFT_MAP,
    # Gifts repurposed as country selectors → value drops to 1 diamond
    "TikTok": 1, "tiktok": 1,
    "It's corn": 1,  # EN confirmed
    "Pop": 1, "pop": 1,
    "Maracas": 1, "maracas": 1,
    "Te adoro": 1, "te adoro": 1,
    "love you so much": 1,
    "Oldies": 1, "oldies": 1, "clasicos": 1,  # EN confirmed → Guatemala
    "white rose": 1,  # Panama
    # Value adjustments
    "Doughnut": 30, "Rosquilla": 30,
}

# ── MOTOS_ONLY additions ────────────────────────────────────────────────────
MOTOGP_MODE = True
COMBAT_FORCE_MULTIPLIER = 1.5
RACER_ASSETS_PATH = "assets/motos"
MOTOGP_LITE_PARTICLES = True
HYPE_TIMER_ENABLED = False  # Samba disaster incompatible with MotoGP edition
HYPE_TIMER_LABEL = "VUELTA FINAL EN"
HYPE_DISASTER_TITLE = "🚨 ¡ÚLTIMA VUELTA! MAX CHAOS!"

METEOR_COUNT = 10
METEOR_BOOST_MIN = 3
METEOR_BOOST_MAX = 8

# ---------------------------------------------------------------------------
# Gift → Country direct mapping (MotoGP edition)
# Keys are lowercase + stripped at runtime — include ES and EN variants.
# ⚠️ = English name unconfirmed; verify via "[Gift raw]" console log in live stream.
# ---------------------------------------------------------------------------
MOTOGP_GIFT_COUNTRY_MAP = {
    # Argentina
    "rosa": "Argentina",
    "rose": "Argentina",
    # Brasil
    "tiktok": "Brasil",
    # Mexico
    "it's corn": "Mexico",
    # Colombia
    "pop": "Colombia",
    # Chile
    "cono de helado": "Chile",
    "ice cream cone": "Chile",
    # Peru
    "te adoro": "Peru",
    "love you so much": "Peru",
    # Venezuela
    "maracas": "Venezuela",
    # Uruguay
    "gg": "Uruguay",
    # Guatemala
    "clasicos": "Guatemala",
    "oldies": "Guatemala",         # EN confirmed
    # Honduras
    "cake slice": "Honduras",      # EN confirmed
    "porcion de torta": "Honduras",
    # Panama
    "white rose": "Panama",
    # Ecuador
    "glow stick": "Ecuador",
    "batuta luminosa": "Ecuador",
    # Paraguay
    "guiño guiño": "Paraguay",
    "wink wink": "Paraguay",       # EN confirmed
    # Puerto Rico
    "youre awesome": "Puerto Rico",
    "you're awesome": "Puerto Rico",  # EN confirmed (apóstrofo estándar)
    # Bolivia
    "alas guardianes": "Bolivia",
    "guardian wings": "Bolivia",
}
