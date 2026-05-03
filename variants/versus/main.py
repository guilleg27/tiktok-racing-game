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

    def __init__(self, username: str, idle_mode: bool = False, matchup=None):
        self.username    = username.lstrip("@") if username else ""
        self.idle_mode   = idle_mode
        self.matchup     = matchup  # Matchup instance selected at startup
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
                matchup=self.matchup,
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


# ─────────────────────────────────────────────────────────────────────────────
# Pygame-native startup dialog (no tkinter / Tcl-Tk dependency)
# ─────────────────────────────────────────────────────────────────────────────

def _show_pygame_startup_dialog(prefill_username: str, matchups: list) -> dict:
    """Render a startup form using pygame directly.

    Args:
        prefill_username: Username to pre-populate the text field.
        matchups: List of Matchup instances to choose from.

    Returns:
        Dict with keys ``username``, ``matchup_label``, and optionally ``idle``.
    """
    import pygame

    pygame.init()
    pygame.display.set_caption("Versus — Selector de Duelo")

    W, H = 460, 320
    screen = pygame.display.set_mode((W, H))
    clock = pygame.time.Clock()

    # ── Colours ──────────────────────────────────────────────────────────────
    BG      = (15, 15, 25)
    PANEL   = (28, 28, 42)
    BORDER  = (70, 70, 110)
    ACCENT  = (80, 160, 255)
    WHITE   = (230, 230, 240)
    GREY    = (140, 140, 160)
    BTN_BG  = (40, 80, 160)
    BTN_HI  = (60, 110, 220)
    BTN_IDL = (50, 50, 70)
    BTN_IDH = (75, 75, 100)
    SEL_BG  = (40, 60, 100)
    TEXT_CL = (200, 200, 215)

    # ── Fonts ─────────────────────────────────────────────────────────────────
    try:
        font_lbl  = pygame.font.SysFont("Arial", 15, bold=True)
        font_inp  = pygame.font.SysFont("Arial", 17)
        font_btn  = pygame.font.SysFont("Arial", 15, bold=True)
        font_title = pygame.font.SysFont("Arial", 19, bold=True)
    except Exception:
        font_lbl = font_inp = font_btn = font_title = pygame.font.Font(None, 20)

    # ── State ─────────────────────────────────────────────────────────────────
    username_text   = prefill_username
    cursor_visible  = True
    cursor_timer    = 0
    selected_idx    = 0
    matchup_labels  = [m.label for m in matchups]

    # Input field rect
    inp_rect = pygame.Rect(30, 110, W - 60, 36)

    # Matchup option rects (one per matchup)
    opt_rects: list[pygame.Rect] = []
    opt_y = 200
    for _ in matchup_labels:
        opt_rects.append(pygame.Rect(30, opt_y, W - 60, 32))
        opt_y += 38

    # Button rects
    btn_connect = pygame.Rect(30,  H - 52, 185, 36)
    btn_idle    = pygame.Rect(W - 215, H - 52, 185, 36)

    input_focused = True
    running = True
    result: dict = {}

    while running:
        dt = clock.tick(60)
        cursor_timer += dt
        if cursor_timer >= 500:
            cursor_visible = not cursor_visible
            cursor_timer = 0

        mx, my = pygame.mouse.get_pos()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                result = {"username": "", "idle": True, "matchup_label": matchup_labels[selected_idx]}
                running = False

            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                input_focused = inp_rect.collidepoint(mx, my)

                for i, r in enumerate(opt_rects):
                    if r.collidepoint(mx, my):
                        selected_idx = i

                if btn_connect.collidepoint(mx, my):
                    result = {
                        "username": username_text.strip().lstrip("@"),
                        "matchup_label": matchup_labels[selected_idx],
                    }
                    running = False

                if btn_idle.collidepoint(mx, my):
                    result = {
                        "username": "",
                        "idle": True,
                        "matchup_label": matchup_labels[selected_idx],
                    }
                    running = False

            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_RETURN:
                    result = {
                        "username": username_text.strip().lstrip("@"),
                        "matchup_label": matchup_labels[selected_idx],
                    }
                    running = False
                elif event.key == pygame.K_ESCAPE:
                    result = {"username": "", "idle": True, "matchup_label": matchup_labels[selected_idx]}
                    running = False
                elif event.key == pygame.K_TAB:
                    # cycle through matchups
                    selected_idx = (selected_idx + 1) % len(matchup_labels)
                elif input_focused:
                    if event.key == pygame.K_BACKSPACE:
                        username_text = username_text[:-1]
                    else:
                        ch = event.unicode
                        if ch and ch.isprintable():
                            username_text += ch

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(BG)

        # Title bar
        pygame.draw.rect(screen, PANEL, (0, 0, W, 52))
        pygame.draw.line(screen, ACCENT, (0, 52), (W, 52), 2)
        title_surf = font_title.render("⚽  Versus — Selector de Duelo", True, WHITE)
        screen.blit(title_surf, (W // 2 - title_surf.get_width() // 2, 14))

        # Username label
        lbl = font_lbl.render("Username de TikTok  (sin @)", True, GREY)
        screen.blit(lbl, (30, 72))

        # Input box
        border_col = ACCENT if input_focused else BORDER
        pygame.draw.rect(screen, PANEL, inp_rect, border_radius=6)
        pygame.draw.rect(screen, border_col, inp_rect, 2, border_radius=6)

        display_text = username_text if username_text else ""
        inp_surf = font_inp.render(display_text, True, WHITE)
        screen.blit(inp_surf, (inp_rect.x + 10, inp_rect.y + 8))

        # Blinking cursor
        if input_focused and cursor_visible:
            cx = inp_rect.x + 10 + inp_surf.get_width() + 2
            cy = inp_rect.y + 7
            pygame.draw.line(screen, WHITE, (cx, cy), (cx, cy + 20), 2)

        # Placeholder text
        if not username_text:
            ph = font_inp.render("ej: miusuario", True, (80, 80, 100))
            screen.blit(ph, (inp_rect.x + 10, inp_rect.y + 8))

        # Matchup label
        lbl2 = font_lbl.render("Seleccionar Duelo:", True, GREY)
        screen.blit(lbl2, (30, 175))

        # Matchup options
        for i, (lbl_text, r) in enumerate(zip(matchup_labels, opt_rects)):
            is_sel = (i == selected_idx)
            is_hov = r.collidepoint(mx, my)
            bg = SEL_BG if is_sel else (PANEL if not is_hov else (35, 50, 75))
            pygame.draw.rect(screen, bg, r, border_radius=5)
            bord = ACCENT if is_sel else BORDER
            pygame.draw.rect(screen, bord, r, 2 if is_sel else 1, border_radius=5)

            # Radio circle
            circ_x = r.x + 16
            circ_y = r.y + r.height // 2
            pygame.draw.circle(screen, bord, (circ_x, circ_y), 7, 2)
            if is_sel:
                pygame.draw.circle(screen, ACCENT, (circ_x, circ_y), 4)

            opt_surf = font_btn.render(lbl_text, True, WHITE if is_sel else TEXT_CL)
            screen.blit(opt_surf, (r.x + 32, r.y + r.height // 2 - opt_surf.get_height() // 2))

        # Buttons
        for btn_r, label, normal, hover in [
            (btn_connect, "Conectar", BTN_BG, BTN_HI),
            (btn_idle,    "Modo IDLE", BTN_IDL, BTN_IDH),
        ]:
            col = hover if btn_r.collidepoint(mx, my) else normal
            pygame.draw.rect(screen, col, btn_r, border_radius=8)
            pygame.draw.rect(screen, ACCENT if col == BTN_HI else BORDER, btn_r, 2, border_radius=8)
            bs = font_btn.render(label, True, WHITE)
            screen.blit(bs, (btn_r.centerx - bs.get_width() // 2,
                              btn_r.centery - bs.get_height() // 2))

        # Hint
        hint = font_lbl.render("Enter = Conectar   |   Esc = IDLE   |   Tab = cambiar duelo", True, (60, 60, 80))
        screen.blit(hint, (W // 2 - hint.get_width() // 2, H - 14))

        pygame.display.flip()

    pygame.display.quit()
    return result


def get_startup_params() -> tuple[str, bool, object]:
    """Prompt for username and matchup selection.

    Returns:
        Tuple of ``(username, idle_mode, matchup)``.
    """
    from variants.versus.matchups import ALL_MATCHUPS, get_matchup, DEFAULT_MATCHUP

    # ── CLI shortcuts ─────────────────────────────────────────────────────────
    args = sys.argv[1:]
    matchup_id: Optional[str] = None
    username_arg: Optional[str] = None
    idle_mode = False

    for arg in args:
        if arg in ("--idle", "-i"):
            idle_mode = True
        elif arg.startswith("--matchup="):
            matchup_id = arg.split("=", 1)[1]
        elif arg.startswith("@") or (not arg.startswith("--")):
            username_arg = arg.lstrip("@")

    matchup = get_matchup(matchup_id) if matchup_id else None

    if idle_mode:
        return ("", True, matchup or DEFAULT_MATCHUP)
    if username_arg and matchup:
        return (username_arg, False, matchup)

    # ── GUI dialog — pygame-native (no tkinter required) ─────────────────────
    if is_frozen() or (not username_arg):
        try:
            result = _show_pygame_startup_dialog(username_arg or "", ALL_MATCHUPS)
            selected_matchup = next(
                (m for m in ALL_MATCHUPS if m.label == result["matchup_label"]),
                DEFAULT_MATCHUP,
            )
            uname = result.get("username", "")
            is_idle = result.get("idle", False) or not uname
            return (uname, is_idle, selected_matchup)
        except Exception as e:
            logger.warning(f"Startup dialog failed: {e}")
            return ("", True, DEFAULT_MATCHUP)

    # ── Terminal fallback ─────────────────────────────────────────────────────
    print("\n╔══════════════════════════════════════════╗")
    print("║  ⚽  Versus — Selector de duelo  ⚽       ║")
    print("╚══════════════════════════════════════════╝\n")
    print("Duelos disponibles:")
    for i, m in enumerate(ALL_MATCHUPS):
        print(f"  {i + 1}. {m.label}  [{m.id}]")
    print()
    try:
        choice = input(f"Elige duelo (1-{len(ALL_MATCHUPS)}, Enter=1): ").strip()
        idx = int(choice) - 1 if choice.isdigit() else 0
        idx = max(0, min(idx, len(ALL_MATCHUPS) - 1))
        selected_matchup = ALL_MATCHUPS[idx]
    except (EOFError, OSError):
        selected_matchup = DEFAULT_MATCHUP

    print(f"\n▶ Duelo: {selected_matchup.label}\n")
    print("Controles demo (sin TikTok):")
    print("  Q   → Gift izquierda (Dona)")
    print("  W   → Gift derecha  (Capibara)")
    print("  E   → Fan comment izquierda")
    print("  R   → Fan comment derecha")
    print("  ESC → Salir\n")

    try:
        uname = input("Username de TikTok (Enter para modo IDLE): ").strip().lstrip("@")
        if not uname or uname.lower() == "idle":
            return ("", True, selected_matchup)
        return (uname, False, selected_matchup)
    except (EOFError, OSError):
        return ("", True, selected_matchup)


# Keep old name as alias so any external callers don't break.
def get_username() -> tuple[str, bool]:
    """Legacy shim — use ``get_startup_params`` for new code."""
    u, idle, _ = get_startup_params()
    return (u, idle)


def main() -> None:
    try:
        username, idle_mode, matchup = get_startup_params()
        app = VersusApplication(username, idle_mode, matchup=matchup)
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