"""
Versus variant config — 1v1 duelo entre dos equipos.
MVP: Boca Juniors vs River Plate.

Importa todo el core y sobreescribe solo lo necesario.
"""

from core.config import *  # noqa: F401, F403

# ── IDENTIDAD DEL DUELO ─────────────────────────────────────────────────────
VERSUS_MODE = True

# Portrait layout: reserve the top of the game canvas for TikTok/OBS face-cam.
# Physics and HUD use the band below this (core default was 114).
GAME_AREA_TOP: int = 200

# Definición de los dos equipos
TEAM_LEFT = {
    "name":      "River",
    "short":     "RIV",
    "color":     (255, 255, 255),   # Blanco millonario
    "accent":    (220, 40, 40),     # Rojo
    "keywords":  ["river", "riv", "millo", "millonario", "rvr", "r", "1"],
}

TEAM_RIGHT = {
    "name":      "Boca",
    "short":     "BOC",
    "color":     (0, 80, 200),      # Azul xeneize
    "accent":    (255, 215, 0),     # Amarillo
    "keywords":  ["boca", "boc", "xeneize", "boquense", "b", "2"],
}

# Clave: nombre del gift en minúsculas (como llega de TikTok, ES y EN)
# Valor: nombre del equipo ("River" o "Boca")
VERSUS_GIFT_TEAM_MAP: dict[str, str] = {
    # River = Rosquilla / Doughnut (30 monedas)
    "rosquilla":  "River",
    "doughnut":   "River",
    "dona":       "River",         # nombre sprite local

    # Boca = Capibara / Capybara (30 monedas)
    "capibara":   "Boca",
    "capybara":   "Boca",
}

# ── MODO VICTORIA ───────────────────────────────────────────────────────────
# "score"  → primer equipo en llegar a SCORE_LIMIT gana el set
# "time"   → al acabar MATCH_DURATION_SECS gana quien tenga más score
VICTORY_MODE: str = "time"

SCORE_LIMIT: int = 10          # puntos para ganar en modo "score"
MATCH_DURATION_SECS: float = 600.0   # 1 min para pruebas; cambiar a 600.0 para producción (10 min)
# MATCH_DURATION_SECS: float = 600.0   # 1 min para pruebas; cambiar a 600.0 para producción (10 min)

# ── GOL DE ORO (muerte súbita) ───────────────────────────────────────────────
# When regular time ends in a tie, golden goal / sudden death starts immediately.
# No extra-time countdown — the next team to score wins.
EXTRA_TIME_SECS: float = 0.0     # unused; kept for compatibility
GOLDEN_GOAL_ENABLED: bool = True  # always True; first goal wins on tie

# ── AUTOPILOT (core) ─────────────────────────────────────────────────────────
# Versus: solo regalos reales; sin simulación de caos en IDLE.
AUTOPILOT_ENABLED: bool = False

# ── CONVERSIÓN GIFT → PUNTOS ─────────────────────────────────────────────────
# Override del valor 30 monedas mapeados como 1 punto de juego para no
# que el score sea en diamantes sino en "goles" lógicos
VERSUS_GIFT_POINT_VALUE: int = 1   # cada gift mapeado = 1 punto

# ── PANTALLA DE VICTORIA ─────────────────────────────────────────────────────
VICTORY_SCREEN_DURATION: float = 30.0   # segundos mostrando la pantalla
SHOW_TOP_DONOR_GLOBAL: bool = True       # top donador global del stream
SHOW_MVP_WINNER_TEAM: bool = True        # MVP del equipo ganador

# ── TECLAS DEMO (modo desarrollo sin TikTok conectado) ───────────────────────
DEMO_KEY_TEAM_LEFT  = "q"   # Q → gift a River
DEMO_KEY_TEAM_RIGHT = "w"   # W → gift a Boca
DEMO_GIFT_NAME_LEFT  = "Rosquilla"
DEMO_GIFT_NAME_RIGHT = "Capibara"

# ── OVERRIDES VISUALES ───────────────────────────────────────────────────────
# Fondo más dramático para el clásico
GRADIENT_TOP    = (10, 10, 30)
GRADIENT_BOTTOM = (5, 5, 15)
OUTER_GRADIENT_TOP    = (40, 40, 70)
OUTER_GRADIENT_BOTTOM = (20, 20, 45)

# Ancho de pantalla (mismo que core)
# PhysicsWorld usará solo 2 carriles (uno por equipo)
VERSUS_NUM_LANES: int = 2

# Assets de los equipos (imagen circular / escudo simplificado como texto)
# Si no existen los PNGs el engine hace fallback a texto con las siglas
RACER_ASSETS_PATH = "assets/versus"

# ── SUPABASE ─────────────────────────────────────────────────────────────────
VERSUS_DB_VARIANT: str = "versus"   # valor de la columna `variant`

# ── FLAGS COMPATIBILIDAD (evita KeyError en core que lee estas vars) ─────────
MOTOGP_MODE             = False
MOTOGP_LITE_PARTICLES   = False
MOTOGP_GIFT_COUNTRY_MAP: dict = {}

# Alias para que core/physics_world.py no reviente:
# RACE_COUNTRIES es consumido por physics_world → sustituimos con los 2 equipos
RACE_COUNTRIES = [TEAM_LEFT["name"], TEAM_RIGHT["name"]]

# COUNTRY_ABBREV también se usa en el render
COUNTRY_ABBREV = {
    TEAM_LEFT["name"]:  TEAM_LEFT["short"],
    TEAM_RIGHT["name"]: TEAM_RIGHT["short"],
}

# Colores para el render de los equipos (reutiliza GIFT_COLORS del core)
from core.config import GIFT_COLORS as _BASE_COLORS
GIFT_COLORS = {
    **_BASE_COLORS,
    TEAM_LEFT["name"]:  TEAM_LEFT["color"],
    TEAM_RIGHT["name"]: TEAM_RIGHT["color"],
}

# ── AUDIO ────────────────────────────────────────────────────────────────────
HYPE_TIMER_ENABLED = False   # Sin catástrofes en el duelo

# ── RETRO LED SCOREBOARD & AMBIENT (versus UI) ───────────────────────────────
# Scoreboard fonts: DOTMATRI.TTF (primary) under assets/versus/fonts/; DSEG7 fallback optional.
VERSUS_SCORE_PULSE_DURATION_SEC: float = 0.38
VERSUS_SCOREBOARD_CORNER_RADIUS: int = 10
# Bokeh / data-stream overlay over the split field (disabled — cleaner Tablero-style look).
VERSUS_AMBIENT_ENABLED: bool = False
# Confetti-style sparks on mapped gifts (disabled for versus clarity).
VERSUS_GIFT_SPARK_PARTICLES: bool = False
VERSUS_AMBIENT_BOKEH_COUNT: int = 36
VERSUS_AMBIENT_BOKEH_ALPHA_MAX: int = 48
VERSUS_AMBIENT_STREAM_COUNT: int = 14
VERSUS_AMBIENT_STREAM_ALPHA: int = 28
VERSUS_DATA_STREAM_SPEED_PX_S: float = 24.0
VERSUS_PUCK_GROUND_GLOW_ALPHA: int = 42

# ── TIRO LIBRE (evento de likes) ─────────────────────────────────────────────
LIKES_PER_FREE_KICK: int = 2000        # likes acumulados para disparar Tiro Libre
FREE_KICK_BALL_COUNT: int = 20         # pelotas en la lluvia
FREE_KICK_BALL_SPEED_MIN: float = 180.0  # px/s mínimo vertical
FREE_KICK_BALL_SPEED_MAX: float = 320.0  # px/s máximo vertical
FREE_KICK_BALL_RADIUS: int = 14        # radio del círculo de cada pelota