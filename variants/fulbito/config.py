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
    # LATAM (8)
    "ARG", "BRA", "MEX", "COL", "URU",
    "ECU", "PAR", "PAN",
    # Europa (7)
    "ENG", "FRA", "CRO", "POR", "ALE", "PAI", "ESP",
    # Norte América (2)
    "USA", "CAN",
    # Otros (10)
    "AUS", "AUST", "COR", "BEL",
    "CHE", "EGI", "JAP", "MAR", "SUE", "NOR",
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
    "ENG": "Inglaterra",
    "FRA": "Francia",
    "CRO": "Croacia",
    "POR": "Portugal",
    "ALE": "Alemania",
    "PAI": "Países Bajos",
    "ESP": "España",
    "USA": "USA",
    "CAN": "Canadá",
    "AUS": "Australia",
    "AUST": "Austria",
    "COR": "Corea del Sur",
    "BEL": "Bélgica",
    "CHE": "Chequia",
    "EGI": "Egipto",
    "JAP": "Japón",
    "MAR": "Marruecos",
    "SUE": "Suecia",
    "NOR": "Noruega",
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
    # PAI
    "pai": "PAI", "hol": "PAI", "holanda": "PAI", "netherlands": "PAI",
    "paises bajos": "PAI", "países bajos": "PAI", "ned": "PAI",
    # ESP
    "esp": "ESP", "spain": "ESP", "españa": "ESP", "espana": "ESP",
    # USA
    "usa": "USA", "estados unidos": "USA", "eeuu": "USA",
    # CAN
    "can": "CAN", "canada": "CAN", "canadá": "CAN",
    # AUS
    "aus": "AUS", "australia": "AUS",
    # AUST
    "aust": "AUST", "austria": "AUST",
    # COR
    "cor": "COR", "corea": "COR", "korea": "COR", "corea del sur": "COR",
    # BEL
    "bel": "BEL", "belgica": "BEL", "bélgica": "BEL", "belgium": "BEL",
    # CHE
    "che": "CHE", "chequia": "CHE", "czech": "CHE", "republica checa": "CHE", "república checa": "CHE",
    # EGI
    "egi": "EGI", "egipto": "EGI", "egypt": "EGI",
    # JAP
    "jap": "JAP", "japon": "JAP", "japón": "JAP", "japan": "JAP",
    # MAR
    "mar": "MAR", "marruecos": "MAR", "morocco": "MAR",
    # SUE
    "sue": "SUE", "suecia": "SUE", "sweden": "SUE",
    # NOR
    "nor": "NOR", "noruega": "NOR", "norway": "NOR",
}

# ─────────────────────────────────────────────
# FIXTURE — SELECCIÓN POR PARTIDO
# ─────────────────────────────────────────────

# Máximo de países activos por partido (4 carriles)
FULBITO_RACE_COUNTRY_COUNT = 4

# Fixture por defecto si el streamer no configura nada (los 4 más populares de LATAM)
FULBITO_DEFAULT_FIXTURE: list[str] = ["ARG", "BRA", "MEX", "COL"]

# ─────────────────────────────────────────────
# SISTEMA DE SELECCIÓN HÍBRIDA
# ─────────────────────────────────────────────

# Crowd: cantidad de países elegidos por voto del chat (excluyendo al King)
FULBITO_CROWD_PICKS = 2

FULBITO_INTERMISSION_SECONDS = 15   # countdown entre partidos

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

# El partido termina en el instante en que el primer corredor llega a la meta
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

# Distancia por diamante (px) — calibrado para ~1000 diamantes para ganar
# Rosa (1💎) = 2px (floor), TikTok (50💎) = 20px, León (100💎) = 40px, Universo (1000💎) = 400px
FULBITO_DISTANCE_PER_DIAMOND: float = 0.40

# Distancia mínima por gift sin importar el valor
FULBITO_MIN_GIFT_DISTANCE: float = 2.0

# Multiplicador de distancia para comentarios válidos
# Con distance_per_diamond=0.15, un comentario = 1 * 0.15 = muy poco
# Subimos a 1.0 para que sea equivalente a 1 diamante (2px por floor)
COMMENT_DISTANCE_MULTIPLIER = 1.0   # override del core (era 0.33)
GAME_MODE = "GIFT"

# Visual effects threshold: total_diamonds >= this triggers fire trail + crowd flash
FULBITO_BIG_GIFT_THRESHOLD = 20

# ─────────────────────────────────────────────
# ASSETS
# ─────────────────────────────────────────────

FLAG_RADIUS = 18   # radio del círculo de bandera (≈36px diám, cabe en arco de 46px)

# ─────────────────────────────────────────────
# VALIDACIÓN DE FIXTURE EN RUNTIME
# ─────────────────────────────────────────────

def validate_fixture(countries: list[str]) -> list[str]:
    """
    Valida y normaliza un fixture antes de arrancar un partido.
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