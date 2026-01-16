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
import os
import ssl
import certifi

from typing import Optional

from src.config import FPS
from src.events import EventType, GameEvent, ConnectionState
from src.tiktok_manager import TikTokManager
from src.game_engine import GameEngine
from src.database import Database

# Configurar certificados SSL para el ejecutable
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()
ssl._create_default_https_context = ssl._create_unverified_context

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


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
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(
                sig,
                lambda: asyncio.create_task(self._signal_shutdown())
            )
    
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
        if self.idle_mode:
            logger.info("🎮 Starting in IDLE mode - Press L to connect")
        else:
            logger.info(f"Starting TikTok Live Bot for @{self.username}")
        
        try:
            self.database = Database()
            await self.database.connect()
            
            self.game_engine = GameEngine(
                self.queue, 
                self.username or "idle",
                database=self.database
            )
            
            # Pasar referencia de la app al game engine para poder conectar
            self.game_engine.app = self
            
            self.setup_signal_handlers()
            self.game_engine.init_pygame()
            
            if not self.idle_mode and self.username:
                self.tiktok_manager = TikTokManager(self.queue, self.username)
                await self.tiktok_manager.start()
            else:
                logger.info("✅ Ventana lista. L=Conectar, T=Test, C=Limpiar, ESC=Salir")
            
            await self._game_loop()
            
        except Exception as e:
            logger.error(f"Application error: {e}")
            raise
        finally:
            await self._cleanup()
    
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
    if len(sys.argv) > 1 and sys.argv[1] in ("--idle", "-i"):
        return ("", True)
    
    if len(sys.argv) > 1:
        return (sys.argv[1], False)
    
    print("\n╔═══════════════════════════════════════════╗")
    print("║   TikTok Live Interactive - MVP           ║")
    print("╚═══════════════════════════════════════════╝\n")
    
    username = input("Username (o Enter para modo IDLE): ").strip()
    
    if not username or username.lower() == "idle":
        return ("", True)
    
    return (username, False)


def main() -> None:
    username, idle_mode = get_username()
    
    print("\nControles:")
    print("  L   - Conectar a TikTok (ingresa username)")
    print("  T   - Spawn regalo de prueba")
    print("  J   - Test usuario uniéndose a equipo")  # ← NUEVO
    print("  C   - Limpiar/Reset")
    print("  ESC - Salir")
    print()
    
    app = Application(username, idle_mode)
    
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        print("\n¡Hasta luego!")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()


def resource_path(relative_path):
    """Obtiene la ruta absoluta al recurso, compatible con PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)