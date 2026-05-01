"""
VersusGameEngine — subclase de GameEngine para el modo 1v1.

Sobrescribe exclusivamente la lógica que difiere del core:
  • Sólo 2 equipos (gift_map directo, sin auto-assign)
  • Marcador por puntos y tiempo (un partido; sin series)
  • Tiempo extra + golden goal
  • Pantalla de victoria (top donador + MVP)
  • Sin combos / trails ON FIRE / autopilot (motor liviano)
  • Pantalla partida en dos mitades (River | Boca), banderas fijas al centro de cada mitad
  • Teclas demo Q/W para simular gifts sin TikTok

El render principal y physics lo hereda de core/game_engine.py sin tocar.
"""

import asyncio
import logging
import time
import math
import random
from dataclasses import dataclass
from typing import Optional, List, Any

import pymunk
import pygame

from core.game_engine import GameEngine, _get_font
from core.events import EventType, GameEvent

logger = logging.getLogger(__name__)


@dataclass
class _VersusBokeh:
    """Single soft light speck for the versus ambient overlay."""

    x: float
    y: float
    r: float
    alpha: int
    vx: float
    vy: float


@dataclass
class _VersusStream:
    """Short vertical streak for a subtle \"data stream\" effect."""

    x: float
    y: float
    length: float
    speed: float
    alpha: int


class VersusGameEngine(GameEngine):
    """Modo duelo 1v1 sobre el GameEngine base."""

    # ── Estado versus ────────────────────────────────────────────────────────
    def __init__(self, queue: asyncio.Queue, streamer_name: str, database=None):
        # Importar config versus (ya patched en sys.modules antes de este import)
        from core.config import (
            VICTORY_MODE, SCORE_LIMIT, MATCH_DURATION_SECS,
            EXTRA_TIME_SECS, GOLDEN_GOAL_ENABLED,
            VERSUS_GIFT_TEAM_MAP, VERSUS_GIFT_POINT_VALUE,
            VICTORY_SCREEN_DURATION, SHOW_TOP_DONOR_GLOBAL, SHOW_MVP_WINNER_TEAM,
            TEAM_LEFT, TEAM_RIGHT,
        )

        super().__init__(queue, streamer_name, database=database)

        # Equipos
        self.team_left_name  = TEAM_LEFT["name"]
        self.team_right_name = TEAM_RIGHT["name"]
        self.teams = [self.team_left_name, self.team_right_name]

        # Modos
        self.victory_mode        = VICTORY_MODE          # "score" | "time"
        self.score_limit         = SCORE_LIMIT
        self.match_duration      = MATCH_DURATION_SECS
        self.extra_time_secs     = EXTRA_TIME_SECS
        self.golden_goal_enabled = GOLDEN_GOAL_ENABLED
        self.gift_point_value    = VERSUS_GIFT_POINT_VALUE

        # Gift → equipo
        self.gift_team_map = {k.lower(): v for k, v in VERSUS_GIFT_TEAM_MAP.items()}

        # Pantalla victoria
        self.victory_screen_duration = VICTORY_SCREEN_DURATION
        self.show_top_donor_global   = SHOW_TOP_DONOR_GLOBAL
        self.show_mvp_winner_team    = SHOW_MVP_WINNER_TEAM

        # Score en tiempo real (marcador del partido)
        self.set_score: dict[str, int] = {self.team_left_name: 0, self.team_right_name: 0}

        # Timer de ronda (modo "time")
        self.match_start_time: Optional[float] = None
        self.match_elapsed: float = 0.0
        self.in_extra_time: bool = False
        self.extra_time_start: Optional[float] = None
        self.golden_goal_active: bool = False

        # Victoria versus
        self.versus_winner: Optional[str] = None
        self.versus_victory_time: float = 0.0
        self.versus_victory_active: bool = False

        # Top donador y MVP para pantalla de victoria
        self.victory_top_donor: Optional[str] = None
        self.victory_top_donor_diamonds: int = 0
        self.victory_mvp: Optional[str] = None
        self.victory_mvp_diamonds: int = 0

        # Fixed (cx, lane_y) per team for split layout — regifts do not move flags.
        self._versus_racer_pin: dict[str, tuple[float, float]] = {}

        # Score hit pulse (0..1 per team, decays in update)
        self._score_pulse: dict[str, float] = {
            self.team_left_name: 0.0,
            self.team_right_name: 0.0,
        }
        self._versus_scoreboard: Any = None  # VersusRetroScoreboard, lazy init
        self._versus_anim_time: float = 0.0
        self._versus_last_dt: float = 0.0
        self._versus_ambient_ready: bool = False
        self._versus_bokeh: List[_VersusBokeh] = []
        self._versus_streams: List[_VersusStream] = []

        # Team crest images for the puck: {team_name: pygame.Surface | None}
        self._versus_crests: dict[str, Any] = {}

        # Acumulador de puntos por donador (para MVP y top donador)
        self.donor_points: dict[str, int] = {}          # username → total 💎 global
        self.team_donor_points: dict[str, dict[str, int]] = {  # equipo → {user: pts}
            self.team_left_name: {},
            self.team_right_name: {},
        }

        # Deshabilitar la meta física para que la carrera nunca termine por posición.
        # La victoria se decide únicamente por tiempo (VersusGameEngine.update).
        self.physics_world.finish_line_x = 999999
        self.physics_world.rosa_combo_multiplier = 1.0

        logger.info(
            f"VersusGameEngine iniciado — {self.team_left_name} vs {self.team_right_name} "
            f"| modo={self.victory_mode}"
        )

        self._apply_split_screen_layout()

        # Silence the join-welcome banner — it overlaps the scoreboard.
        self.notification_manager.render = lambda *_args, **_kwargs: None

    # ── Split screen (River | Boca) ─────────────────────────────────────────

    @staticmethod
    def _remove_versus_track_constraints_for_body(pw, body: pymunk.Body) -> None:
        """Remove GrooveJoint and PinJoint constraints attached to ``body``.

        Args:
            pw: Physics world containing ``space`` and racers.
            body: Dynamic body whose track/pin joints should be stripped.
        """
        to_remove: list[pymunk.Constraint] = []
        for j in pw.space.constraints:
            if not isinstance(j, (pymunk.GrooveJoint, pymunk.PinJoint)):
                continue
            if j.b is body or j.a is body:
                to_remove.append(j)
        for j in to_remove:
            pw.space.remove(j)

    def _apply_split_screen_layout(self) -> None:
        """Pin each team flag to the center of its half (River left, Boca right).

        Uses ``PinJoint`` so flags stay fixed for live streams; score changes only
        on the HUD. Re-applies after ``reset_race`` or startup.
        """
        from core.config import SCREEN_WIDTH, RACE_START_X, TEAM_LEFT, TEAM_RIGHT

        pw = self.physics_world
        mid = SCREEN_WIDTH // 2
        gap = 12
        margin = 20
        lane_y = float(pw.game_area_top + pw.game_area_height // 2)

        left_start = float(max(RACE_START_X, margin))
        left_end = float(mid - gap)
        right_start = float(mid + gap)
        right_end = float(SCREEN_WIDTH - margin)

        if left_start >= left_end:
            left_end = left_start + 40.0
        if right_start >= right_end:
            right_end = right_start + 40.0

        bounds = {
            self.team_left_name: (left_start, left_end),
            self.team_right_name: (right_start, right_end),
        }

        self._versus_racer_pin = {}

        for country, racer in pw.racers.items():
            if country not in bounds:
                continue
            x0, x1 = bounds[country]
            cx_fixed = (x0 + x1) * 0.5
            self._remove_versus_track_constraints_for_body(pw, racer.body)
            pin = pymunk.PinJoint(
                pw.space.static_body,
                racer.body,
                (cx_fixed, lane_y),
                (0.0, 0.0),
            )
            pw.space.add(pin)
            racer.body.position = pymunk.Vec2d(cx_fixed, lane_y)
            racer.target_x = cx_fixed
            self._versus_racer_pin[country] = (cx_fixed, lane_y)

        pw.finish_line_x = 999999
        logger.debug(
            "Versus split pins: %s @ %.0f | %s @ %.0f | y=%.0f",
            TEAM_LEFT["name"],
            (left_start + left_end) * 0.5,
            TEAM_RIGHT["name"],
            (right_start + right_end) * 0.5,
            lane_y,
        )

    def _pin_versus_racers_static(self) -> None:
        """Keep versus flags pinned after core physics Lerp (no horizontal drift)."""
        pw = getattr(self, "physics_world", None)
        if pw is None:
            return
        pins = getattr(self, "_versus_racer_pin", None) or {}
        for country, (cx, ly) in pins.items():
            racer = pw.racers.get(country)
            if not racer:
                continue
            if pw.is_country_frozen(country):
                continue
            racer.body.position = pymunk.Vec2d(cx, ly)
            racer.target_x = cx

    def _return_to_idle(self) -> None:
        """Return to IDLE and re-apply split grooves after physics reset."""
        super()._return_to_idle()
        self._apply_split_screen_layout()

    def on_physics_race_reset(self) -> None:
        """Re-apply split layout after a physics-driven race reset (rare in versus)."""
        super().on_physics_race_reset()
        self._apply_split_screen_layout()

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_team_from_gift(self, gift_name: str) -> Optional[str]:
        """Devuelve el equipo mapeado al gift, o None si no está en el mapa."""
        return self.gift_team_map.get(gift_name.strip().lower())

    def _trigger_score_pulse(self, team: str) -> None:
        """Start or refresh the LED score pulse animation for a team."""
        if team in self._score_pulse:
            self._score_pulse[team] = 1.0

    def _register_donor(self, username: str, team: str, diamonds: int) -> None:
        """Acumula puntos de donador globalmente y por equipo."""
        self.donor_points[username] = self.donor_points.get(username, 0) + diamonds
        self.team_donor_points[team][username] = (
            self.team_donor_points[team].get(username, 0) + diamonds
        )

    def _compute_victory_stats(self, winner_team: str) -> None:
        """Calcula top donador global y MVP del equipo ganador."""
        if self.donor_points:
            top_user = max(self.donor_points, key=lambda u: self.donor_points[u])
            self.victory_top_donor          = top_user
            self.victory_top_donor_diamonds = self.donor_points[top_user]

        team_donors = self.team_donor_points.get(winner_team, {})
        if team_donors:
            mvp_user = max(team_donors, key=lambda u: team_donors[u])
            self.victory_mvp          = mvp_user
            self.victory_mvp_diamonds = team_donors[mvp_user]

    # ── Procesamiento de eventos ──────────────────────────────────────────────

    async def _handle_event(self, event: GameEvent) -> None:
        """Override: en GIFT redirige al equipo correcto por gift_map."""
        if event.type == EventType.GIFT:
            gift_name = event.content or ""
            team = self._get_team_from_gift(gift_name)

            if team is None:
                # Regalo no mapeado → ignorar en Versus (no hay auto-assign)
                logger.debug(f"[VERSUS] Regalo ignorado (no mapeado): '{gift_name}'")
                return

            gift_count   = event.extra.get("count", 1) if event.extra else 1
            diamond_count = event.extra.get("diamond_count", 30) if event.extra else 30
            username = self.sanitize_username(event.username)

            # Pasar el evento al engine base con el equipo ya asignado
            # Reemplazamos username para que _get_user_country_with_autojoin
            # devuelva el equipo correcto. En VERSUS_MODE el mapeo es directo.
            patched_extra = dict(event.extra or {})
            patched_extra["_versus_team"] = team

            patched_event = GameEvent(
                type=EventType.GIFT,
                username=event.username,
                content=event.content,
                extra=patched_extra,
                created_at_sec=event.created_at_sec,
            )

            # Acumular donador
            self._register_donor(username, team, diamond_count * gift_count)

            # Incrementar score del set
            points = self.gift_point_value * gift_count
            self.set_score[team] = self.set_score.get(team, 0) + points
            self._trigger_score_pulse(team)

            logger.info(
                f"⚽ VERSUS GIFT: {username} → {team} | {gift_name} x{gift_count} "
                f"| score={self.set_score}"
            )

            # Llamar al handler base (mueve el racer, sonidos, etc.)
            # Forzamos que el handler base use el equipo correcto
            await self._handle_versus_gift_physics(team, gift_name, diamond_count * gift_count, username)

            # ¿Hay ganador del set?
            self._check_set_winner()
            return

        # Todos los demás eventos los maneja el engine base sin cambios
        await super()._handle_event(event)

    async def _handle_versus_gift_physics(
        self,
        team: str,
        gift_name: str,
        total_diamonds: int,
        username: str,
    ) -> None:
        """Gift feedback (audio/SFX) without moving flags — live layout stays fixed."""
        if team not in self.physics_world.racers:
            logger.warning(f"[VERSUS] Equipo '{team}' no encontrado en racers")
            return

        # Arrancar si estaba en IDLE
        if self.game_state == "IDLE":
            self._transition_to_racing()

        self._on_real_activity()
        self._update_captain_points(username, team, total_diamonds)

        self._pin_versus_racers_static()
        racer = self.physics_world.racers[team]
        pos = (float(racer.body.position.x), float(racer.body.position.y))
        was_frozen = self.physics_world.is_country_frozen(team)

        self.audio_manager.play_gift_sound(gift_name=gift_name, diamond_value=total_diamonds)
        if not was_frozen:
            import core.config as _cfg

            is_large = total_diamonds > 50
            if getattr(_cfg, "VERSUS_GIFT_SPARK_PARTICLES", False):
                count = 15 + int(total_diamonds / 8) if is_large else 10 + int(total_diamonds / 10)
                self.emit_explosion(
                    pos=pos,
                    color=(255, 215, 0),
                    count=count,
                    power=1.0 if is_large else 0.7,
                    diamond_count=total_diamonds,
                )
            if total_diamonds >= 100:
                self.screen_shaker.big_impact_shake()
            elif is_large:
                self.screen_shaker.impact_shake()

        # Cloud sync del evento de regalo
        if self.cloud_manager.enabled:
            asyncio.create_task(self.cloud_manager.sync_gift_event(
                session_id=self.session_id,
                username=username,
                country=team,
                gift_name=gift_name,
                diamond_count=total_diamonds,
                gift_count=1,
            ))

    # ── Lógica de victoria del set ────────────────────────────────────────────

    def _check_set_winner(self) -> None:
        """Evalúa si algún equipo ganó el set actual."""
        if self.versus_victory_active:
            return

        winner = None

        if self.victory_mode == "score":
            for team in self.teams:
                if self.set_score.get(team, 0) >= self.score_limit:
                    winner = team
                    break

        # Modo tiempo: lo revisa update()
        if winner:
            self._trigger_set_victory(winner)

    def _trigger_set_victory(self, winner_team: str) -> None:
        """Declara fin del partido y muestra la pantalla de victoria (sin series)."""
        if self.versus_victory_active:
            return
        self._show_match_victory(winner_team)

    def _show_match_victory(self, winner_team: str) -> None:
        """El equipo ganó el partido (único marcador + tiempo o límite de puntos)."""
        self.versus_winner = winner_team
        self.versus_victory_active = True
        self.versus_victory_time = 0.0
        self._compute_victory_stats(winner_team)

        sl = self.set_score.get(self.team_left_name, 0)
        sr = self.set_score.get(self.team_right_name, 0)
        logger.info(
            f"🎉 PARTIDO: ganó {winner_team} | Marcador {sl}-{sr} | "
            f"Top donador: {self.victory_top_donor} ({self.victory_top_donor_diamonds}💎) | "
            f"MVP {winner_team}: {self.victory_mvp} ({self.victory_mvp_diamonds}💎)"
        )

        self.audio_manager.play_victory_sound(winner_country=winner_team)
        self.screen_shaker.big_impact_shake()

        # Cloud sync disabled for versus variant — uncomment to re-enable.
        # if self.cloud_manager.enabled:
        #     asyncio.create_task(self._sync_versus_result(winner_team))

    # ── Override update: timer de partido y tiempo extra ──────────────────────

    def update(self, dt: float) -> None:
        """Override update para gestionar el timer de partido (modo time)."""
        super().update(dt)
        self._pin_versus_racers_static()
        self._versus_anim_time += dt
        self._versus_last_dt = dt
        from core.config import VERSUS_SCORE_PULSE_DURATION_SEC, VERSUS_AMBIENT_ENABLED

        dur = float(VERSUS_SCORE_PULSE_DURATION_SEC) or 0.35
        for tname in list(self._score_pulse.keys()):
            v = self._score_pulse[tname]
            if v > 0.0:
                self._score_pulse[tname] = max(0.0, v - dt / dur)

        if VERSUS_AMBIENT_ENABLED:
            self._update_versus_ambient(dt)

        # No hacer nada si ya hay victoria de partido
        if self.versus_victory_active:
            self.versus_victory_time += dt
            if self.versus_victory_time >= self.victory_screen_duration:
                self._reset_versus()
            return

        if self.game_state != "RACING":
            return

        # ── Modo tiempo ──────────────────────────────────────────────────────
        if self.victory_mode == "time":
            if self.match_start_time is None:
                return  # Todavía no arrancó

            now = time.time()

            if not self.in_extra_time:
                self.match_elapsed = now - self.match_start_time

                if self.match_elapsed >= self.match_duration:
                    # Regular time over
                    self._evaluate_time_winner()
            else:
                # Gol de Oro (sudden death): first team to score wins, no clock
                if self.golden_goal_active:
                    for team in self.teams:
                        if self.set_score.get(team, 0) > self.set_score.get(
                            self._other_team(team), 0
                        ):
                            self._trigger_set_victory(team)
                            return

    def _other_team(self, team: str) -> str:
        return self.team_right_name if team == self.team_left_name else self.team_left_name

    def _evaluate_time_winner(self) -> None:
        """Evaluate who won when regular time expires.

        If there is a clear winner, trigger victory immediately.
        On a tie, activate *Gol de Oro* (golden goal / sudden death):
        the next team to score wins — no extra-time countdown.
        """
        s_left  = self.set_score.get(self.team_left_name, 0)
        s_right = self.set_score.get(self.team_right_name, 0)

        if s_left != s_right:
            winner = self.team_left_name if s_left > s_right else self.team_right_name
            self._trigger_set_victory(winner)
        else:
            # Tie → golden goal (sudden death, no extra-time clock)
            self.in_extra_time   = True
            self.extra_time_start = time.time()
            self.golden_goal_active = True
            logger.info("EMPATE -> GOL DE ORO (muerte súbita)")
            self._add_floating_text("¡GOL DE ORO!", color=(255, 215, 0))

    # ── Sync Supabase ─────────────────────────────────────────────────────────

    async def _sync_versus_result(self, winner_team: str) -> None:
        """Guarda resultado del partido versus en Supabase (opcional)."""
        try:
            await self.cloud_manager.sync_race_result(
                country=winner_team,
                winner_name=self.victory_mvp or "Unknown",
                total_diamonds=self.victory_mvp_diamonds,
                streamer_name=self.streamer_name,
            )
            logger.info(f"☁️ Versus result synced: {winner_team} ganó el partido")
        except Exception as e:
            logger.error(f"❌ Error sync versus result: {e}")

    # ── Reset completo ────────────────────────────────────────────────────────

    def _reset_versus(self) -> None:
        """Reset completo: vuelta a IDLE, marcador a cero."""
        self.set_score    = {self.team_left_name: 0, self.team_right_name: 0}
        self._score_pulse = {self.team_left_name: 0.0, self.team_right_name: 0.0}
        self.match_start_time  = None
        self.match_elapsed     = 0.0
        self.in_extra_time     = False
        self.extra_time_start  = None
        self.golden_goal_active = False
        self.versus_winner      = None
        self.versus_victory_active = False
        self.versus_victory_time   = 0.0
        self.victory_top_donor     = None
        self.victory_top_donor_diamonds = 0
        self.victory_mvp           = None
        self.victory_mvp_diamonds  = 0
        self.donor_points.clear()
        for team in self.teams:
            self.team_donor_points[team].clear()

        self._return_to_idle()
        logger.info("🔄 Versus reseteado — nuevo partido")

    # ── Helpers de texto flotante ─────────────────────────────────────────────

    def _add_floating_text(self, text: str, color=(255, 255, 255)) -> None:
        """Agrega texto flotante al centro de la pantalla."""
        try:
            from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
            cx = SCREEN_WIDTH // 2
            cy = SCREEN_HEIGHT // 2
            self.add_floating_text(text, cx, cy, color=color, font_size=28)
        except Exception as e:
            logger.debug(f"[floating_text] {e}")

    # ── handle_pygame_events: agrega teclas demo Q/W ──────────────────────────

    def handle_pygame_events(self) -> None:
        """Extiende el handler base con teclas demo Q/W para gifts versus."""
        super().handle_pygame_events()

        # Leer eventos pygame de nuevo solo para las teclas que nos interesan
        # NOTA: super() ya drenó la cola, así que procesamos las que lleguen
        # en el mismo frame a través del flag de tecla presionada.
        # → Usamos un enfoque alternativo: hook post-evento con pygame.key.get_pressed()
        keys = pygame.key.get_pressed()

        # Q → gift a River (team_left)
        if keys[pygame.K_q] and not getattr(self, "_q_held", False):
            self._q_held = True
            self._inject_demo_gift(self.team_left_name)
        elif not keys[pygame.K_q]:
            self._q_held = False

        # W → gift a Boca (team_right)
        if keys[pygame.K_w] and not getattr(self, "_w_held", False):
            self._w_held = True
            self._inject_demo_gift(self.team_right_name)
        elif not keys[pygame.K_w]:
            self._w_held = False

    def _inject_demo_gift(self, team: str) -> None:
        """Inyecta un gift de demo para el equipo dado."""
        from core.config import (
            DEMO_GIFT_NAME_LEFT, DEMO_GIFT_NAME_RIGHT,
            TEAM_LEFT,
        )
        gift_name = DEMO_GIFT_NAME_LEFT if team == TEAM_LEFT["name"] else DEMO_GIFT_NAME_RIGHT
        event = GameEvent(
            type=EventType.GIFT,
            username=f"demo_{team.lower()}",
            content=gift_name,
            extra={"diamond_count": 30, "count": 1},
        )
        self.queue.put_nowait(event)
        logger.debug(f"[DEMO] Injected {gift_name} → {team}")

    # ── Overrides: suprimir elementos de UI de carrera ───────────────────────

    def _draw_permanent_cta(self, surface) -> None:
        pass


    def _render_podium_tags(self) -> None:
        pass

    def _render_finish_line(self) -> None:
        pass

    def _render_final_stretch_line(self) -> None:
        pass

    def _render_leaderboard(self) -> None:
        pass

    def _render_likes_bar(self) -> None:
        pass

    def _render_header(self) -> None:
        pass

    def start_autopilot(self) -> None:
        """Versus: autopilot disabled (no chaos loop or asyncio task)."""

    def register_combo_event(self, country: str) -> int:
        """Versus: gift combo / ON FIRE tracking disabled.

        Args:
            country: Team name (ignored).

        Returns:
            Always 0.
        """
        return 0

    def _decay_rosa_combos(self) -> None:
        """Versus: keep Rosa distance multiplier at 1.0 (no streak logic)."""
        self.physics_world.rosa_combo_multiplier = 1.0

    def _update_rosa_combo(self, country: str, now: float) -> None:
        """Versus: Rosa streak multiplier disabled."""

    def _update_combo_flashes(self, dt: float) -> None:
        """Versus: combo milestone flashes disabled."""

    def _update_motion_trails(self, dt: float) -> None:
        """Versus: ON FIRE neon trails disabled."""

    def _render_motion_trails(self) -> None:
        """Versus: skip drawing motion trails."""

    def _render_combo_flashes(self) -> None:
        """Versus: skip drawing combo flash overlays."""

    def _init_versus_ambient_if_needed(self) -> None:
        """Seed bokeh and stream particles once the playfield rect is known."""
        if self._versus_ambient_ready:
            return
        from core.config import SCREEN_WIDTH, VERSUS_AMBIENT_BOKEH_COUNT, VERSUS_AMBIENT_STREAM_COUNT

        pw = self.physics_world
        top = float(pw.game_area_top)
        h = float(pw.game_area_height)
        rnd = random.Random(42)
        self._versus_bokeh = []
        for _ in range(int(VERSUS_AMBIENT_BOKEH_COUNT)):
            self._versus_bokeh.append(
                _VersusBokeh(
                    x=rnd.uniform(0, SCREEN_WIDTH),
                    y=rnd.uniform(top, top + h),
                    r=rnd.uniform(2.0, 9.0),
                    alpha=int(rnd.uniform(18, 55)),
                    vx=rnd.uniform(-4.0, 4.0),
                    vy=rnd.uniform(-10.0, -2.5),
                )
            )
        self._versus_streams = []
        for _ in range(int(VERSUS_AMBIENT_STREAM_COUNT)):
            self._versus_streams.append(
                _VersusStream(
                    x=rnd.uniform(0, SCREEN_WIDTH),
                    y=rnd.uniform(top, top + h),
                    length=rnd.uniform(14.0, 42.0),
                    speed=rnd.uniform(16.0, 38.0),
                    alpha=int(rnd.uniform(12, 32)),
                )
            )
        self._versus_ambient_ready = True

    def _update_versus_ambient(self, dt: float) -> None:
        """Drift bokeh and scroll stream streaks within the versus playfield."""
        from core.config import SCREEN_WIDTH, VERSUS_AMBIENT_ENABLED, VERSUS_DATA_STREAM_SPEED_PX_S

        if not VERSUS_AMBIENT_ENABLED:
            return
        self._init_versus_ambient_if_needed()
        pw = self.physics_world
        top = float(pw.game_area_top)
        h = float(pw.game_area_height)
        bottom = top + h
        stream_factor = max(0.35, float(VERSUS_DATA_STREAM_SPEED_PX_S) / 24.0)
        for b in self._versus_bokeh:
            b.x += b.vx * dt
            b.y += b.vy * dt
            if b.y < top - 12:
                b.y = bottom + random.uniform(0.0, 24.0)
                b.x = random.uniform(0.0, float(SCREEN_WIDTH))
            if b.x < -15 or b.x > SCREEN_WIDTH + 15:
                b.x = random.uniform(0.0, float(SCREEN_WIDTH))
        for s in self._versus_streams:
            s.y += s.speed * dt * stream_factor
            if s.y > bottom + s.length:
                s.y = top - s.length
                s.x = random.uniform(0.0, float(SCREEN_WIDTH))

    def _draw_versus_ambient_layer(self) -> None:
        """Additive bokeh and vertical streaks over the split-field tint."""
        from core.config import (
            VERSUS_AMBIENT_ENABLED,
            VERSUS_AMBIENT_BOKEH_ALPHA_MAX,
        )

        if not VERSUS_AMBIENT_ENABLED:
            return
        try:
            self._init_versus_ambient_if_needed()
            surf = self.render_surface
            cap = int(VERSUS_AMBIENT_BOKEH_ALPHA_MAX)
            for b in self._versus_bokeh:
                sz = max(5, int(b.r * 2) + 4)
                blob = pygame.Surface((sz, sz), pygame.SRCALPHA)
                a = min(cap, max(6, b.alpha))
                pygame.draw.circle(blob, (210, 230, 255, a), (sz // 2, sz // 2), max(2, int(b.r)))
                surf.blit(blob, (int(b.x - sz // 2), int(b.y - sz // 2)), special_flags=pygame.BLEND_RGBA_ADD)
            for s in self._versus_streams:
                hseg = max(4, int(s.length))
                seg = pygame.Surface((2, hseg), pygame.SRCALPHA)
                seg.fill((170, 200, 255, min(55, s.alpha + 10)))
                surf.blit(seg, (int(s.x), int(s.y)), special_flags=pygame.BLEND_RGBA_ADD)
        except Exception as e:
            logger.debug(f"[versus_ambient] {e}")

    def _render_lanes(self) -> None:
        """Draw two vertical halves (River / Boca) with a divider; no horizontal lane grid."""
        try:
            from core.config import SCREEN_WIDTH, TEAM_LEFT, TEAM_RIGHT

            pw = self.physics_world
            top = int(pw.game_area_top)
            h = int(pw.game_area_height)
            mid = SCREEN_WIDTH // 2

            # Deep burgundy / navy tint (Tablero-style); team names live on the LED scoreboard.
            left_panel = pygame.Surface((mid, h), pygame.SRCALPHA)
            left_panel.fill((48, 10, 14, 235))
            self.render_surface.blit(left_panel, (0, top))

            right_w = SCREEN_WIDTH - mid
            right_panel = pygame.Surface((right_w, h), pygame.SRCALPHA)
            right_panel.fill((6, 18, 46, 238))
            self.render_surface.blit(right_panel, (mid, top))

            self._draw_versus_ambient_layer()
            glow = pygame.Surface((SCREEN_WIDTH, h), pygame.SRCALPHA)
            for w, a in ((7, 18), (4, 35), (2, 70)):
                pygame.draw.line(
                    glow,
                    (255, 248, 200, a),
                    (mid, top),
                    (mid, top + h),
                    w,
                )
            self.render_surface.blit(glow, (0, top))
            pygame.draw.line(
                self.render_surface,
                (255, 252, 220),
                (mid, top),
                (mid, top + h),
                2,
            )
        except Exception as e:
            logger.debug(f"[render_lanes versus] {e}")

    def _render_leader_spotlight(self, racer) -> None:
        """Versus: leader spotlight disabled (two independent halves)."""

    def _render_race_start_hud(self, alpha: int) -> None:
        """Versus: hide the GO! / Type-to-vote fade-in overlay."""

    def _render_shortcuts_panel(self) -> None:
        """Versus: hide the 1→RIV / 2→BOC scrolling ticker."""

    def _render_global_ranking_futuristic(self) -> None:
        """Versus: hide world-records / global ranking panel."""

    def _render_idle_screen(self) -> None:
        """Versus: hide the IDLE overlay (dark dim + connect prompt)."""

    def _render_captain_label(self, racer, flag_x: int, flag_y: int) -> None:
        """Captain label hidden in this version (logic kept, rendering skipped)."""
        return
        country = racer.country  # noqa: F401 — unreachable, kept for logic reference
        captain = self.current_captains.get(country, "")
        if not captain:
            return
        label_y = flag_y + 25
        captain_text = f"@{captain}"
        if country in self.captain_change_timer:
            color = (255, 223, 0)
            font_size = 12
        else:
            color = (255, 245, 220)
            font_size = 10
        glow_rgb = (
            (100, 220, 255) if country == self.team_left_name else (255, 220, 100)
        )
        try:
            captain_font = _get_font("Arial", font_size, bold=True)
            for dx, dy, al in (
                (2, 0, 50),
                (-2, 0, 50),
                (0, 2, 45),
                (0, -2, 45),
                (2, 2, 28),
                (-2, -2, 28),
            ):
                g = captain_font.render(captain_text, True, glow_rgb)
                g.set_alpha(al)
                self.render_surface.blit(
                    g,
                    (
                        flag_x - g.get_width() // 2 + dx,
                        label_y - g.get_height() // 2 + dy,
                    ),
                )
            captain_surface = self._render_text_enhanced(
                captain_text,
                captain_font,
                color,
                outline_color=(0, 0, 0),
                outline_width=2,
            )
            captain_rect = captain_surface.get_rect(center=(flag_x, label_y))
            self.render_surface.blit(captain_surface, captain_rect)
        except Exception as e:
            logger.debug(f"[versus_captain_label] {e}")

    def _load_versus_crest(self, team_name: str, size: int) -> "Optional[pygame.Surface]":
        """Load and cache the team crest PNG scaled to *size* × *size* pixels.

        Args:
            team_name: Team identifier ("River" or "Boca").
            size: Target pixel size (square).

        Returns:
            Scaled pygame.Surface or None if the asset is missing.
        """
        cache_key = (team_name, size)
        if cache_key in self._versus_crests:
            return self._versus_crests[cache_key]

        from core.resources import resource_path
        import os

        filename = f"escudo-{team_name.lower()}.png"
        path = resource_path(os.path.join("assets", "versus", "images", filename))
        surf: "Optional[pygame.Surface]" = None
        try:
            raw = pygame.image.load(path).convert_alpha()
            surf = pygame.transform.smoothscale(raw, (size, size))
        except Exception as e:
            logger.debug(f"[versus_crest] could not load {filename}: {e}")
            surf = None

        self._versus_crests[cache_key] = surf
        return surf

    def _render_racer(self, racer, is_winner: bool = False) -> None:
        """Team crest PNG puck with ground glow; falls back to sphere if image missing."""
        from core.config import MOTOGP_MODE, SCREEN_HEIGHT, TEAM_LEFT, TEAM_RIGHT, VERSUS_PUCK_GROUND_GLOW_ALPHA

        if MOTOGP_MODE:
            super()._render_racer(racer, is_winner=is_winner)
            return

        x = float(racer.body.position.x)
        y = float(racer.body.position.y + (racer.y_offset if hasattr(racer, "y_offset") else 0.0))
        radius = float(racer.draw_radius)
        angle = float(racer.body.angle)

        x = float(x) if math.isfinite(x) else float(self.physics_world.start_x)
        y = float(y) if math.isfinite(y) else float(
            racer.lane * self.physics_world.lane_height + self.physics_world.lane_height // 2
        )
        radius = float(radius) if math.isfinite(radius) else 30.0

        is_frozen = self.physics_world.is_country_frozen(racer.country)
        if is_frozen:
            x += random.uniform(-3, 3)
            y += random.uniform(-2, 2)
        elif racer.country in self.on_fire_countries:
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)

        if is_winner:
            radius = radius * self.winner_scale_pulse

        ix = self._safe_int(x, self.physics_world.start_x)
        iy = self._safe_int(y, SCREEN_HEIGHT // 2)
        ir = self._safe_int(radius, 30)

        # ── Crest display size ───────────────────────────────────────────────
        # 60 % of each half-width keeps the crest prominent without dominating.
        from core.config import SCREEN_WIDTH
        pw = self.physics_world
        half_w = SCREEN_WIDTH // 2
        max_from_width  = int(half_w * 0.60)
        max_from_height = int(pw.game_area_height * 0.55)
        crest_size = min(max_from_width, max_from_height)
        if is_winner:
            crest_size = int(crest_size * self.winner_scale_pulse)

        # ── Ground glow ellipse (scaled to crest size) ───────────────────────
        acc = (
            TEAM_LEFT["accent"]
            if racer.country == self.team_left_name
            else TEAM_RIGHT["accent"]
        )
        glow_alpha = int(VERSUS_PUCK_GROUND_GLOW_ALPHA)
        gr = crest_size // 2
        ell_w, ell_h = max(gr * 3, 24), max(12, gr // 2 + 4)
        ground = pygame.Surface((ell_w, ell_h), pygame.SRCALPHA)
        pygame.draw.ellipse(ground, (*acc[:3], glow_alpha), ground.get_rect())
        self.render_surface.blit(ground, (ix - ell_w // 2, iy + gr - ell_h // 2 + 2))

        # ── Crest image (or sphere fallback) ────────────────────────────────
        crest = self._load_versus_crest(racer.country, crest_size)
        if crest is not None:
            pulse = self._score_pulse.get(racer.country, 0.0)
            if pulse > 0.01:
                # Scale-up bounce: crest grows up to 20 % at pulse peak
                scaled_px = int(crest_size * (1.0 + 0.20 * pulse))
                scaled = pygame.transform.smoothscale(crest, (scaled_px, scaled_px))
                self.render_surface.blit(scaled, scaled.get_rect(center=(ix, iy)))
                # Team-colored concentric glow rings radiating outward
                ring_base_r = scaled_px // 2 + 4
                for i in range(4):
                    ring_r = ring_base_r + i * 7
                    ring_a = int(pulse * (160 - i * 36))
                    if ring_a <= 0:
                        break
                    rsz = ring_r * 2 + 6
                    ring_surf = pygame.Surface((rsz, rsz), pygame.SRCALPHA)
                    pygame.draw.circle(
                        ring_surf, (*acc[:3], ring_a),
                        (rsz // 2, rsz // 2), ring_r, max(2, 4 - i),
                    )
                    self.render_surface.blit(ring_surf, ring_surf.get_rect(center=(ix, iy)))
            else:
                self.render_surface.blit(crest, crest.get_rect(center=(ix, iy)))
        else:
            # ── Sphere fallback ──────────────────────────────────────────────
            d = crest_size
            ball = pygame.Surface((d, d), pygame.SRCALPHA)
            bcx, bcy = d // 2, d // 2
            base = racer.color
            if not (isinstance(base, (tuple, list)) and len(base) >= 3):
                base = (140, 140, 140)
            if racer.country == self.team_left_name:
                dark, midc = (200, 200, 208), (252, 252, 255)
            else:
                dark = tuple(max(0, int(c * 0.42)) for c in base[:3])
                midc = tuple(min(255, int(c * 0.75) + 18) for c in base[:3])
            pygame.draw.circle(ball, dark, (bcx, bcy), gr)
            pygame.draw.circle(ball, midc, (bcx, bcy), max(2, gr - 2))
            self.render_surface.blit(ball, (ix - bcx, iy - bcy))
            pygame.draw.circle(self.render_surface, (0, 0, 0), (ix, iy), gr, 2)

        _ = angle  # rotation reserved

        if is_frozen:
            size = crest_size + 4
            ice_surf = pygame.Surface((size, size), pygame.SRCALPHA)
            ice_surf.fill((80, 210, 255, 100))
            pygame.draw.rect(ice_surf, (200, 240, 255, 200), (0, 0, size, size), 2)
            self.render_surface.blit(ice_surf, (ix - size // 2, iy - size // 2))
            remaining = self.physics_world.frozen_countries.get(racer.country, 0.0)
            timer_font = _get_font("Arial", 18, bold=True)
            timer_surf = timer_font.render(f"{remaining:.1f}s", True, (180, 235, 255))
            self.render_surface.blit(
                timer_surf,
                (ix - timer_surf.get_width() // 2, iy - size // 2 - 22),
            )

        self._render_captain_label(racer, ix, iy)

    def _transition_to_racing(self) -> None:
        super()._transition_to_racing()
        self._apply_split_screen_layout()
        if self.victory_mode == "time" and self.match_start_time is None:
            self.match_start_time = time.time()
            logger.info("Timer de partido iniciado")

    # ── Render: HUD de Versus sobre el render base ────────────────────────────

    def render(self) -> None:
        """Delega al render base; el HUD se inyecta via _pre_flip_screen_overlay."""
        super().render()

    def _pre_flip_screen_overlay(self) -> None:
        """Renderiza el HUD de versus justo antes del display.flip() del core."""
        self._render_versus_hud()
        if self.versus_victory_active:
            self._render_victory_screen()

    def _ensure_versus_scoreboard(self) -> None:
        """Lazily construct (or rebuild after config change) the retro LED scoreboard."""
        if self._versus_scoreboard is not None:
            return
        self._versus_crests.clear()  # force crest reload at new sizes
        self.asset_manager._versus_digital_font_cache.clear()  # flush font cache for new sizes
        from variants.versus.scoreboard_ui import load_versus_scoreboard_fonts
        from core.config import VERSUS_SCOREBOARD_CORNER_RADIUS

        self._versus_scoreboard = load_versus_scoreboard_fonts(
            self.asset_manager,
            score_size=60,
            label_size=52,
            timer_size=22,
            badge_height=50,
            corner_radius=int(VERSUS_SCOREBOARD_CORNER_RADIUS),
        )

    def _render_versus_hud(self) -> None:
        """Retro LED scoreboard: scores, timer, optional Golden Goal row."""
        if self.game_state not in ("RACING", "IDLE"):
            return

        try:
            from core.config import SCREEN_WIDTH, GAME_MARGIN, TEAM_LEFT, TEAM_RIGHT

            surface = self.screen
            cx = GAME_MARGIN + SCREEN_WIDTH // 2

            left_name = self.team_left_name
            right_name = self.team_right_name
            s_left = self.set_score.get(left_name, 0)
            s_right = self.set_score.get(right_name, 0)

            timer_text: Optional[str] = None
            timer_color = (255, 218, 130)
            if self.victory_mode == "time":
                if self.in_extra_time and self.golden_goal_active:
                    # Golden goal / sudden death — no clock, just the label
                    timer_text = "GOL DE ORO"
                    timer_color = (255, 215, 0)
                elif self.match_start_time is None:
                    remaining = self.match_duration
                    timer_text = f"TIEMPO  {int(remaining) // 60}:{int(remaining) % 60:02d}"
                else:
                    remaining = max(0.0, self.match_duration - self.match_elapsed)
                    timer_color = (255, 218, 130) if remaining > 30 else (255, 120, 95)
                    timer_text = f"TIEMPO  {int(remaining) // 60}:{int(remaining) % 60:02d}"

            # "GOL DE ORO" is already shown in the timer row; no extra row needed.
            golden_row = False

            pw = self.physics_world
            first_lane_top = pw.game_area_top + pw.lane_y_offset
            gap = 6
            panel_w = min(SCREEN_WIDTH - 12, 420)
            label_h = 58     # RIVER / BOCA font row
            row2_h  = 68     # badge + score on same row
            timer_h = 24 if timer_text else 0
            gg_h    = 0       # golden_row always False
            pad_y   = 6
            total_h = label_h + row2_h + timer_h + gg_h + pad_y
            top_y = max(GAME_MARGIN + 4, GAME_MARGIN + first_lane_top - total_h - 30)

            panel_rect = pygame.Rect(0, 0, panel_w, total_h)
            panel_rect.centerx = cx
            panel_rect.top = top_y

            self._ensure_versus_scoreboard()
            sb = self._versus_scoreboard

            la = TEAM_LEFT["accent"]
            rc_b = TEAM_RIGHT["color"]
            sb.draw(
                surface,
                panel_rect,
                left_team_upper=left_name,
                right_team_upper=right_name,
                s_left=s_left,
                s_right=s_right,
                timer_text=timer_text,
                timer_color=timer_color,
                golden_goal_row=golden_row,
                anim_time=self._versus_anim_time,
                dt=self._versus_last_dt,
                pulse_left=self._score_pulse.get(left_name, 0.0),
                pulse_right=self._score_pulse.get(right_name, 0.0),
                river_name_color=(min(255, la[0] + 30), min(255, la[1] + 20), min(255, la[2] + 20)),
                river_name_glow=(255, 140, 140),
                boca_name_color=(min(255, rc_b[0] + 40), min(255, rc_b[1] + 60), 255),
                boca_name_glow=(160, 200, 255),
            )

            if self.connection_state and str(self.connection_state) not in (
                "ConnectionState.CONNECTED",
            ):
                hint = pygame.font.SysFont("Arial", 12).render(
                    "Q=River  W=Boca  (DEMO)", True, (100, 100, 100)
                )
                surface.blit(hint, hint.get_rect(centerx=cx, bottom=self.screen.get_height() - 4))

        except Exception as e:
            logger.debug(f"[render_versus_hud] {e}")

    def _render_victory_screen(self) -> None:
        """Enhanced victory screen: winner crest, final score, stat cards, countdown bar."""
        if not self.versus_winner:
            return

        try:
            from core.config import (
                ACTUAL_WIDTH, ACTUAL_HEIGHT, TEAM_LEFT, TEAM_RIGHT,
                GAME_MARGIN, GAME_AREA_TOP, GAME_AREA_BOTTOM, SCREEN_HEIGHT,
            )

            surface = self.screen
            sw, sh = surface.get_size()
            aw = sw if sw > 0 else ACTUAL_WIDTH
            ah = sh if sh > 0 else ACTUAL_HEIGHT
            cx = aw // 2
            t  = self.versus_victory_time
            f  = min(1.0, t * 2.0)       # general 0→1 fade-in over 0.5 s

            winner_cfg = TEAM_LEFT if self.versus_winner == TEAM_LEFT["name"] else TEAM_RIGHT
            loser_cfg  = TEAM_RIGHT if self.versus_winner == TEAM_LEFT["name"] else TEAM_LEFT  # noqa: F841
            w_accent   = winner_cfg["accent"]
            w_color    = winner_cfg["color"]

            # ── Vertical band reserved for content (between camera and chat) ──
            # Top = where the game area starts (below the camera feed).
            # Bottom = where the game area ends (above the chat strip).
            play_top    = GAME_MARGIN + GAME_AREA_TOP                    # ≈ 240 px
            play_bottom = GAME_MARGIN + SCREEN_HEIGHT - GAME_AREA_BOTTOM # ≈ 795 px
            play_center = (play_top + play_bottom) // 2

            # Estimated total content height so we can center it.
            CONTENT_H = 430
            y = max(play_top + 6, play_center - CONTENT_H // 2)

            # ── Dark overlay (fade in) ───────────────────────────────────────
            ov = pygame.Surface((aw, ah), pygame.SRCALPHA)
            ov.fill((0, 0, 0, int(248 * min(1.0, t * 1.5))))
            surface.blit(ov, (0, 0))

            # ── Winner-colored radial glow (centred on content block) ────────
            pulse = 0.7 + 0.3 * math.sin(t * 2.2)
            glow_cy = play_center
            glow_surf = pygame.Surface((aw, ah), pygame.SRCALPHA)
            for i in range(6, 0, -1):
                r = 80 + i * 45
                a = int(pulse * (14 - i * 2) * f)
                if a > 0:
                    pygame.draw.circle(glow_surf, (*w_accent[:3], a), (cx, glow_cy), r)
            surface.blit(glow_surf, (0, 0))

            # ── Row 1: VS badge strip (small crests + score) ─────────────────
            mini = 48
            l_crest = self._load_versus_crest(self.team_left_name, mini)
            r_crest = self._load_versus_crest(self.team_right_name, mini)

            score_l = self.set_score.get(self.team_left_name, 0)
            score_r = self.set_score.get(self.team_right_name, 0)

            score_font_sm = self.asset_manager.get_versus_digital_font(30)
            gap = 70

            # Left crest + score
            if l_crest:
                sc = l_crest.copy(); sc.set_alpha(int(230 * f))
                surface.blit(sc, sc.get_rect(centerx=cx - gap - mini // 2, centery=y + mini // 2))
            sl_surf = score_font_sm.render(str(score_l), True, (255, 212, 72))
            sl_surf.set_alpha(int(255 * f))
            surface.blit(sl_surf, sl_surf.get_rect(centerx=cx - gap + mini // 2 + 4, centery=y + mini // 2))

            # Dash
            dash_font = pygame.font.SysFont("Arial", 22, bold=True)
            dash = dash_font.render("—", True, (90, 90, 90))
            dash.set_alpha(int(200 * f))
            surface.blit(dash, dash.get_rect(center=(cx, y + mini // 2)))

            # Right score + crest
            sr_surf = score_font_sm.render(str(score_r), True, (255, 212, 72))
            sr_surf.set_alpha(int(255 * f))
            surface.blit(sr_surf, sr_surf.get_rect(centerx=cx + gap - mini // 2 - 4, centery=y + mini // 2))
            if r_crest:
                sc = r_crest.copy(); sc.set_alpha(int(230 * f))
                surface.blit(sc, sc.get_rect(centerx=cx + gap + mini // 2, centery=y + mini // 2))

            y += mini + 14

            # ── Row 2: Winner crest (large, golden rings) ────────────────────
            crest_sz = 150
            bounce   = 1.0 + 0.035 * math.sin(t * 3.5)
            draw_sz  = int(crest_sz * bounce * min(1.0, t * 3.0))
            w_crest  = self._load_versus_crest(self.versus_winner, crest_sz)
            crest_cy = y + crest_sz // 2

            # Golden rings (on intermediate surface)
            ring_pulse = 0.55 + 0.45 * math.sin(t * 4.0)
            ring_surf  = pygame.Surface((aw, crest_sz + 40), pygame.SRCALPHA)
            local_cx   = cx
            local_cy   = crest_sz // 2 + 20
            for i in range(4):
                ra = int(ring_pulse * (140 - i * 32) * f)
                if ra > 0:
                    pygame.draw.circle(
                        ring_surf, (255, 215, 0, ra),
                        (local_cx, local_cy), crest_sz // 2 + 6 + i * 7, max(1, 4 - i),
                    )
            surface.blit(ring_surf, (0, y - 20))

            if w_crest and draw_sz > 10:
                ds = pygame.transform.smoothscale(w_crest, (draw_sz, draw_sz))
                ds.set_alpha(int(255 * f))
                surface.blit(ds, ds.get_rect(centerx=cx, centery=crest_cy))

            y += crest_sz + 10

            # ── Row 3: Title "GANADOR: RIVER" ────────────────────────────────
            title_font = self.asset_manager.get_versus_digital_font(44)
            title_text = f"GANADOR: {self.versus_winner.upper()}"
            title_f    = min(1.0, t * 3.0)

            for offset, af in ((5, 0.20), (3, 0.38)):
                for dx, dy in ((-offset, 0), (offset, 0), (0, -offset), (0, offset)):
                    g = title_font.render(title_text, True, w_accent[:3])
                    g.set_alpha(int(200 * title_f * af))
                    surface.blit(g, g.get_rect(centerx=cx + dx, centery=y + dx))
            ts = title_font.render(title_text, True, w_color[:3])
            ts.set_alpha(int(255 * title_f))
            surface.blit(ts, ts.get_rect(centerx=cx, centery=y + title_font.get_height() // 2))
            y += title_font.get_height() + 12

            # ── Separator ────────────────────────────────────────────────────
            sep = pygame.Surface((int(aw * 0.72), 1), pygame.SRCALPHA)
            sep.fill((255, 255, 255, int(35 * f)))
            surface.blit(sep, sep.get_rect(centerx=cx, top=y))
            y += 10

            # ── Row 4: Stat cards (Top Donador | MVP) ────────────────────────
            card_w   = int(aw * 0.40)
            card_h   = 72
            pad      = 10
            card_l_x = cx - card_w - pad // 2
            card_r_x = cx + pad // 2

            lbl_font  = pygame.font.SysFont("Arial", 12, bold=True)
            user_font = pygame.font.SysFont("Arial", 14, bold=True)
            dia_font  = pygame.font.SysFont("Arial", 12)

            def _stat_card(x: int, cy_top: int, title: str, username, diamonds: int,
                           accent: tuple) -> None:
                cs = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
                for i in range(card_h):
                    ratio = i / card_h
                    r = int(12 + accent[0] * 0.07 * (1 - ratio * 0.5))
                    g = int(12 + accent[1] * 0.07 * (1 - ratio * 0.5))
                    b = int(22 + accent[2] * 0.10 * (1 - ratio * 0.5))
                    a = int(170 * f)
                    pygame.draw.line(cs, (r, g, b, a), (0, i), (card_w, i))
                pygame.draw.rect(cs, (*accent[:3], int(160 * f)),
                                 (0, 0, card_w, card_h), 1, border_radius=6)
                t_s = lbl_font.render(title, True, accent[:3])
                t_s.set_alpha(int(230 * f))
                cs.blit(t_s, (8, 6))
                if username:
                    u_s = user_font.render(f"@{username}", True, (235, 235, 235))
                    u_s.set_alpha(int(255 * f))
                    cs.blit(u_s, (8, 24))
                    d_s = dia_font.render(f"{diamonds} diamantes", True, (170, 170, 170))
                    d_s.set_alpha(int(200 * f))
                    cs.blit(d_s, (8, 48))
                else:
                    nd = lbl_font.render("sin datos", True, (90, 90, 90))
                    cs.blit(nd, (8, 30))
                surface.blit(cs, (x, cy_top))

            if self.show_top_donor_global:
                _stat_card(card_l_x, y, "TOP DONADOR",
                           self.victory_top_donor, self.victory_top_donor_diamonds,
                           (255, 215, 0))

            if self.show_mvp_winner_team:
                _stat_card(card_r_x, y, f"MVP {self.versus_winner.upper()}",
                           self.victory_mvp, self.victory_mvp_diamonds,
                           w_accent)

            y += card_h + 14

            # ── Row 5: Countdown bar ─────────────────────────────────────────
            remaining = max(0.0, self.victory_screen_duration - t)
            progress  = remaining / max(1.0, self.victory_screen_duration)

            bar_w = int(aw * 0.62)
            bar_h = 5
            bx    = cx - bar_w // 2

            track = pygame.Surface((bar_w, bar_h), pygame.SRCALPHA)
            track.fill((55, 55, 55, 140))
            surface.blit(track, (bx, y))

            fill_w = int(bar_w * progress)
            if fill_w > 2:
                fc = (80, 210, 110) if remaining > 8 else (255, 130, 50)
                fill = pygame.Surface((fill_w, bar_h), pygame.SRCALPHA)
                fill.fill((*fc, 210))
                surface.blit(fill, (bx, y))

            y += bar_h + 6

            cd_font  = pygame.font.SysFont("Arial", 14, bold=True)
            cd_color = (80, 210, 110) if remaining > 8 else (255, 130, 50)
            cd_text  = f"Nuevo partido en {int(remaining) + 1}s..." if remaining > 0 else "Preparandose..."
            cd_surf  = cd_font.render(cd_text, True, cd_color)
            cd_surf.set_alpha(int(190 * f))
            surface.blit(cd_surf, cd_surf.get_rect(centerx=cx, top=y))

        except Exception as e:
            logger.debug(f"[render_victory_screen] {e}")