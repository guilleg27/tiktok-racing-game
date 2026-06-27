"""
CountriesGameEngine — subclase de GameEngine para el modo Countries (12 países).

Añade sobre el core:
  · Pantalla de victoria custom: escudo pulsante + anillos dorados + stat cards + countdown
  · Stats de sesión acumuladas entre carreras (wins por país, totales del stream)
  · Momentum aura: anillos de color alrededor del escudo en combo / ON FIRE
  · "Agita las banderas": renombra la barra de likes en lugar de "Nitro Boost"
"""

from __future__ import annotations

import asyncio
import math
import random
import time
import logging

import pygame

from core.game_engine import GameEngine, _get_font
from core.events import EventType

logger = logging.getLogger(__name__)

_QUIEREME_NAMES              = ("quiéreme", "quiereme", "heart me", "me gusta")
_COUNTRIES_FOLLOW_DISTANCE   = 5
_COUNTRIES_SHARE_DISTANCE    = 1     # 3 px/share (was 9 px — flood de shares ganaba solo)
_COUNTRIES_SHARE_COOLDOWN    = 3.0   # segundos entre shares del mismo usuario
_COUNTRIES_QUIEREME_DISTANCE = 15
_COUNTRIES_VOTE_DIAMOND      = 0.12  # 0.36 px/voto — calibrado para 80-150 viewers (~90 seg)
_COUNTRIES_GIFT_SCALE        = 0.33  # gifts valen 1/3 del core (1💎 ≈ 2.75 votos)
_COUNTRIES_MAX_TARGET_LEAD   = 80.0  # px max que target_x puede adelantarse al cuerpo físico
_COUNTRIES_DRAIN_RATE        = 3.0   # px/s a los que se drena el overflow de gifts grandes
_AVATAR_SIZE                 = 16    # diámetro px del círculo de avatar del capitán


class CountriesGameEngine(GameEngine):

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        # Per-race accumulators (cleared on _return_to_idle)
        self._comment_counts: dict[str, int] = {}
        self._diamond_totals: dict[str, int] = {}
        self._last_share_time: dict[str, float] = {}
        self._gift_overflow: dict[str, float] = {}
        # px contributed per user per country — used for captain ranking
        self._captain_px: dict[str, dict[str, float]] = {}

        # Avatar cache: persiste entre carreras (las fotos no cambian)
        self._avatar_cache: dict[str, pygame.Surface | None] = {}
        self._avatar_pending: set[str] = set()

        # Stats snapshot at the moment the winner is detected
        self._victory_top_commenter: tuple[str, int] = ("", 0)
        self._victory_top_donor: tuple[str, int] = ("", 0)

        # Session stats: persist across races for the whole stream
        self._session_wins: dict[str, int] = {}
        self._session_race_count: int = 0

    # ── Stat hooks ──────────────────────────────────────────────────────────

    def _on_gift_processed(self, username: str, country: str, diamonds: int) -> None:
        if username:
            self._diamond_totals[username] = self._diamond_totals.get(username, 0) + diamonds

    def _on_vote_processed(self, username: str, country: str) -> None:
        if username:
            self._comment_counts[username] = self._comment_counts.get(username, 0) + 1

    # ── Victory trigger: snapshot race stats + update session totals ─────────

    def _trigger_victory_sequence(self, winner_country: str, winner_captain: str) -> None:
        if self._comment_counts:
            top_u = max(self._comment_counts, key=self._comment_counts.get)  # type: ignore[arg-type]
            self._victory_top_commenter = (top_u, self._comment_counts[top_u])
        else:
            self._victory_top_commenter = ("", 0)

        if self._diamond_totals:
            top_d = max(self._diamond_totals, key=self._diamond_totals.get)  # type: ignore[arg-type]
            self._victory_top_donor = (top_d, self._diamond_totals[top_d])
        else:
            self._victory_top_donor = ("", 0)

        self._session_wins[winner_country] = self._session_wins.get(winner_country, 0) + 1
        self._session_race_count += 1

        super()._trigger_victory_sequence(winner_country, winner_captain)

    # ── Desactivar countdown de desastre ────────────────────────────────────

    def _update_hype_timer(self) -> None:
        pass

    def _render_hype_timer(self, surface) -> None:
        pass

    # ── Timer de victoria: 15s en lugar de 30s ───────────────────────────────

    def update(self, dt: float) -> None:
        if (
            self.physics_world is not None
            and self.physics_world.race_finished
            and self.physics_world.winner
            and self.winner_animation_time >= 15.0
        ):
            self._return_to_idle()
            return
        super().update(dt)
        self._drain_gift_overflow(dt)

    # ── Avatar del capitán ───────────────────────────────────────────────────────

    def _queue_avatar_fetch(self, username: str, avatar_url: str) -> None:
        if username in self._avatar_cache or username in self._avatar_pending:
            return
        if not avatar_url:
            self._avatar_cache[username] = self._make_placeholder_circle()
            return
        logger.info("[avatar] queuing fetch for %s", username)
        self._avatar_pending.add(username)
        asyncio.create_task(self._fetch_avatar(username, avatar_url))

    @staticmethod
    def _make_placeholder_circle() -> pygame.Surface:
        sz   = _AVATAR_SIZE
        surf = pygame.Surface((sz, sz), pygame.SRCALPHA)
        surf.fill((0, 0, 0, 0))
        pygame.draw.circle(surf, (90, 140, 255, 200), (sz // 2, sz // 2), sz // 2)
        return surf

    async def _fetch_avatar(self, username: str, avatar_url: str) -> None:
        try:
            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(None, self._download_url, avatar_url)
            if data:
                import io as _io
                buf = _io.BytesIO(data)
                buf.seek(0)
                raw = pygame.image.load(buf).convert()
                # Pre-clip to circle once — avoids work every frame at 60fps
                sz      = _AVATAR_SIZE
                clipped = pygame.Surface((sz, sz), pygame.SRCALPHA)
                clipped.fill((0, 0, 0, 0))
                pygame.draw.circle(clipped, (255, 255, 255, 255), (sz // 2, sz // 2), sz // 2)
                scaled  = pygame.transform.smoothscale(raw, (sz, sz))
                # BLEND_RGB_MULT: keeps RGB of image where mask is white (inside circle)
                # alpha remains from draw.circle: 255 inside, 0 outside
                clipped.blit(scaled, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
                self._avatar_cache[username] = clipped
                logger.info("Avatar cached for %s (%d bytes)", username, len(data))
            else:
                self._avatar_cache[username] = None
                logger.warning("Avatar download returned empty data for %s", username)
        except Exception as exc:
            logger.warning("Avatar fetch failed for %s: %s", username, exc)
            self._avatar_cache[username] = None
        finally:
            self._avatar_pending.discard(username)

    @staticmethod
    def _download_url(url: str) -> bytes | None:
        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.read()
        except Exception as exc:
            logger.debug("Avatar download error: %s", exc)
            return None

    def _render_captain_label(self, racer, flag_x: int, flag_y: int) -> None:
        country = racer.country
        captain = self.current_captains.get(country, "")
        if not captain:
            return

        av_sz   = _AVATAR_SIZE
        avatar  = self._avatar_cache.get(captain)
        has_av  = avatar is not None
        row_y   = flag_y + 25   # vertical center of the label row
        gap     = 4             # px between avatar and text

        try:
            is_new  = country in self.captain_change_timer
            color   = (255, 223, 0) if is_new else (255, 245, 200)
            font_sz = 12 if is_new else 10
            font    = _get_font("Arial", font_sz, bold=True)
            text_surf = self._render_text_enhanced(
                captain, font, color,
                outline_color=(0, 0, 0), outline_width=2,
            )
            tw, th = text_surf.get_size()

            if has_av:
                # ── Avatar + name side by side, centered on flag_x ───────────
                total_w = av_sz + gap + tw
                left_x  = flag_x - total_w // 2

                # Soft glow behind avatar (filled circle, low alpha — no hard pixelated border)
                glow_sz = av_sz + 4
                glow    = pygame.Surface((glow_sz, glow_sz), pygame.SRCALPHA)
                glow.fill((0, 0, 0, 0))
                pygame.draw.circle(glow, (255, 210, 60, 70), (glow_sz // 2, glow_sz // 2), glow_sz // 2)
                self.render_surface.blit(glow, (left_x - 2, row_y - glow_sz // 2))
                self.render_surface.blit(avatar, (left_x, row_y - av_sz // 2))

                # Text to the right of avatar
                self.render_surface.blit(text_surf, (left_x + av_sz + gap, row_y - th // 2))
            else:
                # ── Name only, centered ───────────────────────────────────────
                self.render_surface.blit(text_surf, text_surf.get_rect(center=(flag_x, row_y)))

        except Exception as exc:
            logger.debug("Captain label render error: %s", exc)

    def _drain_gift_overflow(self, dt: float) -> None:
        """Drena el overflow de gifts grandes para evitar teletransportes visuales.

        Cada frame: si target_x está más de _COUNTRIES_MAX_TARGET_LEAD px adelante
        del cuerpo físico, el exceso se encola. La cola se drena a _COUNTRIES_DRAIN_RATE
        px/s — el país avanza visiblemente en lugar de saltar.
        """
        if not self.physics_world or self.physics_world.race_finished:
            return
        drain_px = _COUNTRIES_DRAIN_RATE * dt
        for country, racer in self.physics_world.racers.items():
            lead = racer.target_x - racer.body.position.x
            if lead > _COUNTRIES_MAX_TARGET_LEAD:
                overflow = lead - _COUNTRIES_MAX_TARGET_LEAD
                racer.target_x -= overflow
                self._gift_overflow[country] = self._gift_overflow.get(country, 0.0) + overflow
            pending = self._gift_overflow.get(country, 0.0)
            if pending > 0.0:
                to_apply = min(drain_px, pending)
                racer.target_x += to_apply
                self._gift_overflow[country] = pending - to_apply

    # ── Sin tabla de clasificación final ─────────────────────────────────────

    def _render_leaderboard(self) -> None:
        pass

    # ── Victory screen ───────────────────────────────────────────────────────

    def _render_victory_sequence(self) -> None:
        if not self.victory_sequence_active:
            return

        from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, GAME_AREA_TOP, GAME_AREA_BOTTOM

        surface = self.render_surface
        sw, sh   = SCREEN_WIDTH, SCREEN_HEIGHT
        cx       = sw // 2
        t        = self.victory_sequence_time
        fade_in  = min(1.0, t * 2.5)   # 0→1 in 0.4 s

        winner = self.physics_world.winner
        if not winner:
            return

        racer    = self.physics_world.racers.get(winner)
        w_accent = racer.color if racer else (255, 215, 0)

        play_top = GAME_AREA_TOP
        play_h   = sh - GAME_AREA_BOTTOM - play_top
        play_cy  = play_top + play_h // 2

        # ── Confetti from core ────────────────────────────────────────────
        self._render_confetti()

        # ── Dark overlay on the race area ─────────────────────────────────
        ov = pygame.Surface((sw, play_h), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 210))
        surface.blit(ov, (0, play_top))

        # ── Radial glow centred on the play area ──────────────────────────
        pulse_glow = 0.65 + 0.35 * math.sin(t * 2.5)
        glow = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for i in range(6, 0, -1):
            r = 80 + i * 38
            a = int(pulse_glow * (14 - i * 2))
            if a > 0:
                pygame.draw.circle(glow, (*w_accent[:3], a), (cx, play_cy), r)
        surface.blit(glow, (0, 0))

        # ── Layout anchor: centred accounting for podium below countdown ────
        content_h = 460
        y = max(play_top + 10, play_cy - content_h // 2)

        # ── Pulsing winner flag / escudo ──────────────────────────────────
        flag_sz  = 110
        scale_in = min(1.0, t * 3.0)                   # bounce-in over 0.33 s
        bounce   = 1.0 + 0.06 * math.sin(t * 3.8)      # continuous breathe
        draw_sz  = max(1, int(flag_sz * scale_in * bounce))

        flag_surf = self.asset_manager.get_sprite(winner, flag_sz)
        flag_cy   = y + flag_sz // 2

        if flag_surf and draw_sz > 10:
            scaled = pygame.transform.smoothscale(flag_surf, (draw_sz, draw_sz))
            surface.blit(scaled, scaled.get_rect(centerx=cx, centery=flag_cy))

        # Golden rings pulsing around the flag
        ring_pulse = 0.5 + 0.5 * math.sin(t * 4.2)
        for i in range(3):
            ring_a = int(ring_pulse * (130 - i * 40))
            if ring_a > 0:
                pygame.draw.circle(
                    surface, (255, 215, 0),
                    (cx, flag_cy),
                    flag_sz // 2 + 6 + i * 7,
                    max(1, 3 - i),
                )

        y += flag_sz + 10

        # ── Country name ──────────────────────────────────────────────────
        pulse_gold = (255, int(200 + 55 * math.sin(t * 6.0)), int(50 * abs(math.sin(t * 4.0))))
        title_font = _get_font("Arial", 36, bold=True)
        title_text = f"¡{winner.upper()} GANA!"

        shadow_s = title_font.render(title_text, True, (0, 0, 0))
        surface.blit(shadow_s, shadow_s.get_rect(centerx=cx + 2, centery=y + title_font.get_height() // 2 + 2))
        title_s = title_font.render(title_text, True, pulse_gold)
        surface.blit(title_s,  title_s.get_rect(centerx=cx,     centery=y + title_font.get_height() // 2))
        y += title_font.get_height() + 5

        # ── Captain ───────────────────────────────────────────────────────
        captain = self.victory_winner_captain
        if captain and captain != "Unknown":
            cap_font = _get_font("Arial", 15, bold=True)
            cap_text = f"CAMPEON: @{captain}"
            cap_s = cap_font.render(cap_text, True, (210, 210, 255))
            surface.blit(cap_s, cap_s.get_rect(centerx=cx, centery=y + cap_font.get_height() // 2))
            y += cap_font.get_height() + 5

        # Separator
        pygame.draw.line(surface, (100, 100, 120), (cx - int(sw * 0.34), y), (cx + int(sw * 0.34), y))
        y += 10

        # ── Stat cards ────────────────────────────────────────────────────
        card_w  = int(sw * 0.42)
        card_h  = 74
        gap     = 8
        card_lx = cx - card_w - gap // 2
        card_rx = cx + gap // 2

        lbl_font  = _get_font("Arial", 12, bold=True)
        user_font = _get_font("Arial", 14, bold=True)
        sub_font  = _get_font("Arial", 11)

        def _stat_card(
            sx: int, sy: int, title: str,
            username: str, value: int, value_label: str,
            accent: tuple,
        ) -> None:
            cs = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            for row in range(card_h):
                ratio = row / card_h
                r = int(12 + accent[0] * 0.06 * (1 - ratio * 0.5))
                g = int(12 + accent[1] * 0.06 * (1 - ratio * 0.5))
                b = int(22 + accent[2] * 0.08 * (1 - ratio * 0.5))
                pygame.draw.line(cs, (r, g, b, 185), (0, row), (card_w, row))
            pygame.draw.rect(cs, (*accent[:3], 180), (0, 0, card_w, card_h), 1, border_radius=6)
            t_s = lbl_font.render(title, True, accent[:3])
            cs.blit(t_s, (8, 5))
            if username:
                u_sh = user_font.render(f"@{username}", True, (0, 0, 0))
                cs.blit(u_sh, (9, 22))
                u_s = user_font.render(f"@{username}", True, (240, 240, 240))
                cs.blit(u_s, (8, 21))
                v_s = sub_font.render(f"{value:,} {value_label}", True, (180, 180, 180))
                cs.blit(v_s, (8, 48))
            else:
                nd = lbl_font.render("sin datos", True, (100, 100, 100))
                cs.blit(nd, (8, 28))
            surface.blit(cs, (sx, sy))

        commenter_user, commenter_count = self._victory_top_commenter
        donor_user, donor_diamonds      = self._victory_top_donor

        _stat_card(card_lx, y, "TOP VOTADOR", commenter_user, commenter_count, "votos",  (100, 180, 255))
        _stat_card(card_rx, y, "MVP",         donor_user,    donor_diamonds,   "puntos", (255, 215, 0))
        y += card_h + 8

        # ── Session race counter ──────────────────────────────────────────
        if self._session_race_count > 0:
            n = self._session_race_count
            sess_s = _get_font("Arial", 12).render(
                f"SESION: {n} {'carrera' if n == 1 else 'carreras'}",
                True, (150, 150, 200),
            )
            surface.blit(sess_s, sess_s.get_rect(centerx=cx, top=y))
            y += sess_s.get_height() + 8

        # ── Countdown bar ─────────────────────────────────────────────────
        VICTORY_TOTAL = 15.0
        remaining = max(0.0, VICTORY_TOTAL - self.winner_animation_time)
        progress  = remaining / VICTORY_TOTAL

        bar_w = int(sw * 0.62)
        bar_h = 5
        bx    = cx - bar_w // 2

        pygame.draw.rect(surface, (50, 50, 50), (bx, y, bar_w, bar_h))
        fill_w = int(bar_w * progress)
        if fill_w > 2:
            fc = (80, 210, 110) if remaining > 5 else (255, 130, 50)
            pygame.draw.rect(surface, fc, (bx, y, fill_w, bar_h))
        y += bar_h + 5

        cd_font  = _get_font("Arial", 13, bold=True)
        cd_color = (80, 210, 110) if remaining > 5 else (255, 130, 50)
        cd_text  = f"Nueva carrera en {int(remaining) + 1}s..." if remaining > 0 else "Preparando..."

        cd_sh = cd_font.render(cd_text, True, (0, 0, 0))
        surface.blit(cd_sh, cd_sh.get_rect(centerx=cx + 1, top=y + 1))
        cd_s = cd_font.render(cd_text, True, cd_color)
        surface.blit(cd_s,  cd_s.get_rect(centerx=cx,     top=y))
        y += cd_font.get_height() + 10

        # ── Podio de sesión ───────────────────────────────────────────────
        if self._session_wins:
            from core.config import COUNTRY_ABBREV

            ranked = sorted(self._session_wins.items(), key=lambda kv: kv[1], reverse=True)[:5]

            pod_flag_sz  = 34
            pod_item_w   = 68
            pod_name_fnt = _get_font("Arial", 10, bold=True)
            pod_wins_fnt = _get_font("Arial", 15, bold=True)
            pod_lbl_fnt  = _get_font("Arial", 10)

            # "VICTORIAS" label centred above the row
            lbl_s = pod_lbl_fnt.render("VICTORIAS", True, (120, 120, 150))
            surface.blit(lbl_s, lbl_s.get_rect(centerx=cx, top=y))
            y += lbl_s.get_height() + 4

            total_w = len(ranked) * pod_item_w
            pod_x   = cx - total_w // 2

            for i, (country, wins) in enumerate(ranked):
                item_cx = pod_x + i * pod_item_w + pod_item_w // 2

                # Use the racer's existing sprite (already correct appearance) scaled down
                pod_racer = self.physics_world.racers.get(country)
                raw_sprite = pod_racer.sprite if pod_racer else None
                if raw_sprite:
                    flag_s = pygame.transform.smoothscale(raw_sprite, (pod_flag_sz, pod_flag_sz))
                    surface.blit(flag_s, flag_s.get_rect(centerx=item_cx, top=y))

                # Country abbreviation
                abbrev = COUNTRY_ABBREV.get(country, country[:3].upper())
                name_s = pod_name_fnt.render(abbrev, True, (200, 200, 200))
                surface.blit(name_s, name_s.get_rect(centerx=item_cx, top=y + pod_flag_sz + 2))

                # Win count in gold
                wins_s = pod_wins_fnt.render(f"{wins}", True, (255, 215, 0))
                surface.blit(wins_s, wins_s.get_rect(centerx=item_cx, top=y + pod_flag_sz + 14))

        # ── Entry fade-in overlay ─────────────────────────────────────────
        if fade_in < 1.0:
            fade_ov = pygame.Surface((sw, play_h), pygame.SRCALPHA)
            fade_ov.fill((0, 0, 0, int(255 * (1.0 - fade_in))))
            surface.blit(fade_ov, (0, play_top))

    # ── Momentum aura ────────────────────────────────────────────────────────

    def _render_racer(self, racer, is_winner: bool = False) -> None:
        if not is_winner:
            self._draw_momentum_aura(racer)
        super()._render_racer(racer, is_winner)
        self._draw_lane_badge(racer)
        if not is_winner:
            self._draw_country_name_label(racer)

    def _draw_lane_badge(self, racer) -> None:
        x = racer.body.position.x
        y = racer.body.position.y + getattr(racer, 'y_offset', 0.0)
        if not (math.isfinite(x) and math.isfinite(y)):
            return

        r       = racer.draw_radius   # 12 px
        badge_r = 8                   # circle radius
        gap     = 5                   # space between flag left edge and badge right edge

        cx = int(x) - r - gap - badge_r
        cy = int(y)

        size = badge_r * 2 + 2        # surface size with 1px margin on each side
        c    = badge_r + 1            # center coords inside the surface

        badge = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(badge, (15, 15, 25, 215), (c, c), badge_r)          # dark fill
        pygame.draw.circle(badge, (*racer.color[:3], 210), (c, c), badge_r, 1) # colored border

        num_s = _get_font("Arial", 10, bold=True).render(str(racer.lane + 1), True, (255, 255, 255))
        badge.blit(num_s, num_s.get_rect(center=(c, c)))

        self.render_surface.blit(badge, (cx - c, cy - c))

    def _draw_momentum_aura(self, racer) -> None:
        combo_count = self.combo_counts.get(racer.country, 0)
        is_on_fire  = racer.country in self.on_fire_countries

        if combo_count < self.combo_threshold and not is_on_fire:
            return

        x = racer.body.position.x
        y = racer.body.position.y
        if not (math.isfinite(x) and math.isfinite(y)):
            return

        base_r = racer.draw_radius
        pulse  = 0.5 + 0.5 * math.sin(time.perf_counter() * 5.0)

        if is_on_fire:
            color = (255, 120, 0)
            rings = 4
            max_r = int(base_r * 2.4)
        else:
            color = (100, 200, 255)
            rings = 2
            max_r = int(base_r * 1.8)

        for i in range(rings):
            r_i = int(base_r + 3 + i * (max_r - base_r) / rings)
            a_i = int(pulse * max(0, 80 - i * 20))
            if a_i <= 0:
                continue
            size = r_i * 2 + 4
            aura = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(
                aura, (*color, a_i),
                (size // 2, size // 2),
                r_i, max(1, 2 - i),
            )
            self.render_surface.blit(aura, (int(x) - size // 2, int(y) - size // 2))

    # ── Country name label (right of flag, moves with it) ────────────────────

    def _draw_country_name_label(self, racer) -> None:
        x = racer.body.position.x
        y = racer.body.position.y + getattr(racer, 'y_offset', 0.0)
        if not (math.isfinite(x) and math.isfinite(y)):
            return

        r    = racer.draw_radius  # 12 px
        gap  = 6
        font = _get_font("Arial", 9, bold=True)
        name = racer.country

        text_surf = font.render(name, True, (255, 255, 255))
        tw, th = text_surf.get_size()

        tx = int(x) + r + gap
        ty = int(y) - th // 2

        pad_x, pad_y = 3, 2
        bg = pygame.Surface((tw + pad_x * 2, th + pad_y * 2), pygame.SRCALPHA)
        pygame.draw.rect(bg, (0, 0, 0, 160), bg.get_rect(), border_radius=4)
        self.render_surface.blit(bg, (tx - pad_x, ty - pad_y))

        self.render_surface.blit(font.render(name, True, (0, 0, 0)), (tx + 1, ty + 1))
        self.render_surface.blit(text_surf, (tx, ty))

    # ── "Agita las banderas" + mini podio de sesión a la derecha ────────────

    def _render_likes_bar(self) -> None:
        from core.config import (
            GAME_MODE, CTA_BANNER_Y, CTA_BANNER_HEIGHT, LIKES_BAR_HEIGHT, SCREEN_WIDTH,
        )

        bar_height   = LIKES_BAR_HEIGHT  # 12 px
        bar_margin_x = 20
        full_width   = SCREEN_WIDTH - 2 * bar_margin_x  # 420 px

        # Mini podium: up to 3 countries sorted by session wins
        ranked_pod = (
            sorted(self._session_wins.items(), key=lambda kv: kv[1], reverse=True)[:3]
            if self._session_wins else []
        )
        MINI_FLAG  = 16
        MINI_NUM_W = 20   # estimated px for "Nx"
        MINI_ITEM  = MINI_FLAG + 3 + MINI_NUM_W   # 39 px per entry
        MINI_GAP   = 4
        BAR_PAD    = 8    # gap between bar end and first flag

        pod_reserve = (
            len(ranked_pod) * MINI_ITEM + max(0, len(ranked_pod) - 1) * MINI_GAP + BAR_PAD
        ) if ranked_pod else 0

        bar_width = full_width - pod_reserve
        progress  = min(1.0, self.current_likes / self.likes_goal) if self.likes_goal > 0 else 0.0

        label_font = _get_font("Arial Black", 12, bold=False)
        label      = f"¡AGITA LAS BANDERAS! ({self.current_likes}/{self.likes_goal})"
        label_surf = label_font.render(label, True, (255, 255, 255))

        if GAME_MODE == "COMMENT" and self.game_state == "RACING":
            label_y = CTA_BANNER_Y + CTA_BANNER_HEIGHT + 2 + self._hud_offset
            bar_y   = label_y + label_surf.get_height() + 2
        else:
            bar_y   = self.header_height + 2 + self._hud_offset
            label_y = bar_y - 2 - label_surf.get_height()

        # ── Bar (shortened when podium is visible) ────────────────────────
        track_surf = pygame.Surface((bar_width, bar_height), pygame.SRCALPHA)
        track_surf.fill((0, 0, 0, 0))
        pygame.draw.rect(
            track_surf, (30, 30, 40, 220),
            (0, 0, bar_width, bar_height), border_radius=bar_height // 2,
        )
        self.render_surface.blit(track_surf, (bar_margin_x, bar_y))

        if progress > 0.001:
            fill_w    = max(bar_height, int(bar_width * progress))
            grad_surf = pygame.Surface((fill_w, bar_height), pygame.SRCALPHA)
            for col in range(fill_w):
                tv = col / bar_width
                r, g, b = 255, int(120 * (1 - tv) + 105 * tv), int(50 * (1 - tv) + 180 * tv)
                pygame.draw.line(grad_surf, (r, g, b, 255), (col, 0), (col, bar_height - 1))
            clip_surf = pygame.Surface((fill_w, bar_height), pygame.SRCALPHA)
            pygame.draw.rect(
                clip_surf, (255, 255, 255, 255),
                (0, 0, fill_w, bar_height), border_radius=bar_height // 2,
            )
            grad_surf.blit(clip_surf, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)
            self.render_surface.blit(grad_surf, (bar_margin_x, bar_y))

        pygame.draw.rect(
            self.render_surface, (255, 180, 180, 120),
            pygame.Rect(bar_margin_x, bar_y, bar_width, bar_height),
            1, border_radius=bar_height // 2,
        )
        self.render_surface.blit(label_surf, (int(bar_margin_x), int(label_y)))

        # ── Mini podio a la derecha de la barra ───────────────────────────
        if ranked_pod:
            bar_cy   = bar_y + bar_height // 2
            pod_x    = bar_margin_x + bar_width + BAR_PAD
            wins_fnt = _get_font("Arial", 11, bold=True)

            # Fondo negro leve para que no se confunda con la pista
            pod_total_w = len(ranked_pod) * MINI_ITEM + max(0, len(ranked_pod) - 1) * MINI_GAP
            bg_pad = 3
            bg = pygame.Surface((pod_total_w + bg_pad * 2, bar_height + bg_pad * 2), pygame.SRCALPHA)
            bg.fill((0, 0, 0, 160))
            self.render_surface.blit(bg, (pod_x - bg_pad, bar_cy - bar_height // 2 - bg_pad))

            for i, (country, wins) in enumerate(ranked_pod):
                item_x    = pod_x + i * (MINI_ITEM + MINI_GAP)
                pod_racer = self.physics_world.racers.get(country)
                raw_spr   = pod_racer.sprite if pod_racer else None
                if raw_spr:
                    flag_s = pygame.transform.smoothscale(raw_spr, (MINI_FLAG, MINI_FLAG))
                    self.render_surface.blit(flag_s, flag_s.get_rect(left=item_x, centery=bar_cy))
                wins_s = wins_fnt.render(f"{wins}", True, (255, 215, 0))
                self.render_surface.blit(wins_s, wins_s.get_rect(left=item_x + MINI_FLAG + 3, centery=bar_cy))

    # ── Ranking: convertir ISOs de otras variantes a nombre completo ─────────

    async def _fetch_global_ranking(self) -> None:
        await super()._fetch_global_ranking()
        from core.config import COUNTRY_ABBREV
        iso_to_full = {v: k for k, v in COUNTRY_ABBREV.items()}
        for dataset in (self.global_rank_data, self.daily_rank_data):
            for entry in dataset:
                raw = entry.get('country', '')
                entry['country'] = iso_to_full.get(raw, raw)

    # ── Idle screen: quitar línea "Distancia: X diamantes" ──────────────────

    def _render_idle_screen(self) -> None:
        from core.config import SCREEN_WIDTH, SCREEN_HEIGHT

        overlay = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.render_surface.blit(overlay, (0, 0))

        if self.last_winner:
            _panel_bottom = (SCREEN_HEIGHT - 210) // 2 + 40 + 210
            winner_font = _get_font("Arial", 14, bold=True)
            winner_text = f"Último ganador: {self.last_winner}"
            winner_surface = self._render_text_enhanced(
                winner_text, winner_font, (100, 255, 150),
                outline_color=(0, 0, 0), outline_width=2,
            )
            self.render_surface.blit(
                winner_surface,
                winner_surface.get_rect(center=(SCREEN_WIDTH // 2, _panel_bottom + 18)),
            )
            # "Distancia: X diamantes" omitido intencionalmente

        self._render_global_ranking_futuristic()

    # ── Return to idle: clear per-race state, keep session stats ─────────────

    def _return_to_idle(self) -> None:
        self._comment_counts.clear()
        self._diamond_totals.clear()
        self._victory_top_commenter = ("", 0)
        self._victory_top_donor = ("", 0)
        self._last_share_time.clear()
        self._gift_overflow.clear()
        self._captain_px.clear()

        # Save assignments before super() clears them, then restore so users
        # keep their country across races until they explicitly vote another.
        saved_assignments = dict(self.user_assignments)
        saved_cache      = dict(self.user_country_cache)
        super()._return_to_idle()
        self.user_assignments.update(saved_assignments)
        self.user_country_cache.update(saved_cache)

    # ── Capitán: quien más px hizo avanzar a su país (votos + gifts unificados) ──

    def _add_captain_px(self, country: str, username: str, px: float) -> None:
        per_country = self._captain_px.setdefault(country, {})
        per_country[username] = per_country.get(username, 0.0) + px

    def get_mvp_for_country(self, country: str) -> str:
        per_country = self._captain_px.get(country, {})
        if not per_country:
            return super().get_mvp_for_country(country)
        return max(per_country, key=per_country.__getitem__)

    # ── Gifts: escalar distancia a 0.33× del core ────────────────────────────────

    async def _handle_gift_event(self, event) -> None:
        if not self.physics_world:
            await super()._handle_gift_event(event)
            return
        before = {c: r.target_x for c, r in self.physics_world.racers.items()}
        await super()._handle_gift_event(event)
        username = self.sanitize_username(event.username or "")
        for country, racer in self.physics_world.racers.items():
            delta = racer.target_x - before.get(country, racer.target_x)
            if delta > 0:
                scaled_delta = delta * _COUNTRIES_GIFT_SCALE
                racer.target_x -= delta * (1.0 - _COUNTRIES_GIFT_SCALE)
                # Attribute scaled px to the sender for captain ranking
                if username:
                    self._add_captain_px(country, username, scaled_delta)
        self._queue_avatar_fetch(username, event.avatar_url)

    # ── Vote: corregir distancia para calibrar a 80-150 viewers ────────────────

    async def _handle_vote_event(self, event) -> None:
        username = self.sanitize_username(event.username or "")
        country  = event.content
        # Attribute px BEFORE super so get_mvp_for_country is current when core checks
        if username and country:
            self._add_captain_px(country, username, _COUNTRIES_VOTE_DIAMOND * 3.0)
        await super()._handle_vote_event(event)
        if self.physics_world and not self.physics_world.race_finished:
            if country and country in self.physics_world.racers:
                from core.config import COMMENT_POINTS_PER_MESSAGE, COMMENT_DISTANCE_MULTIPLIER
                core_dist = COMMENT_POINTS_PER_MESSAGE * COMMENT_DISTANCE_MULTIPLIER * 3.0
                our_dist  = _COUNTRIES_VOTE_DIAMOND * 3.0
                correction = core_dist - our_dist
                if correction > 0:
                    self.physics_world.racers[country].target_x -= correction
        self._queue_avatar_fetch(username, event.avatar_url)

    # ── Follow / Share / Quiereme ─────────────────────────────────────────────

    async def _handle_event(self, event) -> None:
        if event.type == EventType.SHARE:
            await self._handle_countries_share(event)
            return
        if event.type == EventType.GIFT:
            gift_name = (event.content or '').lower().strip()
            if gift_name in _QUIEREME_NAMES:
                await self._handle_countries_quiereme(event)
                return
        await super()._handle_event(event)

    def _resolve_country(self, username: str) -> str | None:
        """Voted country first, auto-balance fallback."""
        country = self.user_assignments.get(username)
        if not country or country not in self.physics_world.racers:
            country, _ = self.assign_country_to_user(username)
        return country if country in self.physics_world.racers else None

    async def _handle_follow_event(self, event) -> None:
        await super()._handle_follow_event(event)
        if self.game_state != 'RACING' or self.physics_world is None:
            return
        username = self.sanitize_username(event.username or 'someone')
        country = self._resolve_country(username)
        if country:
            self.physics_world.apply_gift_impulse(country, 'follow', _COUNTRIES_FOLLOW_DISTANCE)
            self.spawn_floating_text(f"¡{username} nos sigue!", 0, 0, (100, 220, 255))

    async def _handle_countries_share(self, event) -> None:
        username = self.sanitize_username(event.username or 'someone')
        now = time.perf_counter()
        if now - self._last_share_time.get(username, 0.0) < _COUNTRIES_SHARE_COOLDOWN:
            return
        self._last_share_time[username] = now

        self._on_real_activity()
        if self.game_state == 'IDLE':
            self._transition_to_racing()
        if self.game_state != 'RACING' or self.physics_world is None:
            return
        country = self._resolve_country(username)
        if country:
            self.physics_world.apply_gift_impulse(country, 'share', _COUNTRIES_SHARE_DISTANCE)
            self.spawn_floating_text(f"¡{username} compartió!", 0, 0, (100, 255, 180))
            logger.info("Share: %s → %s", username, country)

    async def _handle_countries_quiereme(self, event) -> None:
        self._on_real_activity()
        if self.game_state == 'IDLE':
            self._transition_to_racing()
        if self.game_state != 'RACING' or self.physics_world is None:
            return
        username = self.sanitize_username(event.username or 'someone')
        country, _ = self._get_user_country_with_autojoin(username, event.content or '')
        if country and country in self.physics_world.racers:
            self.physics_world.apply_gift_impulse(country, 'quiereme', _COUNTRIES_QUIEREME_DISTANCE)
            self._on_gift_processed(username, country, _COUNTRIES_QUIEREME_DISTANCE)
            self.spawn_floating_text(f"¡{username} nos quiere!", 0, 0, (255, 100, 180))
            logger.info("Quiereme: %s → %s", username, country)

    # ── AutoPilot overrides ───────────────────────────────────────────────────

    async def _autopilot_combat_event(self) -> None:
        if self.physics_world.race_finished:
            return
        lb = self.physics_world.get_leaderboard()
        if not lb:
            return
        leader = lb[0][1]
        result = self.physics_world.apply_gift_effect("Helado", leader)
        if result['effect'] == 'freeze':
            _lr = self.physics_world.racers.get(leader)
            _lx = _lr.body.position.x if _lr else 0.0
            _ly = _lr.body.position.y if _lr else 0.0
            self.spawn_floating_text(f"¡Detengan a {leader}!", _lx, _ly, (130, 220, 255))
        self.screen_shaker.impact_shake()

    async def _autopilot_terremoto(self) -> None:
        countries = list(self.physics_world.racers.keys())
        if not countries:
            return
        lb = self.physics_world.get_leaderboard()
        leader = lb[0][1] if lb else ""
        VIVID = [(255, 80, 0), (0, 220, 255), (255, 0, 200), (80, 255, 60), (255, 220, 0)]
        for country in countries:
            racer = self.physics_world.racers[country]
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            self.emit_explosion(pos=pos, color=random.choice(VIVID), count=30, power=1.8)
        if leader:
            self.spawn_floating_text(f"¡{leader} lidera!", 0, 0, (255, 200, 0))

    async def _autopilot_arcoiris(self) -> None:
        lb = self.physics_world.get_leaderboard()
        if not lb:
            return
        RAINBOW = [
            (255, 0, 0), (255, 127, 0), (255, 215, 0),
            (0, 200, 60), (0, 180, 255), (100, 0, 255), (255, 0, 200),
        ]
        for i, (_, country, *_rest) in enumerate(lb):
            racer = self.physics_world.racers.get(country)
            if racer is None:
                continue
            pos = (float(racer.body.position.x), float(racer.body.position.y))
            self.emit_explosion(pos=pos, color=RAINBOW[i % len(RAINBOW)], count=28, power=1.6)
            await asyncio.sleep(0.06)
        self.screen_shaker.big_impact_shake()

    async def _autopilot_tormenta(self) -> None:
        pass  # disabled in Countries variant

    async def _autopilot_lunar_event(self) -> None:
        if self._lunar_active:
            return
        duration  = max(8.0,  min(20.0, random.gauss(14.0, 3.0)))
        amplitude = max(6.0,  min(12.0, random.gauss(9.0,  1.5)))
        self._activate_lunar_gravity(duration=duration, amplitude=amplitude)
        self.spawn_floating_text("¡Todos flotan!", 0, 0, (180, 180, 255))
