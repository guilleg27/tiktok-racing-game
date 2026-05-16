#!/usr/bin/env python3
"""
TikTok Live Interactive Bot - Motos variant entry point

Usage:
    python variants/motos/main.py @username
    python variants/motos/main.py --idle
"""

# Ensure project root is on sys.path when invoked directly from a subdirectory.
import sys as _sys
from pathlib import Path as _Path
_sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
del _sys, _Path

# Patch motos variant config into core.config BEFORE any core.game_engine import.
# Python caches modules in sys.modules — patching the live module object here
# ensures all subsequent `from .config import NAME` bindings in core/ capture
# the motos values (e.g. MOTOGP_MODE=True).
import core.config as _c
import variants.motos.config as _vc
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

# Project root is three levels up from this file (variants/motos/main.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

from src.config import FPS
from core.events import EventType, GameEvent, ConnectionState
from core.tiktok_manager import TikTokManager
from variants.motos.game_engine import MotosGameEngine as GameEngine
from src.database import Database
from src.resources import is_frozen
from src.event_buffer import HumanizedEventBuffer
from src.telemetry import TelemetryManager

# Configurar certificados SSL para el ejecutable
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context

# ── Logging: show only connection, assets, and gift events ──────────────────
class _MotoFilter(logging.Filter):
    _OWN   = {"__main__", "variants.motos.main", "variants.motos.game_engine"}
    _GIFTS = ("REGALO", "🎁", "🚀", "WINNER", "🏆")
    _CONN  = ("Connected", "Conectad", "Reconnect", "Disconnect",
              "conexión", "Conexión", "timeout", "Timeout")

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno >= logging.WARNING:
            return True
        if record.name in self._OWN:
            return True
        if record.name == "core.tiktok_manager":
            return any(kw in record.getMessage() for kw in self._CONN)
        if record.name == "core.asset_manager":
            return True
        if record.name in ("core.game_engine", "core.physics_world"):
            return any(kw in record.getMessage() for kw in self._GIFTS)
        return False


def _setup_logging() -> None:
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        log_file = os.path.join(os.path.dirname(sys.executable), 'motorace.log')
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(logging.Formatter(fmt))
        file_handler.addFilter(_MotoFilter())
        logging.root.addHandler(file_handler)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(fmt))
    stream_handler.addFilter(_MotoFilter())
    logging.root.addHandler(stream_handler)
    logging.root.setLevel(logging.DEBUG)  # filter decides, not level
    logging.getLogger("httpx").setLevel(logging.WARNING)


_setup_logging()

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
        if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
            crash_dir = Path(os.path.dirname(sys.executable))
        else:
            crash_dir = _PROJECT_ROOT

        crash_file = crash_dir / "crash_report.log"

        with open(crash_file, 'a', encoding='utf-8') as f:
            f.write("\n" + "="*80 + "\n")
            f.write(f"CRASH REPORT - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("="*80 + "\n")
            f.write(f"Error: {type(error).__name__}: {error}\n")
            f.write(f"\nTraceback:\n{traceback_str}\n")
            f.write("="*80 + "\n\n")

        logger.critical(f"💥 Crash report saved to: {crash_file}")
        return str(crash_file)
    except Exception as e:
        logger.error(f"Failed to save crash report: {e}")
        return ""


def _show_error_dialog(error: Exception, crash_file: str = "") -> None:
    error_msg = f"An error occurred:\n\n{type(error).__name__}: {error}"
    if crash_file:
        error_msg += f"\n\nCrash report saved to:\n{crash_file}"

    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        root.attributes('-topmost', True)
        messagebox.showerror("Application Error", error_msg)
        root.destroy()
        return
    except Exception:
        pass

    try:
        import pygame
        pygame.init()
        screen = pygame.display.set_mode((600, 300))
        pygame.display.set_caption("Application Error")
        font = pygame.font.Font(None, 24)
        clock = pygame.time.Clock()
        lines = error_msg.split('\n')
        y_offset = 20
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT or (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE):
                    running = False
            screen.fill((40, 20, 20))
            for i, line in enumerate(lines[:10]):
                text_surface = font.render(line[:60], True, (255, 200, 200))
                screen.blit(text_surface, (20, y_offset + i * 25))
            pygame.display.flip()
            clock.tick(30)
        pygame.quit()
        return
    except Exception:
        pass

    print(f"\n{'='*80}", file=sys.stderr)
    print("APPLICATION ERROR", file=sys.stderr)
    print(f"{'='*80}", file=sys.stderr)
    print(error_msg, file=sys.stderr)
    print(f"{'='*80}\n", file=sys.stderr)


class Application:
    """Main application controller."""

    def __init__(self, username: str, idle_mode: bool = False):
        self.username = username.lstrip("@") if username else ""
        self.idle_mode = idle_mode
        self._raw_queue: asyncio.Queue[GameEvent] = asyncio.Queue()
        self.queue:      asyncio.Queue[GameEvent] = asyncio.Queue()
        self._event_buffer: Optional[HumanizedEventBuffer] = None

        self.database: Optional[Database] = None
        self.tiktok_manager: Optional[TikTokManager] = None
        self.game_engine: Optional[GameEngine] = None

        self._session_id: str = str(uuid.uuid4())
        self._telemetry: Optional[TelemetryManager] = None
        self._shutdown_event = asyncio.Event()
        self._connect_requested = False

    def setup_signal_handlers(self) -> None:
        try:
            loop = asyncio.get_running_loop()
            if sys.platform != 'win32':
                for sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.add_signal_handler(
                            sig,
                            lambda: asyncio.create_task(self._signal_shutdown())
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
        if self.idle_mode:
            logger.info("🎮 Starting in IDLE mode - Press L to connect")
        else:
            logger.info(f"Starting Moto Race for @{self.username}")

        try:
            logger.info("Initializing database...")
            self.database = Database()
            await self.database.connect()
            logger.info("Database initialized")

            logger.info("Initializing game engine...")
            self.game_engine = GameEngine(
                self.queue,
                self.username or "idle",
                database=self.database
            )
            logger.info("Game engine created")

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

            logger.info("Setting up signal handlers...")
            self.setup_signal_handlers()

            logger.info("Initializing pygame...")
            try:
                self.game_engine.init_pygame()
                logger.info("Pygame initialized successfully")
            except Exception as e:
                logger.critical(f"Failed to initialize pygame: {e}")
                logger.critical(traceback.format_exc())
                raise

            if not self.idle_mode and self.username:
                logger.info(f"Connecting to TikTok for @{self.username}...")
                self.tiktok_manager = TikTokManager(self._raw_queue, self.username)
                await self.tiktok_manager.start()
                logger.info("Connected to TikTok")
            else:
                logger.info("✅ Ventana lista. L=Conectar, T=Test, C=Limpiar, ESC=Salir")

            logger.info("Starting game loop...")
            await self._game_loop()
            logger.info("Game loop ended")

        except KeyboardInterrupt:
            logger.info("Application interrupted by user")
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.critical(f"💥 Fatal application error: {e}")
            logger.critical(f"Traceback:\n{error_traceback}")
            crash_file = _save_crash_report(e, error_traceback)
            _show_error_dialog(e, crash_file)
            raise
        finally:
            logger.info("Cleaning up...")
            try:
                await self._cleanup()
            except Exception as cleanup_error:
                logger.error(f"Error during cleanup: {cleanup_error}")
            logger.info("Cleanup complete")

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

        self.game_engine.start_autopilot()

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
                logger.info("Game loop interrupted by user")
                self.game_engine.running = False
                break
            except Exception as e:
                consecutive_errors += 1
                error_traceback = traceback.format_exc()
                logger.exception("Error in game loop iteration: %s", e)
                if consecutive_errors >= max_consecutive_errors:
                    logger.critical(f"Fatal: {max_consecutive_errors} consecutive errors - shutting down")
                    crash_file = _save_crash_report(e, error_traceback)
                    _show_error_dialog(e, crash_file)
                    self.game_engine.running = False
                    break
                if "pygame" in str(e).lower() or "surface" in str(e).lower() or "display" in str(e).lower():
                    logger.critical("Critical pygame/display error - shutting down")
                    crash_file = _save_crash_report(e, error_traceback)
                    _show_error_dialog(e, crash_file)
                    self.game_engine.running = False
                    break

            await self._frame_sleep(target_dt, frame_start)

    async def _cleanup(self) -> None:
        logger.info("Cleaning up...")
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
        logger.info("Cleanup complete")


def get_username() -> tuple[str, bool]:
    if len(sys.argv) > 1 and sys.argv[1] in ("--idle", "-i"):
        return ("", True)

    if len(sys.argv) > 1:
        return (sys.argv[1], False)

    if is_frozen():
        try:
            try:
                import tkinter as tk
                from tkinter import simpledialog
                root = tk.Tk()
                root.withdraw()
                root.attributes('-topmost', True)
                username = simpledialog.askstring(
                    "Moto Race",
                    "Ingresa el username de TikTok (sin @):\n\nDeja vacío para modo IDLE",
                    parent=root
                )
                root.destroy()
                if username and username.strip():
                    username = username.strip().lstrip("@")
                    logger.info(f"Username from dialog: {username}")
                    return (username, False)
                else:
                    logger.info("No username provided - starting in IDLE mode")
                    return ("", True)
            except ImportError:
                logger.info("tkinter not available, trying pygame dialog...")
                try:
                    import pygame
                    pygame.init()
                    pygame.display.init()
                    screen = pygame.display.set_mode((400, 200))
                    pygame.display.set_caption("Moto Race")
                    font = pygame.font.Font(None, 32)
                    clock = pygame.time.Clock()
                    input_text = ""
                    prompt = "Username (Enter for IDLE):"
                    done = False
                    while not done:
                        for event in pygame.event.get():
                            if event.type == pygame.QUIT:
                                done = True
                                input_text = ""
                            elif event.type == pygame.KEYDOWN:
                                if event.key == pygame.K_RETURN:
                                    done = True
                                elif event.key == pygame.K_BACKSPACE:
                                    input_text = input_text[:-1]
                                else:
                                    input_text += event.unicode
                        screen.fill((30, 30, 40))
                        text_surface = font.render(prompt, True, (255, 255, 255))
                        screen.blit(text_surface, (20, 20))
                        input_surface = font.render(input_text, True, (255, 255, 255))
                        screen.blit(input_surface, (20, 80))
                        pygame.display.flip()
                        clock.tick(30)
                    pygame.quit()
                    if input_text and input_text.strip():
                        username = input_text.strip().lstrip("@")
                        logger.info(f"Username from pygame dialog: {username}")
                        return (username, False)
                    else:
                        logger.info("No username provided - starting in IDLE mode")
                        return ("", True)
                except Exception as e2:
                    logger.warning(f"Could not show pygame dialog ({e2}) - defaulting to IDLE mode")
                    return ("", True)
        except Exception as e:
            logger.warning(f"Could not show GUI dialog ({e}) - defaulting to IDLE mode")
            return ("", True)

    print("\n╔═══════════════════════════════════════════╗")
    print("║   Moto Race Live                          ║")
    print("╚═══════════════════════════════════════════╝\n")

    try:
        username = input("Username (o Enter para modo IDLE): ").strip()
        if not username or username.lower() == "idle":
            return ("", True)
        return (username, False)
    except (EOFError, OSError, RuntimeError) as e:
        logger.warning(f"Could not read from stdin ({e}) - defaulting to IDLE mode")
        return ("", True)


def main() -> None:
    try:
        username, idle_mode = get_username()
        logger.info(f"Starting application - username: {username or 'idle'}, idle_mode: {idle_mode}")

        try:
            if sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False:
                print("\nControles:")
                print("  L   - Conectar a TikTok")
                print("  T   - Regalo pequeño | Y - Regalo grande")
                print("  1/2/3 - Rosa/Pesa/Helado (GIFT mode)")
                print("  V   - Test Victoria | ESC - Salir")
                print()
        except (OSError, AttributeError, RuntimeError):
            logger.info("Running in windowed mode - check log file for details")

        app = Application(username, idle_mode)
        logger.info("Application initialized, starting main loop")

        try:
            asyncio.run(app.run())
            logger.info("Application exited normally")
        except KeyboardInterrupt:
            logger.info("Interrupted by user")
        except Exception as e:
            error_traceback = traceback.format_exc()
            logger.critical(f"💥 Fatal error in main: {e}")
            logger.critical(f"Traceback:\n{error_traceback}")
            crash_file = _save_crash_report(e, error_traceback)
            _show_error_dialog(e, crash_file)
            sys.exit(1)

    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        try:
            if sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False:
                print("\n¡Hasta luego!")
        except (OSError, AttributeError, RuntimeError):
            pass
    except Exception as e:
        error_msg = f"Fatal error: {e}"
        logger.critical(error_msg)
        logger.critical("Traceback:\n%s", traceback.format_exc())
        if is_frozen():
            log_file = os.path.join(os.path.dirname(sys.executable), 'motorace.log')
            logger.critical(f"Log file location: {log_file}")
        sys.exit(1)


if __name__ == "__main__":
    main()
