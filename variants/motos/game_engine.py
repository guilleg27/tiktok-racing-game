"""MotoGP variant game engine — extends core GameEngine with a custom victory screen.

Victory screen features:
- Video background (assets/motos/videos/festejo.mp4) via OpenCV
- Winner country flag + name
- Stat cards: TOP VOTADOR / TOP DONADOR
- Countdown bar to next race
- No final-classification table
"""

from __future__ import annotations

import logging
import math
import os
import threading
import time
from typing import Optional

import pygame

from core.game_engine import GameEngine, _get_font, _safe_render
from src.resources import resource_path

logger = logging.getLogger(__name__)

try:
    import cv2
    import numpy as np
    _CV2_AVAILABLE = True
except ImportError:
    _CV2_AVAILABLE = False
    logger.warning("[MotosGE] opencv-python not installed — victory video disabled")


# ---------------------------------------------------------------------------
# Video player
# ---------------------------------------------------------------------------

class _MotosVideoPlayer:
    """Background-thread video player that exposes the current frame as a pygame Surface.

    Reads an mp4 file with OpenCV, loops it, and stores the latest frame
    in a thread-safe buffer.  The render loop calls get_current_frame() to
    retrieve whatever is available without blocking.
    """

    def __init__(self, path: str, fps: float = 30.0) -> None:
        """Initialize the player (does not start playback yet).

        Args:
            path: Absolute path to the video file.
            fps: Target playback frame rate.
        """
        self._path = path
        self._fps = fps
        self._lock = threading.Lock()
        self._current_frame: Optional[pygame.Surface] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None

    # ------------------------------------------------------------------
    def start(self) -> None:
        """Start the background reader thread."""
        if not _CV2_AVAILABLE:
            return
        self._running = True
        self._thread = threading.Thread(target=self._read_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the reader thread to stop and wait for it."""
        self._running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
        with self._lock:
            self._current_frame = None

    def get_current_frame(self) -> Optional[pygame.Surface]:
        """Return the most recently decoded frame (thread-safe, non-blocking).

        Returns:
            A pygame Surface or None if no frame is ready yet.
        """
        with self._lock:
            return self._current_frame

    # ------------------------------------------------------------------
    def _read_loop(self) -> None:
        """Main loop executed on the background thread."""
        cap = cv2.VideoCapture(self._path)  # type: ignore[attr-defined]
        if not cap.isOpened():
            logger.warning("[MotosVideoPlayer] Cannot open video: %s", self._path)
            return

        video_fps = cap.get(cv2.CAP_PROP_FPS) or self._fps  # type: ignore[attr-defined]
        frame_delay = 1.0 / max(1.0, video_fps)

        while self._running:
            ret, frame = cap.read()
            if not ret:
                # Loop: rewind to the beginning
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # type: ignore[attr-defined]
                continue

            # Convert BGR → RGB numpy array → pygame Surface
            try:
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)  # type: ignore[attr-defined]
                surface = pygame.surfarray.make_surface(rgb.swapaxes(0, 1))
                with self._lock:
                    self._current_frame = surface
            except Exception as exc:
                logger.debug("[MotosVideoPlayer] Frame conversion error: %s", exc)

            time.sleep(frame_delay)

        cap.release()


# ---------------------------------------------------------------------------
# MotosGameEngine
# ---------------------------------------------------------------------------

class MotosGameEngine(GameEngine):
    """GameEngine subclass for the MotoGP variant.

    Overrides:
    - _render_leaderboard: suppressed (no final classification table).
    - _trigger_victory_sequence: computes top-voter / top-donor stats and
      starts the video player.
    - _render_victory_sequence: completely new victory screen design.
    - _return_to_idle: cleans up counters and video player.
    - _on_gift_processed / _on_vote_processed: accumulate per-user stats.
    """

    def __init__(self, *args, **kwargs) -> None:
        """Initialize parent and add motos-specific state."""
        super().__init__(*args, **kwargs)

        # Per-user accumulators (reset each race)
        self._comment_counts: dict[str, int] = {}
        self._diamond_totals: dict[str, int] = {}

        # Victory stats (set at the moment the race ends)
        self._victory_top_commenter: tuple[str, int] = ("", 0)
        self._victory_top_donor: tuple[str, int] = ("", 0)

        # Video player (created fresh for each victory)
        self._video_player: Optional[_MotosVideoPlayer] = None

        # Scaled video frame cache (avoids repeated scaling per render call)
        self._video_frame_cache: Optional[pygame.Surface] = None
        self._video_frame_source_id: int = 0  # id() of last source frame

    # ------------------------------------------------------------------
    # Stat hooks (called by core event handlers)
    # ------------------------------------------------------------------

    def _on_gift_processed(self, username: str, country: str, diamonds: int) -> None:
        """Track total diamonds per user across all countries.

        Args:
            username: TikTok username of the sender.
            country: Country the gift was assigned to.
            diamonds: Total diamond value (diamond_count * gift_count).
        """
        if username:
            self._diamond_totals[username] = (
                self._diamond_totals.get(username, 0) + diamonds
            )

    def _on_vote_processed(self, username: str, country: str) -> None:
        """Track total vote count per user across all countries.

        Args:
            username: TikTok username of the voter.
            country: Country the vote was assigned to.
        """
        if username:
            self._comment_counts[username] = (
                self._comment_counts.get(username, 0) + 1
            )

    # ------------------------------------------------------------------
    # Suppress leaderboard table
    # ------------------------------------------------------------------

    def _render_leaderboard(self) -> None:
        """No-op: the motos variant does not show the final classification table."""

    # ------------------------------------------------------------------
    # Floating text font override
    # ------------------------------------------------------------------

    _FLOATING_FONT = "avenirnextcondensed"  # falls back to nearest SysFont match

    def _render_floating_texts(self) -> None:
        """Inject condensed font into every floating text before drawing."""
        for t in self.floating_texts:
            t.font_name = self._FLOATING_FONT
        super()._render_floating_texts()

    # ------------------------------------------------------------------
    # Moto-in-motion: suspension bounce + forward lean
    # ------------------------------------------------------------------

    _MOTO_BOUNCE_AMP   = 0.7   # px — vertical suspension oscillation
    _MOTO_BOUNCE_HZ    = 9.0   # rad/s — fast enough to feel like road vibration
    _MOTO_LEAN_DEG     = 5.0   # degrees clockwise — constant forward lean

    def _render_racer(self, racer, is_winner: bool = False) -> None:
        """Override: add suspension bounce + forward lean before delegating to super."""
        phase = self.leader_glow_time * self._MOTO_BOUNCE_HZ + racer.lane * 0.8
        y_bump = math.sin(phase) * self._MOTO_BOUNCE_AMP

        old_y_offset = getattr(racer, "y_offset", 0.0)
        old_angle    = racer.body.angle

        racer.y_offset    = old_y_offset + y_bump
        racer.body.angle  = math.radians(self._MOTO_LEAN_DEG)

        super()._render_racer(racer, is_winner)

        racer.y_offset   = old_y_offset
        racer.body.angle = old_angle

    # ------------------------------------------------------------------
    # Country badge — circle with 3-letter abbrev to the left of each moto
    # ------------------------------------------------------------------

    def _render_captain_label(self, racer, flag_x: int, flag_y: int) -> None:
        """No-op: captain shown in the lane badge to the left of the moto."""

    def _render_neon_lane_labels(self) -> None:
        """Render neon country name (center, via super) + clean captain pill (left of moto)."""
        super()._render_neon_lane_labels()  # original neon label in the center

        from core.config import COUNTRY_ABBREV

        # Modern condensed font — DIN/Avenir feel, falls back gracefully
        font = _get_font("Arial", 11, bold=False)
        gap = 4
        pad_x, pad_y = 5, 2

        for country, racer in self.physics_world.get_racers().items():
            rx = float(racer.body.position.x)
            ry = float(racer.body.position.y + (racer.y_offset if hasattr(racer, "y_offset") else 0.0))

            captain = self.current_captains.get(country, "")
            is_new  = bool(captain) and country in self.captain_change_timer
            label   = captain[:9] if captain else COUNTRY_ABBREV.get(country, country[:3].upper())

            text_w, text_h = font.size(label)
            pill_w = text_w + pad_x * 2
            pill_h = text_h + pad_y * 2
            radius = pill_h // 2

            sprite_half_w = racer.sprite.get_width() // 2 if racer.sprite else self.physics_world.lane_height
            pill_right = int(rx - sprite_half_w - gap)
            pill_left  = max(2, pill_right - pill_w)

            # No glow needed — clean black pill
            surf_w = pill_w + 4
            surf_h = pill_h + 4
            s  = pygame.Surface((surf_w, surf_h), pygame.SRCALPHA)
            cx = surf_w // 2
            cy = surf_h // 2
            pill_rect = pygame.Rect(cx - pill_w // 2, cy - pill_h // 2, pill_w, pill_h)

            # Black fill
            pygame.draw.rect(s, (0, 0, 0, 210), pill_rect, border_radius=radius)

            # White border (gold flash for new captain)
            border_col = (255, 215, 0) if is_new else (255, 255, 255)
            pygame.draw.rect(s, (*border_col, 220), pill_rect, width=1, border_radius=radius)

            # White text (gold for new captain)
            text_col  = (255, 215, 0) if is_new else (255, 255, 255)
            text_surf = font.render(label, True, text_col)
            s.blit(text_surf, (cx - text_w // 2, cy - text_h // 2))

            self.render_surface.blit(s, (pill_left - 2, int(ry) - surf_h // 2))

    # ------------------------------------------------------------------
    # Victory trigger
    # ------------------------------------------------------------------

    def _trigger_victory_sequence(
        self, winner_country: str, winner_captain: str
    ) -> None:
        """Compute race stats, start video, then delegate to parent.

        Args:
            winner_country: The winning country name.
            winner_captain: Username of the winning country's captain.
        """
        # Snapshot top commenter
        if self._comment_counts:
            top_u = max(self._comment_counts, key=self._comment_counts.get)  # type: ignore[arg-type]
            self._victory_top_commenter = (top_u, self._comment_counts[top_u])
        else:
            self._victory_top_commenter = ("", 0)

        # Snapshot top donor
        if self._diamond_totals:
            top_d = max(self._diamond_totals, key=self._diamond_totals.get)  # type: ignore[arg-type]
            self._victory_top_donor = (top_d, self._diamond_totals[top_d])
        else:
            self._victory_top_donor = ("", 0)

        # Start video
        self._stop_video()
        video_path = resource_path("assets/motos/videos/festejo.mp4")
        self._video_player = _MotosVideoPlayer(video_path)
        self._video_player.start()

        super()._trigger_victory_sequence(winner_country, winner_captain)

        # Replace core victory.wav with the moto-specific track
        self.audio_manager.stop_victory_sound()
        try:
            mp3_path = resource_path(os.path.join("assets", "audio", "victory_moto.mp3"))
            pygame.mixer.music.load(mp3_path)
            pygame.mixer.music.set_volume(0.65)
            pygame.mixer.music.play(-1)  # loop until victory ends
        except Exception as exc:
            logger.warning(f"[MotosGE] victory_moto.mp3 could not play: {exc}")

    def on_physics_race_reset(self) -> None:
        """Stop moto victory music before delegating to core."""
        pygame.mixer.music.stop()
        super().on_physics_race_reset()

    # ------------------------------------------------------------------
    # Victory screen render
    # ------------------------------------------------------------------

    def _render_victory_sequence(self) -> None:
        """Render the motos victory screen (overrides core epic-sequence design).

        Layout (top → bottom, centred horizontally):
        1. Video frame as background (alpha-blended)
        2. Dark overlay
        3. Radial glow in winner colour
        4. Winner flag sprite (large, bouncing) + country name
        5. Two stat cards: TOP VOTADOR | TOP DONADOR
        6. Countdown bar
        """
        if not self.victory_sequence_active:
            return

        from core.config import SCREEN_WIDTH, SCREEN_HEIGHT, COUNTRY_ABBREV

        surface = self.render_surface
        sw, sh = SCREEN_WIDTH, SCREEN_HEIGHT
        cx = sw // 2
        t = self.victory_sequence_time
        # fade-in: 0→1 over 0.4 s — used only for the entry black overlay
        f = min(1.0, t * 2.5)

        winner = self.physics_world.winner
        if not winner:
            return

        # Winner colour (racer colour)
        racer = self.physics_world.racers.get(winner)
        w_accent: tuple = racer.color if racer else (255, 215, 0)

        # ── 0. Confetti (behind everything) ──────────────────────────────
        self._render_confetti()

        from core.config import GAME_AREA_TOP, GAME_AREA_BOTTOM
        play_top    = GAME_AREA_TOP                    # y where the race tracks start
        play_bottom = sh - GAME_AREA_BOTTOM            # y where the race tracks end
        play_h      = play_bottom - play_top           # usable height
        play_cy     = play_top + play_h // 2           # vertical centre of usable area

        # ── 1. Video background — only in the usable race area ────────────
        self._blit_video_background(
            surface, sw, play_h,
            dest_y=play_top,
            alpha=int(255 * min(1.0, t * 2.5)),
        )

        # ── 2. Subtle dark overlay confined to the race area ──────────────
        ov = pygame.Surface((sw, play_h), pygame.SRCALPHA)
        ov.fill((0, 0, 0, 90))
        surface.blit(ov, (0, play_top))

        # ── 3. Radial glow centred on the race area ───────────────────────
        pulse = 0.65 + 0.35 * math.sin(t * 2.5)
        glow_surf = pygame.Surface((sw, sh), pygame.SRCALPHA)
        for i in range(6, 0, -1):
            radius = 70 + i * 40
            alpha = int(pulse * (14 - i * 2))
            if alpha > 0:
                pygame.draw.circle(
                    glow_surf, (*w_accent[:3], alpha), (cx, play_cy), radius
                )
        surface.blit(glow_surf, (0, 0))

        # ── Content block — centred within the usable race area ──────────
        CONTENT_H = 420
        y = max(play_top + 8, play_cy - CONTENT_H // 2)

        # ── 4a. Winner moto — styled panel ───────────────────────────────
        panel_w = int(sw * 0.74)
        panel_h = 120
        panel_x = cx - panel_w // 2
        panel_y = y

        # Background panel: dark with a subtle winner-colour tint
        panel_surf = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        r0, g0, b0 = w_accent[0], w_accent[1], w_accent[2]
        for row in range(panel_h):
            # Very slight vertical gradient — slightly lighter at centre
            center_factor = 1.0 - abs(row / panel_h - 0.5) * 0.6
            rv = int(8  + r0 * 0.05 * center_factor)
            gv = int(8  + g0 * 0.05 * center_factor)
            bv = int(16 + b0 * 0.08 * center_factor)
            pygame.draw.line(panel_surf, (rv, gv, bv, 210), (0, row), (panel_w, row))

        # Rounded accent border
        pygame.draw.rect(panel_surf, (*w_accent[:3], 130),
                         (0, 0, panel_w, panel_h), 2, border_radius=14)
        # Inner highlight line at top for depth
        pygame.draw.line(panel_surf, (255, 255, 255, 30), (14, 1), (panel_w - 14, 1))

        surface.blit(panel_surf, (panel_x, panel_y))

        # Moto sprite — centred inside the panel
        moto_h = 90
        entry  = min(1.0, t * 3.0)
        bounce = 1.0 + 0.04 * math.sin(t * 3.8)
        moto_surf = self.asset_manager.get_sprite_for_racer(winner, moto_h)
        if moto_surf and entry > 0.05:
            draw_h = max(1, int(moto_h * bounce * entry))
            draw_w = max(1, int(moto_surf.get_width() * draw_h / moto_h))
            scaled = pygame.transform.smoothscale(moto_surf, (draw_w, draw_h))
            surface.blit(scaled, scaled.get_rect(
                centerx=cx, centery=panel_y + panel_h // 2))

        y = panel_y + panel_h + 12

        # ── 4b. Country name ──────────────────────────────────────────────
        title_text = f"¡{winner.upper()} GANA!"
        title_font = _get_font("Arial", 40, bold=True)

        pulse_gold = (255, int(200 + 55 * math.sin(t * 6)), int(50 * abs(math.sin(t * 4))))

        # Shadow for legibility
        shadow_surf = title_font.render(title_text, True, (0, 0, 0))
        surface.blit(shadow_surf, shadow_surf.get_rect(centerx=cx + 2, centery=y + title_font.get_height() // 2 + 2))
        title_surf = title_font.render(title_text, True, pulse_gold)
        surface.blit(title_surf, title_surf.get_rect(centerx=cx, centery=y + title_font.get_height() // 2))
        y += title_font.get_height() + 8

        # Captain line
        captain = self.victory_winner_captain
        if captain and captain != "Unknown":
            cap_font = _get_font("Arial", 17, bold=True)
            cap_text = f"CAMPEON DEL CHAT: @{captain}"
            cap_shadow = cap_font.render(cap_text, True, (0, 0, 0))
            surface.blit(cap_shadow, cap_shadow.get_rect(centerx=cx + 1, centery=y + cap_font.get_height() // 2 + 1))
            cap_surf = cap_font.render(cap_text, True, (210, 210, 255))
            surface.blit(cap_surf, cap_surf.get_rect(centerx=cx, centery=y + cap_font.get_height() // 2))
            y += cap_font.get_height() + 8

        # Separator line
        pygame.draw.line(surface, (255, 255, 255, 60), (cx - int(sw * 0.35), y), (cx + int(sw * 0.35), y))
        y += 10

        # ── 5. Stat cards ─────────────────────────────────────────────────
        card_w = int(sw * 0.42)
        card_h = 84
        pad = 8
        card_l_x = cx - card_w - pad // 2
        card_r_x = cx + pad // 2

        lbl_font  = _get_font("Arial", 13, bold=True)
        user_font = _get_font("Arial", 15, bold=True)
        sub_font  = _get_font("Arial", 12, bold=False)

        def _stat_card(
            x: int,
            cy_top: int,
            title: str,
            username: str,
            value: int,
            value_label: str,
            accent: tuple,
        ) -> None:
            cs = pygame.Surface((card_w, card_h), pygame.SRCALPHA)
            for i in range(card_h):
                ratio = i / card_h
                r = int(12 + accent[0] * 0.06 * (1 - ratio * 0.5))
                g = int(12 + accent[1] * 0.06 * (1 - ratio * 0.5))
                b = int(22 + accent[2] * 0.08 * (1 - ratio * 0.5))
                pygame.draw.line(cs, (r, g, b, 185), (0, i), (card_w, i))
            pygame.draw.rect(
                cs, (*accent[:3], 180),
                (0, 0, card_w, card_h), 1, border_radius=6
            )
            # Title — render directly without set_alpha
            t_s = lbl_font.render(title, True, accent[:3])
            cs.blit(t_s, (8, 6))
            if username:
                # Shadow pass
                u_shadow = user_font.render(f"@{username}", True, (0, 0, 0))
                cs.blit(u_shadow, (9, 25))
                u_s = user_font.render(f"@{username}", True, (240, 240, 240))
                cs.blit(u_s, (8, 24))
                v_s = sub_font.render(f"{value:,} {value_label}", True, (180, 180, 180))
                cs.blit(v_s, (8, 54))
            else:
                nd = lbl_font.render("sin datos", True, (100, 100, 100))
                cs.blit(nd, (8, 32))
            surface.blit(cs, (x, cy_top))

        commenter_user, commenter_count = self._victory_top_commenter
        donor_user, donor_diamonds = self._victory_top_donor

        _stat_card(
            card_l_x, y,
            "TOP VOTADOR",
            commenter_user, commenter_count, "votos",
            (100, 180, 255),  # Blue accent
        )
        _stat_card(
            card_r_x, y,
            "TOP DONADOR",
            donor_user, donor_diamonds, "diamantes",
            (255, 215, 0),   # Gold accent
        )
        y += card_h + 14

        # ── 6. Countdown bar (30 s total victory window) ──────────────────
        VICTORY_TOTAL = 30.0
        remaining = max(0.0, VICTORY_TOTAL - self.winner_animation_time)
        progress = remaining / VICTORY_TOTAL

        bar_w = int(sw * 0.62)
        bar_h = 5
        bx = cx - bar_w // 2

        pygame.draw.rect(surface, (55, 55, 55), (bx, y, bar_w, bar_h))
        fill_w = int(bar_w * progress)
        if fill_w > 2:
            fc = (80, 210, 110) if remaining > 8 else (255, 130, 50)
            pygame.draw.rect(surface, fc, (bx, y, fill_w, bar_h))

        y += bar_h + 6
        cd_font = _get_font("Arial", 14, bold=True)
        cd_color = (80, 210, 110) if remaining > 8 else (255, 130, 50)
        cd_text = (
            f"Nueva carrera en {int(remaining) + 1}s..."
            if remaining > 0
            else "Preparando..."
        )
        # Shadow for countdown text
        cd_shadow = cd_font.render(cd_text, True, (0, 0, 0))
        surface.blit(cd_shadow, cd_shadow.get_rect(centerx=cx + 1, top=y + 1))
        cd_surf = cd_font.render(cd_text, True, cd_color)
        surface.blit(cd_surf, cd_surf.get_rect(centerx=cx, top=y))

        # ── 7. Entry fade-in overlay (black → transparent) ───────────────
        if f < 1.0:
            fade_ov = pygame.Surface((sw, play_h), pygame.SRCALPHA)
            fade_ov.fill((0, 0, 0, int(255 * (1.0 - f))))
            surface.blit(fade_ov, (0, play_top))

    # ------------------------------------------------------------------
    # Video helper
    # ------------------------------------------------------------------

    def _blit_video_background(
        self,
        surface: pygame.Surface,
        sw: int,
        sh: int,
        dest_y: int = 0,
        alpha: int = 255,
    ) -> None:
        """Blit the latest video frame scaled to (sw × sh) at position (0, dest_y).

        Args:
            surface: Destination surface.
            sw: Target width in pixels.
            sh: Target height in pixels (height of the destination rectangle).
            dest_y: Y offset on the destination surface where blitting starts.
            alpha: Opacity 0-255.
        """
        if not self._video_player:
            return
        raw = self._video_player.get_current_frame()
        if raw is None:
            return

        # Scale once per unique source frame + target size
        cache_key = (id(raw), sw, sh)
        src_id = id(raw)
        if src_id != self._video_frame_source_id or self._video_frame_cache is None:
            self._video_frame_cache = pygame.transform.smoothscale(raw, (sw, sh))
            self._video_frame_source_id = src_id

        frame = self._video_frame_cache.copy()
        frame.set_alpha(alpha)
        surface.blit(frame, (0, dest_y))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _stop_video(self) -> None:
        """Stop and release the current video player if one is running."""
        if self._video_player:
            self._video_player.stop()
            self._video_player = None
        self._video_frame_cache = None
        self._video_frame_source_id = 0

    def _return_to_idle(self) -> None:
        """Clean up motos stats and video, then delegate to parent."""
        pygame.mixer.music.stop()
        self._stop_video()
        self._comment_counts.clear()
        self._diamond_totals.clear()
        self._victory_top_commenter = ("", 0)
        self._victory_top_donor = ("", 0)
        super()._return_to_idle()

    def cleanup(self) -> None:
        """Stop video player on shutdown.

        Args: none — delegates to parent after cleanup.
        """
        self._stop_video()
        super().cleanup()
