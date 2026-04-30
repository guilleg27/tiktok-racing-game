"""
VersusGameEngine — subclase de GameEngine para el modo 1v1.

Sobrescribe exclusivamente la lógica que difiere del core:
  • Sólo 2 equipos (gift_map directo, sin auto-assign)
  • Marcador por puntos y tiempo (un partido; sin series)
  • Tiempo extra + golden goal
  • Pantalla de victoria (top donador + MVP)
  • Sin combos / trails ON FIRE / autopilot (motor liviano)
  • Teclas demo Q/W para simular gifts sin TikTok

El render principal y physics lo hereda de core/game_engine.py sin tocar.
"""

import asyncio
import logging
import time
import math
import random
from typing import Optional

import pygame

from core.game_engine import GameEngine
from core.events import EventType, GameEvent

logger = logging.getLogger(__name__)


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

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_team_from_gift(self, gift_name: str) -> Optional[str]:
        """Devuelve el equipo mapeado al gift, o None si no está en el mapa."""
        return self.gift_team_map.get(gift_name.strip().lower())

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
        """Aplica impulso físico al racer del equipo, como haría el engine base."""
        if team not in self.physics_world.racers:
            logger.warning(f"[VERSUS] Equipo '{team}' no encontrado en racers")
            return

        # Arrancar si estaba en IDLE
        if self.game_state == "IDLE":
            self._transition_to_racing()

        self._on_real_activity()
        self._update_captain_points(username, team, total_diamonds)

        success, was_frozen = self.physics_world.apply_gift_impulse(
            country=team,
            gift_name=gift_name,
            diamond_count=total_diamonds,
        )

        if success:
            self.audio_manager.play_gift_sound(gift_name=gift_name, diamond_value=total_diamonds)
            racer = self.physics_world.racers[team]
            pos = (racer.body.position.x, racer.body.position.y)
            is_large = total_diamonds > 50
            count = 15 + int(total_diamonds / 8) if is_large else 10 + int(total_diamonds / 10)
            self.emit_explosion(pos=pos, color=(255, 215, 0), count=count, power=1.0 if is_large else 0.7, diamond_count=total_diamonds)
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

        if self.cloud_manager.enabled:
            asyncio.create_task(self._sync_versus_result(winner_team))

    # ── Override update: timer de partido y tiempo extra ──────────────────────

    def update(self, dt: float) -> None:
        """Override update para gestionar el timer de partido (modo time)."""
        super().update(dt)

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
                    # Tiempo regular terminado
                    self._evaluate_time_winner()
            else:
                # Tiempo extra
                extra_elapsed = now - (self.extra_time_start or now)
                if extra_elapsed >= self.extra_time_secs:
                    # Tiempo extra terminado
                    self._evaluate_time_winner(is_extra=True)
                elif self.golden_goal_active:
                    # Golden goal activo: cualquier punto gana
                    for team in self.teams:
                        if self.set_score.get(team, 0) > self.set_score.get(
                            self._other_team(team), 0
                        ):
                            self._trigger_set_victory(team)
                            return

    def _other_team(self, team: str) -> str:
        return self.team_right_name if team == self.team_left_name else self.team_left_name

    def _evaluate_time_winner(self, is_extra: bool = False) -> None:
        """Evalúa quién ganó al terminar el tiempo."""
        s_left  = self.set_score.get(self.team_left_name, 0)
        s_right = self.set_score.get(self.team_right_name, 0)

        if s_left != s_right:
            winner = self.team_left_name if s_left > s_right else self.team_right_name
            self._trigger_set_victory(winner)
        elif not is_extra and self.extra_time_secs > 0:
            # Empate → tiempo extra
            self.in_extra_time = True
            self.extra_time_start = time.time()
            self.golden_goal_active = self.golden_goal_enabled
            mode_txt = "GOLDEN GOAL" if self.golden_goal_active else "TIEMPO EXTRA"
            logger.info(f"EMPATE -> {mode_txt}")
            self._add_floating_text(f"{mode_txt}!", color=(255, 215, 0))
        else:
            # Sigue empatado después del tiempo extra → sorteo (random)
            winner = random.choice(self.teams)
            logger.warning(f"[VERSUS] Empate tras tiempo extra → ganador por sorteo: {winner}")
            self._add_floating_text("¡DEFINICIÓN!", color=(255, 80, 80))
            self._trigger_set_victory(winner)

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

    def _transition_to_racing(self) -> None:
        super()._transition_to_racing()
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

    def _render_versus_hud(self) -> None:
        """HUD compacto: marcador + tiempo, justo arriba del primer carril."""
        if self.game_state not in ("RACING", "IDLE"):
            return

        try:
            from core.config import SCREEN_WIDTH, GAME_MARGIN

            surface = self.screen
            cx = GAME_MARGIN + SCREEN_WIDTH // 2

            font_score = pygame.font.SysFont("Arial Black", 20, bold=True)
            font_timer = pygame.font.SysFont("Arial", 14)

            left_name  = self.team_left_name
            right_name = self.team_right_name
            s_left  = self.set_score.get(left_name, 0)
            s_right = self.set_score.get(right_name, 0)

            score_str  = f"{left_name.upper()}  {s_left}  —  {s_right}  {right_name.upper()}"
            score_surf = font_score.render(score_str, True, (255, 255, 255))
            score_rect = score_surf.get_rect(centerx=cx, top=0)

            timer_surf = None
            timer_rect = score_rect
            if self.victory_mode == "time":
                if self.match_start_time is None:
                    remaining = self.match_duration
                    t_color = (200, 200, 200)
                    t_str = f"TIEMPO  {int(remaining)//60}:{int(remaining)%60:02d}"
                elif self.in_extra_time:
                    extra_elapsed = time.time() - (self.extra_time_start or time.time())
                    remaining = max(0.0, self.extra_time_secs - extra_elapsed)
                    t_color = (255, 100, 100)
                    t_str = "GOLDEN GOAL" if self.golden_goal_active else f"EXTRA  {int(remaining)//60}:{int(remaining)%60:02d}"
                else:
                    remaining = max(0.0, self.match_duration - self.match_elapsed)
                    t_color = (255, 215, 0) if remaining > 30 else (255, 80, 80)
                    t_str = f"TIEMPO  {int(remaining)//60}:{int(remaining)%60:02d}"
                timer_surf = font_timer.render(t_str, True, t_color)
                timer_rect = timer_surf.get_rect(centerx=cx, top=score_rect.bottom + 3)

            pad_x, pad_y = 10, 4
            total_h = score_rect.height + (timer_rect.height + 3 if timer_surf else 0) + pad_y * 2

            pw = self.physics_world
            first_lane_top = pw.game_area_top + pw.lane_y_offset
            gap = 6
            top_y = GAME_MARGIN + first_lane_top - total_h - gap
            top_y = max(GAME_MARGIN + 2, int(top_y))
            score_rect.top = top_y
            if timer_surf:
                timer_rect.top = score_rect.bottom + 3

            bg = pygame.Surface((score_rect.width + pad_x * 2, total_h), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 160))
            surface.blit(bg, (score_rect.left - pad_x, score_rect.top - pad_y))
            surface.blit(score_surf, score_rect)
            if timer_surf:
                surface.blit(timer_surf, timer_rect)

            # Teclas demo
            if self.connection_state and str(self.connection_state) not in ("ConnectionState.CONNECTED",):
                hint = pygame.font.SysFont("Arial", 12).render("Q=River  W=Boca  (DEMO)", True, (100, 100, 100))
                surface.blit(hint, hint.get_rect(centerx=cx, bottom=self.screen.get_height() - 4))

        except Exception as e:
            logger.debug(f"[render_versus_hud] {e}")

    def _render_victory_screen(self) -> None:
        """Pantalla de victoria del partido: marcador final, top donador, MVP."""
        if not self.versus_winner:
            return

        try:
            import pygame
            from core.config import ACTUAL_WIDTH, ACTUAL_HEIGHT, TEAM_LEFT, TEAM_RIGHT

            surface = self.screen
            sw, sh = surface.get_size()
            # Prefer real backbuffer size (packaged / resized); fallback to config.
            aw = sw if sw > 0 else ACTUAL_WIDTH
            ah = sh if sh > 0 else ACTUAL_HEIGHT
            cx = aw // 2

            # Overlay oscuro — cubre toda la ventana (incl. márgenes del marco)
            overlay = pygame.Surface((aw, ah), pygame.SRCALPHA)
            alpha = min(200, int(self.versus_victory_time * 100))
            overlay.fill((0, 0, 0, alpha))
            surface.blit(overlay, (0, 0))

            winner_cfg = TEAM_LEFT if self.versus_winner == TEAM_LEFT["name"] else TEAM_RIGHT
            font_title  = pygame.font.SysFont("Arial Black", 48, bold=True)
            font_sub    = pygame.font.SysFont("Arial", 22, bold=True)
            font_detail = pygame.font.SysFont("Arial", 18)

            cy = ah // 2 - 80

            # Título
            title_surf = font_title.render(f"{winner_cfg['name'].upper()} GANO", True, winner_cfg["color"])
            surface.blit(title_surf, title_surf.get_rect(centerx=cx, centery=cy))
            cy += 60

            left  = self.team_left_name
            right = self.team_right_name
            ma = self.set_score.get(left, 0)
            mb = self.set_score.get(right, 0)
            marcador_str = f"Marcador final: {left} {ma} — {mb} {right}"
            marcador_surf = font_sub.render(marcador_str, True, (255, 215, 0))
            surface.blit(marcador_surf, marcador_surf.get_rect(centerx=cx, centery=cy))
            cy += 45

            # Top donador global
            if self.show_top_donor_global and self.victory_top_donor:
                donor_surf = font_detail.render(
                    f"Top donador: @{self.victory_top_donor} ({self.victory_top_donor_diamonds} diamantes)",
                    True, (200, 200, 255)
                )
                surface.blit(donor_surf, donor_surf.get_rect(centerx=cx, centery=cy))
                cy += 30

            # MVP equipo ganador
            if self.show_mvp_winner_team and self.victory_mvp:
                mvp_surf = font_detail.render(
                    f"MVP {winner_cfg['name']}: @{self.victory_mvp} ({self.victory_mvp_diamonds} diamantes)",
                    True, (255, 230, 100)
                )
                surface.blit(mvp_surf, mvp_surf.get_rect(centerx=cx, centery=cy))
                cy += 30

            # Cuenta regresiva para nuevo duelo
            remaining = max(0.0, self.victory_screen_duration - self.versus_victory_time)
            if remaining < 8:
                countdown_surf = font_detail.render(
                    f"Nuevo partido en {int(remaining) + 1}s...", True, (150, 150, 150)
                )
                surface.blit(countdown_surf, countdown_surf.get_rect(centerx=cx, centery=cy + 20))

        except Exception as e:
            logger.debug(f"[render_victory_screen] {e}")