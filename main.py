#!/usr/bin/env python3
"""
TikTok Live Interactive Bot - MVP with Physics

Usage:
    python main.py @username
    python main.py --idle          # Modo IDLE (ventana abierta, conectar después con L)
"""

import asyncio
import logging
import signal
import sys
import traceback
import os
import ssl
import certifi

from typing import Optional

from src.config import FPS
from src.events import EventType, GameEvent, ConnectionState
from src.tiktok_manager import TikTokManager
from src.game_engine import GameEngine
from src.database import Database
from src.resources import is_frozen

# Configurar certificados SSL para el ejecutable
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context

# Configure logging - write to file if frozen (windowed executable)
if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
    # Executable mode: log to file
    log_file = os.path.join(os.path.dirname(sys.executable), 'tiktok_live_bot.log')
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding='utf-8'),
            logging.StreamHandler()  # Also try to log to stderr if available
        ]
    )
else:
    # Development mode: log to console
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

logger = logging.getLogger(__name__)


def _log_uncaught(exc_type, exc_value, exc_tb):
    """Log any uncaught exception (e.g. from pygame callbacks) then reraise."""
    if exc_type is KeyboardInterrupt:
        sys.__excepthook__(exc_type, exc_value, exc_tb)
        return
    logger.critical("Uncaught exception: %s", exc_value)
    logger.critical("Traceback:\n%s", "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
    sys.stderr.flush()
    sys.stdout.flush()
    sys.__excepthook__(exc_type, exc_value, exc_tb)


sys.excepthook = _log_uncaught


class Application:
    """Main application controller."""
    
    def __init__(self, username: str, idle_mode: bool = False):
        self.username = username.lstrip("@") if username else ""
        self.idle_mode = idle_mode
        self.queue: asyncio.Queue[GameEvent] = asyncio.Queue()
        
        self.database: Optional[Database] = None
        self.tiktok_manager: Optional[TikTokManager] = None
        self.game_engine: Optional[GameEngine] = None
        
        self._shutdown_event = asyncio.Event()
        self._connect_requested = False  # Flag para conectar durante ejecución
    
    def setup_signal_handlers(self) -> None:
        """Setup signal handlers for graceful shutdown. Windows-compatible."""
        try:
            loop = asyncio.get_running_loop()
            # Only setup signal handlers on Unix systems (Windows uses different signals)
            if sys.platform != 'win32':
                for sig in (signal.SIGINT, signal.SIGTERM):
                    try:
                        loop.add_signal_handler(
                            sig,
                            lambda: asyncio.create_task(self._signal_shutdown())
                        )
                    except (NotImplementedError, ValueError):
                        # Signal handlers not supported on this platform
                        pass
        except (NotImplementedError, RuntimeError) as e:
            logger.warning(f"Could not setup signal handlers: {e}")
    
    async def _signal_shutdown(self) -> None:
        logger.info("Shutdown signal received")
        self._shutdown_event.set()
        if self.game_engine:
            self.game_engine.running = False
    
    def request_connect(self, username: str) -> None:
        """Solicitar conexión a TikTok (llamado desde game loop)."""
        if not self.tiktok_manager:
            self.username = username.lstrip("@")
            self._connect_requested = True
            logger.info(f"🔗 Conexión solicitada a @{self.username}")
    
    async def _try_connect(self) -> None:
        """Intentar conectar a TikTok si fue solicitado."""
        if self._connect_requested and not self.tiktok_manager:
            self._connect_requested = False
            try:
                self.tiktok_manager = TikTokManager(self.queue, self.username)
                self.game_engine.streamer_name = self.username
                await self.tiktok_manager.start()
                logger.info(f"✅ Conectado a @{self.username}")
            except Exception as e:
                logger.error(f"❌ Error conectando: {e}")
                self.tiktok_manager = None
    
    async def run(self) -> None:
        """Main application run loop with comprehensive error handling."""
        if self.idle_mode:
            logger.info("🎮 Starting in IDLE mode - Press L to connect")
        else:
            logger.info(f"Starting TikTok Live Bot for @{self.username}")
        
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
            
            # Pasar referencia de la app al game engine para poder conectar
            self.game_engine.app = self
            
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
                self.tiktok_manager = TikTokManager(self.queue, self.username)
                await self.tiktok_manager.start()
                logger.info("Connected to TikTok")
            else:
                logger.info("✅ Ventana lista. L=Conectar, T=Test, C=Limpiar, ESC=Salir")
            
            logger.info("Starting game loop...")
            await self._game_loop()
            logger.info("Game loop ended")
            
        except Exception as e:
            logger.critical(f"Application error: {e}")
            logger.critical(f"Traceback:\n{traceback.format_exc()}")
            raise
        finally:
            logger.info("Cleaning up...")
            await self._cleanup()
            logger.info("Cleanup complete")
    
    async def _game_loop(self) -> None:
        dt = 1.0 / FPS
        
        while self.game_engine.running and not self._shutdown_event.is_set():
            self.game_engine.handle_pygame_events()
            
            # Intentar conectar si fue solicitado
            await self._try_connect()
            
            await self.game_engine.process_events()
            self.game_engine.update(dt)
            self.game_engine.render()
            await asyncio.sleep(dt)
    
    async def _cleanup(self) -> None:
        logger.info("Cleaning up...")
        if self.tiktok_manager:
            await self.tiktok_manager.stop()
        if self.database:
            await self.database.close()
        if self.game_engine:
            self.game_engine.cleanup()
        logger.info("Cleanup complete")


def get_username() -> tuple[str, bool]:
    """Get username from command line arguments or prompt user.
    
    If running as windowed executable (no console), defaults to IDLE mode
    when no arguments are provided.
    
    Returns:
        tuple[str, bool]: (username, idle_mode)
    """
    if len(sys.argv) > 1 and sys.argv[1] in ("--idle", "-i"):
        return ("", True)
    
    if len(sys.argv) > 1:
        return (sys.argv[1], False)
    
    # If frozen (executable), default to IDLE mode (no console available)
    if is_frozen():
        logger.info("Running as windowed executable - starting in IDLE mode")
        logger.info("Use --idle or @username as command line argument, or press L in-game to connect")
        return ("", True)
    
    # Interactive mode: prompt user (only in development)
    print("\n╔═══════════════════════════════════════════╗")
    print("║   TikTok Live Interactive - MVP           ║")
    print("╚═══════════════════════════════════════════╝\n")
    
    try:
        username = input("Username (o Enter para modo IDLE): ").strip()
        
        if not username or username.lower() == "idle":
            return ("", True)
        
        return (username, False)
    except (EOFError, OSError, RuntimeError) as e:
        # Fallback if stdin becomes unavailable
        logger.warning(f"Could not read from stdin ({e}) - defaulting to IDLE mode")
        return ("", True)


def main() -> None:
    """Main entry point. Handles initialization and error reporting."""
    try:
        username, idle_mode = get_username()
        logger.info(f"Starting application - username: {username or 'idle'}, idle_mode: {idle_mode}")
        
        # Only print to console if stdin is available (not windowed)
        try:
            if sys.stdin.isatty() if hasattr(sys.stdin, 'isatty') else False:
                print("\nControles:")
                print("  L   - Conectar a TikTok (ingresa username)")
                print("  T   - Regalo pequeño | Y - Regalo grande")
                print("  1/2/3 - Votos (COMMENT) o Rosa/Pesa/Helado (GIFT)")
                print("  J   - Test usuario uniéndose | K - Test capitanes")
                print("  F   - Test combo ON FIRE | G - Test Final Stretch | V - Test Victoria")
                print("  C/R - Reset carrera | ESC - Salir")
                print("\n  Ver TESTING_BEFORE_LIVE.md para probar sin ir LIVE")
                print()
        except (OSError, AttributeError, RuntimeError):
            # Windowed mode - logs will go to file if configured
            logger.info("Running in windowed mode - check log file for details")
        
        app = Application(username, idle_mode)
        logger.info("Application initialized, starting main loop")
        
        asyncio.run(app.run())
        logger.info("Application exited normally")
        
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
        
        # Log file location for user reference
        if is_frozen():
            log_file = os.path.join(os.path.dirname(sys.executable), 'tiktok_live_bot.log')
            logger.critical(f"Log file location: {log_file}")
        
        sys.exit(1)


if __name__ == "__main__":
    main()