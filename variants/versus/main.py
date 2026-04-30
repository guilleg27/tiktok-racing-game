#!/usr/bin/env python3
"""
TikTok Live Interactive Bot - Versus variant entry point (1v1 Boca vs River)

Usage:
    python variants/versus/main.py @username
    python variants/versus/main.py --idle
"""

# Ensure project root is on sys.path when invoked directly from a subdirectory.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
del _sys, _Path

# ── PATCH: inyectar config de Versus en core.config ANTES de cualquier import ──
# Python cachea módulos en sys.modules. Patchear el módulo vivo aquí garantiza
# que todos los `from core.config import X` en core/ capturen los valores Versus.
import core.config as _c
import variants.versus.config as _vc
for _k, _v in vars(_vc).items():
    if not _k.startswith('_'):
        setattr(_c, _k, _v)
del _c, _vc, _k, _v

import asyncio
import logging
import signal
import sys
import traceback
import os
import time
import ssl
import uuid
import certifi
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.config import FPS
from core.events import EventType, GameEvent, ConnectionState
from core.tiktok_manager import TikTokManager
from core.database import Database
from core.resources import is_frozen
from core.event_buffer import HumanizedEventBuffer
from core.telemetry import TelemetryManager

# Importar el engine versus (debe ir DESPUÉS del patch de config)
from variants.versus.game_engine import VersusGameEngine

# SSL
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context

# ── Logging ──────────────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    log_file = os.path.join(os.path.dirname(sys.executable), 'versus.log')
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()
        ]
    )
else:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

logging.getLogger("httpx").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


def _log_uncaught(exc_type, exc_value, exc_tb):
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Uncaught exception: %s", exc_value)
    logger.critical("Traceback:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    sys.stderr.flush()
    sys.stdout.flush()
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _log_uncaught


def _save_crash_report(error: Exception, traceback_str: str) -> str:
    try:
        crash_dir = Path(os.path.dirname(sys.executable)) if (
            getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS')
        ) else Path(__file__).resolve().parents[2]
        crash_file = crash_dir / "crash_report_versus.log"
        with open(crash_file, 'a', encoding='utf-8') as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"CRASH REPORT VERSUS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n")
            f.write(f"Error: {type(error).__name__}: {error}\n")
            f.write(f"\nTraceback:\n{traceback_str}\n")
            f.write("="*80 + "\n\n")
        logger.critical(f"💥 Crash report guardado en: {crash_file}")
        return str(crash_file)
    except Exception as e:
        logger.error(f"Failed to save crash report: {e}")
        return ""


class VersusApplication:
    """Controlador principal del modo Versus."""

    def __init__(self, username: str, idle_mode: bool = False):
        self.username    = username.lstrip("@") if username else ""
        self.idle_mode   = idle_mode
        self._raw_queue: asyncio.Queue[GameEvent] = asyncio.Queue()
        self.queue:      asyncio.Queue[GameEvent] = asyncio.Queue()
        self._event_buffer: Optional[HumanizedEventBuffer] = None

        self.database:       Optional[Database]          = None
        self.tiktok_manager: Optional[TikTokManager]     = None
        self.game_engine:    Optional[VersusGameEngine]  = None

        self._session_id    = str(uuid.uuid4())
        self._telemetry:    Optional[TelemetryManager]   = None
        self._shutdown_event = asyncio.Event()
        self._connect_requested = False

    def setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            if sys.platform != 'win32':
                for sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.add_signal_handler(
                            sig, lambda: asyncio.create_task(self._signal_shutdown())
                        )
                    except (NotImplementedError, ValueError):
                        pass
        except (NotImplementedError, RuntimeError) as e:
            logger.warning(f"Could not setup signal handlers: {e}")

    async def _signal_shutdown(self) -> None:
        logger.info("Shutdown signal received")
        self._shutdown_event.set()
        if self.game_engine:
            self.game_engine.running = False

    def request_connect(self, username: str) -> None:
        if not self.tiktok_manager:
            self.username = username.lstrip("@")
            self._connect_requested = True
            logger.info(f"🔗 Conexión solicitada a @{self.username}")

    async def _try_connect(self) -> None:
        if self._connect_requested and not self.tiktok_manager:
            self._connect_requested = False
            try:
                self.tiktok_manager = TikTokManager(self._raw_queue, self.username)
                self.game_engine.streamer_name = self.username
                await self.tiktok_manager.start()
                logger.info(f"✅ Conectado a @{self.username}")
            except Exception as e:
                logger.error(f"❌ Error conectando: {e}")
                self.tiktok_manager = None

    async def run(self) -> None:
        logger.info(
            f"⚽ Versus Mode — Boca vs River | "
            f"{'IDLE' if self.idle_mode else '@' + self.username}"
        )
        try:
            self.database = Database()
            await self.database.connect()

            self.game_engine = VersusGameEngine(
                self.queue,
                self.username or "idle",
                database=self.database,
            )
            self.game_engine.app = self

            self._event_buffer = HumanizedEventBuffer(
                raw_queue=self._raw_queue,
                output_queue=self.queue,
            )
            self._event_buffer.start()

            self._telemetry = TelemetryManager(
                game_engine=self.game_engine,
                event_buffer=self._event_buffer,
                cloud_manager=self.game_engine.cloud_manager,
                session_id=self._session_id,
            )
            self._telemetry.start()

            self.setup_signal_handlers()
            self.game_engine.init_pygame()

            if not self.idle_mode and self.username:
                logger.info(f"Conectando a TikTok para @{self.username}...")
                self.tiktok_manager = TikTokManager(self._raw_queue, self.username)
                await self.tiktok_manager.start()
                logger.info("Conectado a TikTok")
            else:
                logger.info("✅ Modo IDLE. Q=River, W=Boca, L=Conectar, ESC=Salir")

            await self._game_loop()

        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            tb = traceback.format_exc()
            logger.critical(f"💥 Fatal error: {e}")
            crash_file = _save_crash_report(e, tb)
            raise
        finally:
            try:
                await self._cleanup()
            except Exception as ce:
                logger.error(f"Cleanup error: {ce}")

    async def _frame_sleep(self, target_dt: float, frame_start: float) -> None:
        elapsed = time.perf_counter() - frame_start
        remaining = target_dt - elapsed
        if remaining > 0.001:
            await asyncio.sleep(remaining)

    async def _game_loop(self) -> None:
        target_dt = 1.0 / FPS
        consecutive_errors = 0
        max_consecutive_errors = 10
        last_time = time.perf_counter()

        # Versus: no autopilot (config AUTOPILOT_ENABLED=False; no chaos task).

        while self.game_engine.running and not self._shutdown_event.is_set():
            await asyncio.sleep(0)
            frame_start = time.perf_counter()
            dt = frame_start - last_time
            last_time = frame_start
            if dt <= 0 or dt > 0.5:
                dt = target_dt
            dt = min(dt, target_dt * 2)

            try:
                self.game_engine.handle_pygame_events()
                await self._try_connect()
                await self.game_engine.process_events()
                self.game_engine.update(dt)
                self.game_engine.render()
                consecutive_errors = 0
            except KeyboardInterrupt:
                self.game_engine.running = False
                break
            except Exception as e:
                consecutive_errors += 1
                logger.exception("Game loop error: %s", e)
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical("Demasiados errores consecutivos — cerrando")
                    self.game_engine.running = False
                    break
                if any(kw in str(e).lower() for kw in ("pygame", "surface", "display")):
                    logger.critical("Error crítico pygame — cerrando")
                    self.game_engine.running = False
                    break

            await self._frame_sleep(target_dt, frame_start)

    async def _cleanup(self) -> None:
        logger.info("Limpiando recursos...")
        if self._telemetry:
            self._telemetry.stop()
        if self.tiktok_manager:
            await self.tiktok_manager.stop()
        if self._event_buffer:
            await self._event_buffer.stop()
        if self.database:
            await self.database.close()
        if self.game_engine and self.game_engine._autopilot_task:
            self.game_engine._autopilot_task.cancel()
            try:
                await self.game_engine._autopilot_task
            except asyncio.CancelledError:
                pass
        if self.game_engine:
            self.game_engine.cleanup()
        logger.info("Limpieza completa")


def get_username() -> tuple[str, bool]:
    if len(sys.argv) > 1 and sys.argv[1] in ("--idle", "-i"):
        return ("", True)
    if len(sys.argv) > 1:
        return (sys.argv[1], False)

    if is_frozen():
        try:
            import tkinter as tk
            from tkinter import simpledialog
            root = tk.Tk()
            root.withdraw()
            root.attributes('-topmost', True)
            username = simpledialog.askstring(
                "Versus — Boca vs River",
                "Ingresa el username de TikTok (sin @):\n\nDeja vacío para modo IDLE (Q=River, W=Boca)",
                parent=root
            )
            root.destroy()
            if username and username.strip():
                return (username.strip().lstrip("@"), False)
            return ("", True)
        except Exception as e:
            logger.warning(f"No GUI dialog: {e}")
            return ("", True)

    print("\n╔══════════════════════════════════════════╗")
    print("║  ⚽  Versus — Boca vs River  ⚽           ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Controles demo (sin TikTok):")
    print("  Q   → Gift a River (Rosquilla)")
    print("  W   → Gift a Boca  (Capibara)")
    print("  L   → Conectar a TikTok")
    print("  R   → Reset a IDLE")
    print("  ESC → Salir\n")

    try:
        username = input("Username de TikTok (Enter para modo IDLE): ").strip()
        if not username or username.lower() == "idle":
            return ("", True)
        return (username, False)
    except (EOFError, OSError):
        return ("", True)


def main() -> None:
    try:
        username, idle_mode = get_username()
        app = VersusApplication(username, idle_mode)
        try:
            asyncio.run(app.run())
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            logger.critical(f"💥 Fatal error in main: {e}")
            logger.critical(traceback.format_exc())
            sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()