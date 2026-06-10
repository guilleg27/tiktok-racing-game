# variants/fulbito/config.py
# Variante: Fulbito — Mundial 2026
# Patrón: override selectivo sobre core/config.py
# Imports en main.py: from core.config import *; from variants.fulbito.config import *

from core.config import *  # noqa: F401, F403  — hereda todo lo de core
import re
import pygame  # noqa: E402

# ─────────────────────────────────────────────
# IDENTIDAD DE LA VARIANTE
# ─────────────────────────────────────────────

VARIANT_NAME = "fulbito"
VARIANT_DISPLAY_NAME = "Fulbito — Mundial 2026"

# ─────────────────────────────────────────────
# RENDIMIENTO
# ─────────────────────────────────────────────

FPS = 30                          # igual que motos — headroom para Live Studio

VOL_BGM = 0.0
VOL_SFX = 0.0
VOL_VOTE = 0.0
VOL_COMBO = 0.0
VOL_FINAL_STRETCH = 0.0
VOL_VICTORY = 0.0

# ─────────────────────────────────────────────
# PAÍSES — POOL COMPLETO (22)
# ─────────────────────────────────────────────
# Orden: LATAM → Europa → Norte América
# Clave: código ISO-2 en mayúsculas (usado como ID interno, key de assets, y Supabase)

FULBITO_ALL_COUNTRIES = [
    # LATAM (9)
    "ARG", "BRA", "MEX", "COL", "URU",
    "ECU", "PAR", "PAN", "GUA",
    # Europa (7)
    "ENG", "FRA", "CRO", "POR", "ALE", "HOL", "ESP",
    # Norte América (2)
    "USA", "CAN",
]

# Nombres para display en pantalla y Supabase
FULBITO_COUNTRY_NAMES = {
    "ARG": "Argentina",
    "BRA": "Brasil",
    "MEX": "México",
    "COL": "Colombia",
    "URU": "Uruguay",
    "ECU": "Ecuador",
    "PAR": "Paraguay",
    "PAN": "Panamá",
    "GUA": "Guatemala",
    "ENG": "Inglaterra",
    "FRA": "Francia",
    "CRO": "Croacia",
    "POR": "Portugal",
    "ALE": "Alemania",
    "HOL": "Países Bajos",
    "ESP": "España",
    "USA": "USA",
    "CAN": "Canadá",
}

# Aliases de chat → código ISO
# El viewer escribe cualquiera de estas variantes y se mapea al país correcto.
# Keys en minúsculas — el engine normaliza con .lower().strip() antes de lookup.
FULBITO_CHAT_ALIASES: dict[str, str] = {
    # ARG
    "arg": "ARG", "argentina": "ARG", "argen": "ARG", "argentin": "ARG",
    # BRA
    "bra": "BRA", "brasil": "BRA", "brazil": "BRA", "braz": "BRA",
    # MEX
    "mex": "MEX", "mexico": "MEX", "méxico": "MEX",
    # COL
    "col": "COL", "colombia": "COL", "colom": "COL",
    # URU
    "uru": "URU", "uruguay": "URU",
    # ECU
    "ecu": "ECU", "ecuador": "ECU",
    # PAR
    "par": "PAR", "paraguay": "PAR",
    # PAN
    "pan": "PAN", "panama": "PAN", "panamá": "PAN",
    # GUA
    "gua": "GUA", "guatemala": "GUA", "guate": "GUA",
    # ENG
    "eng": "ENG", "england": "ENG", "inglaterra": "ENG", "ing": "ENG",
    # FRA
    "fra": "FRA", "france": "FRA", "francia": "FRA",
    # CRO
    "cro": "CRO", "croatia": "CRO", "croacia": "CRO",
    # POR
    "por": "POR", "portugal": "POR",
    # ALE
    "ale": "ALE", "germany": "ALE", "alemania": "ALE", "ger": "ALE",
    # HOL
    "hol": "HOL", "holanda": "HOL", "netherlands": "HOL",
    "paises bajos": "HOL", "países bajos": "HOL", "ned": "HOL",
    # ESP
    "esp": "ESP", "spain": "ESP", "españa": "ESP", "espana": "ESP",
    # USA
    "usa": "USA", "estados unidos": "USA", "eeuu": "USA",
    # CAN
    "can": "CAN", "canada": "CAN", "canadá": "CAN",
}

# ─────────────────────────────────────────────
# FIXTURE — SELECCIÓN POR CARRERA
# ─────────────────────────────────────────────

# Máximo de países activos por carrera (4 carriles)
FULBITO_RACE_COUNTRY_COUNT = 4

# Máximo de países en el pool activo del stream (el streamer lo configura antes de arrancar)
FULBITO_POOL_MAX = 18  # igual que el total — puede usar todos

# Fixture por defecto si el streamer no configura nada (los 4 más populares de LATAM)
FULBITO_DEFAULT_FIXTURE: list[str] = ["ARG", "BRA", "MEX", "COL"]

# ─────────────────────────────────────────────
# SISTEMA DE SELECCIÓN HÍBRIDA
# ─────────────────────────────────────────────

# King: el ganador de la carrera anterior se queda automáticamente
FULBITO_KING_STAYS = True

# Crowd: cantidad de países elegidos por voto del chat (excluyendo al King)
FULBITO_CROWD_PICKS = 2

# Wildcard: 1 país aleatorio del pool (o manual via tecla W)
FULBITO_WILDCARD_COUNT = 1

# Tecla para forzar nuevo wildcard manualmente durante la intermission
FULBITO_WILDCARD_KEY = pygame.K_w  # noqa: F405

FULBITO_INTERMISSION_SECONDS = 15   # countdown entre carreras

# Ventana de votación Crowd: los viewers votan durante RACE_INTERMISSION
# Los 2 países con más votos únicos de viewers entran a la siguiente carrera
FULBITO_VOTE_WINDOW_SECONDS = FULBITO_INTERMISSION_SECONDS

# ─────────────────────────────────────────────
# SALA DE ESPERA — RACE_INTERMISSION
# ─────────────────────────────────────────────

FULBITO_INTERMISSION_KEY = pygame.K_RETURN  # noqa: F405  — skip manual

# ─────────────────────────────────────────────
# FÍSICA — CARRILES ALTERNADOS
# ─────────────────────────────────────────────

# Dirección por índice de carril (0-indexed, de arriba hacia abajo)
# True  = izquierda → derecha (dirección "normal")
# False = derecha → izquierda (dirección "invertida")
FULBITO_LANE_DIRECTIONS: dict[int, bool] = {
    0: True,   # carril 0: →
    1: False,  # carril 1: ←
    2: True,   # carril 2: →
    3: False,  # carril 3: ←
}

# Meta: el corredor gana cuando cruza este umbral de progreso (0.0 a 1.0)
# 1.0 = llegó al extremo opuesto del carril
FULBITO_WIN_THRESHOLD = 0.95

# La carrera termina en el instante en que el primer corredor llega a la meta
FULBITO_SUDDEN_DEATH = True

# Posición inicial de cada corredor según la dirección de su carril
# True (→): empieza en x = FULBITO_START_MARGIN (izquierda)
# False (←): empieza en x = WIDTH - FULBITO_START_MARGIN (derecha)
FULBITO_START_MARGIN = 20           # px desde el borde

# ─────────────────────────────────────────────
# FÍSICA — PARÁMETROS DE MOVIMIENTO
# ─────────────────────────────────────────────

# Fuerza base por diamante (heredada de core, override si hace falta)
# GIFT_BASE_FORCE = 120  ← mantener el de core por ahora

# Los gifts no tienen país asignado — van al equipo que va último
FULBITO_GIFT_TO_LAST = True

# Un viewer no puede cambiar de equipo una vez asignado
FULBITO_LOCK_TEAM_MID_RACE = True

# Impulso por voto de comentario (escalado por COMMENT_DISTANCE_MULTIPLIER de core)
# 1 comentario con país válido = 1 voto → impulso al corredor de ese país
FULBITO_COMMENT_GIVES_IMPULSE = True

# Distancia por diamante (px) — calibrado para track de 242px
# Rosa (1💎) = 2px (floor), Galaxia (1000💎) = 150px
FULBITO_DISTANCE_PER_DIAMOND: float = 0.15

# Distancia mínima por gift sin importar el valor
FULBITO_MIN_GIFT_DISTANCE: float = 2.0

# Multiplicador de distancia para comentarios válidos
# Con distance_per_diamond=0.15, un comentario = 1 * 0.15 = muy poco
# Subimos a 1.0 para que sea equivalente a 1 diamante (2px por floor)
COMMENT_DISTANCE_MULTIPLIER = 1.0   # override del core (era 0.33)
GAME_MODE = "GIFT"

# ─────────────────────────────────────────────
# ASSETS
# ─────────────────────────────────────────────

# Rutas de banderas por código ISO. El engine usa asset_manager.get_sprite_for_racer(code).
# Los assets existentes se reutilizan; los pendientes se agregan a la misma carpeta.
FULBITO_FLAG_PATH = "variants/fulbito/assets/flags/"

# Tamaño de la bandera en pantalla (px). Más grande que motos (12) porque son banderas, no sprites complejos.
FLAG_RADIUS = 28   # radio del círculo de bandera

# Todos los 18 assets están listos:
FULBITO_ASSETS_READY = [
    "ARG", "BRA", "MEX", "COL", "URU", "ECU", "PAR", "PAN", "GUA",  # LATAM
    "ENG", "FRA", "CRO", "POR", "ALE", "HOL", "ESP",                  # Europa
    "USA", "CAN",                                                       # Norte América
]

FULBITO_ASSETS_PENDING: list[str] = []

# ─────────────────────────────────────────────
# SUPABASE — TORNEO ACUMULATIVO
# ─────────────────────────────────────────────

# Identificador de variante en la tabla match_results
FULBITO_SUPABASE_VARIANT = "fulbito"

# Schema de match_results (referencia — la tabla ya existe en Supabase):
# session_id TEXT, date TIMESTAMP, team_a TEXT, team_b TEXT,
# team_c TEXT, team_d TEXT, winner TEXT, duration_secs INT, variant TEXT
# Nota: 4 equipos por carrera (a diferencia de las variantes 1v1)

# ─────────────────────────────────────────────
# HUD Y UI
# ─────────────────────────────────────────────

# Etiquetas personalizadas para el HUD
HYPE_TIMER_LABEL = "TIEMPO RESTANTE"
HYPE_DISASTER_TITLE = "¡ÚLTIMA VUELTA! MAX CAOS"

# Banner de intermission
FULBITO_INTERMISSION_TITLE = "PRÓXIMA CARRERA"
FULBITO_INTERMISSION_SUBTITLE = "¡Votá tu país en el chat!"

# Banner de victoria
FULBITO_VICTORY_LABEL = "¡GANÓ"          # se concatena: "¡GANÓ [País]!"

# ─────────────────────────────────────────────
# VALIDACIÓN DE FIXTURE EN RUNTIME
# ─────────────────────────────────────────────

def validate_fixture(countries: list[str]) -> list[str]:
    """
    Valida y normaliza un fixture antes de arrancar una carrera.
    - Acepta entre 2 y FULBITO_RACE_COUNTRY_COUNT países.
    - Todos deben estar en FULBITO_ALL_COUNTRIES.
    - Retorna la lista validada o lanza ValueError con mensaje descriptivo.
    """
    if not (2 <= len(countries) <= FULBITO_RACE_COUNTRY_COUNT):
        raise ValueError(
            f"Fixture inválido: se esperan 2-{FULBITO_RACE_COUNTRY_COUNT} países, "
            f"recibidos {len(countries)}: {countries}"
        )
    invalid = [c for c in countries if c not in FULBITO_ALL_COUNTRIES]
    if invalid:
        raise ValueError(
            f"Países no reconocidos en el fixture: {invalid}. "
            f"Pool válido: {FULBITO_ALL_COUNTRIES}"
        )
    return countries


def resolve_alias(text: str) -> str | None:
    """
    Busca un alias de país dentro del texto del chat.
    Primero intenta match exacto, luego busca dentro del texto.
    Retorna el código ISO o None si no hay match.

    Ejemplos que deben funcionar:
      "méxico 🇲🇽🇲🇽" → "MEX"
      "soy de mexico" → "MEX"
      "apoyo a méxico" → "MEX"
      "usa" → "USA"
      "vamos arg!!" → "ARG"
    """
    if not text:
        return None

    clean = text.lower().strip()

    # 1. Match exacto primero (más confiable)
    if clean in FULBITO_CHAT_ALIASES:
        return FULBITO_CHAT_ALIASES[clean]

    # 2. Buscar alias dentro del texto
    # Ordenar por longitud descendente para matchear primero
    # los aliases más largos (evita que "per" matchee "peru")
    for alias, code in sorted(
        FULBITO_CHAT_ALIASES.items(),
        key=lambda x: len(x[0]),
        reverse=True,
    ):
        _SUBSTRING_WHITELIST = {
            "usa", "arg", "bra", "mex", "gua", "pan",
            "uru", "ecu", "fra", "ale", "hol",
            "esp", "cro", "can", "eng",
        }
        if len(alias) < 4 and alias not in _SUBSTRING_WHITELIST:
            continue
        if re.search(r'\b' + re.escape(alias) + r'\b', clean):
            return code

    return None


if __name__ == '__main__':
    tests = [
        ("méxico 🇲🇽🇲🇽🇲🇽🇲🇽", "MEX"),
        ("soy de mexico", "MEX"),
        ("apoyo a méxico", "MEX"),
        ("usa", "USA"),
        ("vamos arg!!", "ARG"),
        ("argentina campeon", "ARG"),
        ("como estas", None),
        ("mecico", None),
        ("ok", None),
    ]
    ok = True
    for text, expected in tests:
        result = resolve_alias(text)
        status = "OK" if result == expected else "FAIL"
        if status == "FAIL":
            ok = False
        print(f"{status}: '{text}' → {result} (esperado: {expected})")
    print("Todos OK" if ok else "Hay fallos")