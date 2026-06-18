#!/usr/bin/env python3
"""
Fulbito — Gameplay simulator.

Arranca el engine sin conexion a TikTok e inyecta eventos sinteticos
(comentarios, gifts, likes, shares, subscribes, follows) para simular
varios partidos consecutivos activando todas las funcionalidades.

Uso:
    python variants/fulbito/test_gameplay.py
    python variants/fulbito/test_gameplay.py --races 3 --speed 2.0
    python variants/fulbito/test_gameplay.py --slow           # ~1 min por race
    python variants/fulbito/test_gameplay.py --slow --duration 90

Flags:
    --races N      Cantidad de partidos a simular (default: 2)
    --speed X      Multiplicador de velocidad de gifts (default: 1.0)
    --seed N       Semilla del RNG para reproducibilidad
    --slow         Preset de carrera lenta (~60s): gifts pequeños con baja frecuencia
    --duration N   Duracion maxima de la fase de race en segundos (default: 25, slow: 120)
"""

import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
del _sys, _Path

import core.config as _c
import variants.fulbito.config as _fc
for _k, _v in vars(_fc).items():
    if not _k.startswith('_'):
        setattr(_c, _k, _v)
del _c, _fc, _k, _v

import argparse
import asyncio
import logging
import random
import sys
import time
import uuid

from core.config import FPS
from core.events import EventType, GameEvent
from core.database import Database

from variants.fulbito.game_engine import FulbitoGameEngine
from variants.fulbito.config import (
    FULBITO_ALL_COUNTRIES,
    FULBITO_COUNTRY_NAMES,
    FULBITO_CHAT_ALIASES,
    FULBITO_RACE_COUNTRY_COUNT,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger("fulbito.test")


# ──────────────────────────────────────────────────────────────────────────────
# Catalogo de gifts simulados — diamantes representativos
# ──────────────────────────────────────────────────────────────────────────────

GIFT_CATALOG = [
    ("Rosa",          1),    # tier 0 — ring only
    ("Perfume",       5),    # tier 0
    ("Hand Heart",    1),    # tier 0
    ("Heart Me",      1),    # quiereme
    ("Quiéreme",      1),    # quiereme
    ("Mic",          10),    # tier 1 fire
    ("Doughnut",     30),    # tier 1
    ("TikTok",       50),    # tier 2 fire
    ("Hat and Mustache", 99),  # tier 2
    ("Rosa Roja",   100),    # tier 2
    ("Galaxy",      200),    # tier 3 fire intenso
    ("Diamond",     500),    # tier 4 + burst blanco
    ("Universe",   1000),    # tier 4 maximo
]

# Pool de usernames simulados
USERNAMES = [
    "carlos_arg", "maria_mex", "pedro_bra", "lucia_col", "andres_uru",
    "diego_ecu", "sofia_par", "miguel_esp", "anna_fra", "tom_eng",
    "yuki_jap", "fan_cro", "user_pai", "club_member_01", "vip_donor",
    "anon123", "viewer_xyz", "amigo42", "chico_uy", "chica_mx",
]


# ──────────────────────────────────────────────────────────────────────────────
# Simulador de eventos
# ──────────────────────────────────────────────────────────────────────────────

class GameplaySimulator:
    """Inyecta eventos sinteticos en la cola del engine para simular un live."""

    def __init__(
        self,
        engine: FulbitoGameEngine,
        queue: asyncio.Queue,
        races: int,
        speed: float,
        rng: random.Random,
        slow: bool = False,
        duration: float | None = None,
    ):
        self.engine = engine
        self.queue = queue
        self.races = races
        self.speed = speed
        self.rng = rng
        self.slow = slow
        # Duration: explicit arg wins; if --slow and no explicit arg → 120s; default 25s
        self.max_race_duration = duration if duration is not None else (120.0 if slow else 25.0)
        self._race_count = 0

    # ── Helpers de inyeccion ──────────────────────────────────────────────────

    def _put(self, event: GameEvent) -> None:
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.warning("Queue llena, descartando evento %s", event.type.name)

    def _vote(self, country_code: str, username: str | None = None) -> None:
        """Vota por un pais usando un alias del chat (simula un comentario)."""
        aliases = [a for a, c in FULBITO_CHAT_ALIASES.items() if c == country_code]
        text = self.rng.choice(aliases) if aliases else country_code
        self._put(GameEvent(
            type=EventType.COMMENT,
            username=username or self.rng.choice(USERNAMES),
            content=text,
        ))

    def _gift(self, country_code: str, gift_name: str, diamonds: int) -> None:
        """Envia un gift atribuido a un pais. El engine asigna el pais al
        username, que ya esta unido al equipo via comentario previo."""
        self._put(GameEvent(
            type=EventType.GIFT,
            username=f"fan_{country_code.lower()}_{self.rng.randint(1, 999)}",
            content=gift_name,
            extra={'diamond_count': diamonds, 'count': 1},
        ))

    def _like(self, count: int = 5) -> None:
        self._put(GameEvent(
            type=EventType.LIKE,
            username=self.rng.choice(USERNAMES),
            extra={'count': count},
        ))

    def _share(self) -> None:
        self._put(GameEvent(
            type=EventType.SHARE,
            username=self.rng.choice(USERNAMES),
        ))

    def _subscribe(self) -> None:
        self._put(GameEvent(
            type=EventType.SUBSCRIBE,
            username=self.rng.choice(USERNAMES),
        ))

    def _follow(self) -> None:
        self._put(GameEvent(
            type=EventType.FOLLOW,
            username=self.rng.choice(USERNAMES),
        ))

    # ── Espera por estado ─────────────────────────────────────────────────────

    async def _wait_for_state(self, target: str, timeout: float = 30.0) -> bool:
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            if self.engine.game_state == target:
                return True
            await asyncio.sleep(0.1)
        logger.warning("Timeout esperando estado %s (actual=%s)",
                       target, self.engine.game_state)
        return False

    # ── Fases ─────────────────────────────────────────────────────────────────

    async def _phase_fixture_setup(self) -> None:
        """Salta el sorteo confirmando el fixture inmediatamente."""
        logger.info("[FASE 1] Confirmando fixture inicial...")
        await asyncio.sleep(2.0)
        if self.engine.game_state == 'FIXTURE_SETUP':
            self.engine._confirm_fixture()
            logger.info("Fixture confirmado: %s", self.engine.current_fixture)
        await asyncio.sleep(1.0)

    async def _phase_start_race(self) -> None:
        """Trigger explicito del race si el engine quedo en IDLE."""
        logger.info("[FASE 2] Arrancando race...")
        if self.engine.game_state == 'IDLE':
            self.engine._transition_to_race_running()
        await asyncio.sleep(0.5)

    async def _phase_race_running(self) -> None:
        """Inyecta una mezcla de gifts, comentarios, likes, shares y subs
        durante el race. Ejercita combat, momentum, fire tiers y club bonus."""
        self._race_count += 1
        fixture = list(self.engine.current_fixture)
        logger.info("[FASE 3] Race #%d arrancando con fixture=%s",
                    self._race_count, fixture)

        # 1. Inyectar comentarios iniciales para que viewers se unan a los equipos
        logger.info("  → Inyectando comentarios de chat para unir viewers a equipos")
        for _ in range(15):
            country = self.rng.choice(fixture)
            self._vote(country)
            await asyncio.sleep(0.05 / self.speed)

        await asyncio.sleep(0.5 / self.speed)

        # 2. Engagement events (share, subscribe, follow)
        logger.info("  → Engagement: shares, subscribes, follows")
        self._share()
        self._subscribe()
        self._follow()
        await asyncio.sleep(0.5 / self.speed)

        # 3. Burst de likes
        logger.info("  → Burst de likes")
        for _ in range(5):
            self._like(count=self.rng.randint(3, 15))
            await asyncio.sleep(0.1 / self.speed)

        # 4. Gifts en cascada — fase principal del race
        logger.info("  → Cascada de gifts (mixto de tiers)")
        gift_count = 0
        race_start = time.monotonic()
        max_race_duration = 25.0  # safety stop

        while (
            self.engine.game_state == 'RACE_RUNNING'
            and time.monotonic() - race_start < max_race_duration
        ):
            country = self.rng.choice(fixture)

            # Distribucion: 60% small, 25% medium, 12% big, 3% mega
            roll = self.rng.random()
            if roll < 0.60:
                gift_name, diamonds = self.rng.choice(GIFT_CATALOG[:5])
            elif roll < 0.85:
                gift_name, diamonds = self.rng.choice(GIFT_CATALOG[5:8])
            elif roll < 0.97:
                gift_name, diamonds = self.rng.choice(GIFT_CATALOG[8:11])
            else:
                gift_name, diamonds = self.rng.choice(GIFT_CATALOG[11:])
                logger.info("    MEGA GIFT %s (%d💎) → %s",
                            gift_name, diamonds, country)

            self._gift(country, gift_name, diamonds)
            gift_count += 1

            # Cada 20 gifts, inyectar un comentario adicional para mantener chat vivo
            if gift_count % 20 == 0:
                self._vote(self.rng.choice(fixture))

            # Likes ocasionales mezclados
            if self.rng.random() < 0.15:
                self._like(count=self.rng.randint(5, 25))

            await asyncio.sleep(self.rng.uniform(0.1, 0.4) / self.speed)

        elapsed = time.monotonic() - race_start
        logger.info("  → Race terminada (gifts enviados=%d, duracion=%.1fs)",
                    gift_count, elapsed)

    async def _phase_finished(self) -> None:
        """Espera la pantalla de victoria."""
        logger.info("[FASE 4] Victory screen...")
        await self._wait_for_state('RACE_FINISHED', timeout=10.0)
        # La pantalla dura ~7s antes de pasar a INTERMISSION
        await asyncio.sleep(6.0)

    async def _phase_intermission(self) -> None:
        """Vota durante el intermission para alimentar el proximo fixture."""
        logger.info("[FASE 5] Intermission — viewers votando proximo fixture...")
        await self._wait_for_state('RACE_INTERMISSION', timeout=10.0)

        # Lluvia de votos para el proximo fixture
        for _ in range(40):
            country = self.rng.choice(FULBITO_ALL_COUNTRIES)
            username = f"voter_{self.rng.randint(1, 99)}"
            self._vote(country, username=username)
            await asyncio.sleep(0.1 / self.speed)

        # Esperar al siguiente race
        await self._wait_for_state('RACE_RUNNING', timeout=20.0)

    # ── Loop principal ────────────────────────────────────────────────────────

    async def run(self) -> None:
        try:
            await self._phase_fixture_setup()
            await self._phase_start_race()

            for race_idx in range(self.races):
                await self._phase_race_running()
                await self._phase_finished()

                if race_idx < self.races - 1:
                    await self._phase_intermission()

            logger.info("[FIN] Simulacion completa (%d races). El juego "
                        "queda corriendo — cerra con ESC.", self.races)

        except asyncio.CancelledError:
            logger.info("Simulator cancelado")
            raise
        except Exception:
            logger.exception("Error en simulator")


# ──────────────────────────────────────────────────────────────────────────────
# Bootstrap minimo del engine (similar a FulbitoApplication pero sin TikTok)
# ──────────────────────────────────────────────────────────────────────────────

class TestApp:
    def __init__(self, races: int, speed: float, rng: random.Random):
        self.races = races
        self.speed = speed
        self.rng = rng
        self.queue: asyncio.Queue[GameEvent] = asyncio.Queue()
        self.database: Database | None = None
        self.game_engine: FulbitoGameEngine | None = None
        self._shutdown = asyncio.Event()
        self._session_id = str(uuid.uuid4())

    async def run(self) -> None:
        logger.info("⚽ Fulbito Gameplay Simulator — %d races, speed=%.1fx",
                    self.races, self.speed)

        self.database = Database()
        await self.database.connect()

        self.game_engine = FulbitoGameEngine(
            self.queue,
            streamer_name="simulator",
            database=self.database,
        )
        self.game_engine.app = self
        self.game_engine.init_pygame()

        # Lanzar el simulador en paralelo
        sim = GameplaySimulator(
            self.game_engine, self.queue, self.races, self.speed, self.rng
        )
        sim_task = asyncio.create_task(sim.run())

        try:
            await self._game_loop()
        finally:
            sim_task.cancel()
            try:
                await sim_task
            except asyncio.CancelledError:
                pass
            await self._cleanup()

    async def _game_loop(self) -> None:
        target_dt = 1.0 / FPS
        last = time.perf_counter()
        while self.game_engine.running and not self._shutdown.is_set():
            await asyncio.sleep(0)
            frame_start = time.perf_counter()
            dt = frame_start - last
            last = frame_start
            if dt <= 0 or dt > 0.5:
                dt = target_dt
            dt = min(dt, target_dt * 2)

            try:
                self.game_engine.handle_pygame_events()
                await self.game_engine.process_events()
                self.game_engine.update(dt)
                self.game_engine.render()
            except Exception:
                logger.exception("Frame error")
                break

            elapsed = time.perf_counter() - frame_start
            remaining = target_dt - elapsed
            if remaining > 0.001:
                await asyncio.sleep(remaining)

    async def _cleanup(self) -> None:
        logger.info("Cleanup...")
        if self.game_engine:
            self.game_engine.cleanup()
        if self.database:
            await self.database.close()


# ──────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Fulbito gameplay simulator")
    parser.add_argument("--races", type=int, default=2,
                        help="cantidad de races a simular")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="multiplicador de velocidad de gifts")
    parser.add_argument("--seed", type=int, default=None,
                        help="semilla del RNG (default: aleatorio)")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else random.randint(0, 999999)
    logger.info("seed=%d", seed)
    rng = random.Random(seed)

    app = TestApp(races=args.races, speed=args.speed, rng=rng)
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        logger.info("Interrumpido por usuario")
    except Exception:
        logger.exception("Error fatal")
        sys.exit(1)


if __name__ == "__main__":
    main()
