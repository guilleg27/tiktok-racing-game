"""
Retro stadium LED scoreboard rendering for Versus mode.

Pure drawing API (no TikTok / event logic). Fonts are injected so tests can mock
``pygame.font.Font`` and CI can run without bundled TTF files.

Visual target: dark matte face, metallic frame, team names + mini badges,
golden center scores (Tablero-style reference).
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

import pygame


def _ease_out_cubic(t: float) -> float:
    """Ease-out cubic in 0..1.

    Args:
        t: Linear progress clamped to [0, 1].

    Returns:
        Smoothed value in [0, 1].
    """
    t = max(0.0, min(1.0, t))
    p = 1.0 - t
    return 1.0 - p * p * p


def _draw_text_glow(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: Tuple[int, int, int],
    glow_rgb: Tuple[int, int, int],
    center: Tuple[int, int],
    layers: int = 4,
) -> None:
    """Draw label text with soft outer glow using offset blits.

    Args:
        surface: Destination surface.
        text: UTF-8 string to render.
        font: Font used for rendering.
        color: Main glyph RGB.
        glow_rgb: Glow tint RGB (semi-transparent copies).
        center: Pixel center (cx, cy) for the final text.
        layers: Number of outward glow steps.
    """
    cx, cy = center
    for i in range(layers, 0, -1):
        off = i
        alpha = max(8, 35 - i * 7)
        g_surf = font.render(text, True, glow_rgb)
        g_surf.set_alpha(alpha)
        for dx, dy in (
            (-off, 0),
            (off, 0),
            (0, -off),
            (0, off),
            (-off, -off),
            (off, off),
            (-off, off),
            (off, -off),
        ):
            surface.blit(g_surf, (cx - g_surf.get_width() // 2 + dx, cy - g_surf.get_height() // 2 + dy))
    main = font.render(text, True, color)
    surface.blit(main, (cx - main.get_width() // 2, cy - main.get_height() // 2))


def _draw_led_digit_block(
    surface: pygame.Surface,
    digit_text: str,
    font: pygame.font.Font,
    base_color: Tuple[int, int, int],
    glow_color: Tuple[int, int, int],
    center: Tuple[int, int],
    pulse_strength: float,
) -> pygame.Rect:
    """Draw a score digit with LED-style glow and optional hit pulse scale."""
    ease = _ease_out_cubic(pulse_strength)
    scale_boost = 1.0 + 0.12 * ease
    tint_add = int(40 * ease)

    def _clamp_c(c: int) -> int:
        return min(255, c + tint_add)

    lit_color = (_clamp_c(base_color[0]), _clamp_c(base_color[1]), _clamp_c(base_color[2]))

    raw = font.render(digit_text, True, lit_color)
    w, h = raw.get_size()
    if pulse_strength > 0.001:
        nw = max(1, int(w * scale_boost))
        nh = max(1, int(h * scale_boost))
        scaled = pygame.transform.smoothscale(raw, (nw, nh))
        rect = scaled.get_rect(center=center)
        surface.blit(scaled, rect)
        return raw.get_rect(center=center)
    _draw_text_glow(surface, digit_text, font, lit_color, glow_color, center, layers=4)
    r = raw.get_rect(center=center)
    surface.blit(raw, r)
    return r


class VersusRetroScoreboard:
    """Matte-black LED panel with metallic frame, team headers, and golden scores."""

    def __init__(
        self,
        score_font: pygame.font.Font,
        label_font: pygame.font.Font,
        timer_font: pygame.font.Font,
        *,
        corner_radius: int = 10,
        left_badge: Optional[pygame.Surface] = None,
        right_badge: Optional[pygame.Surface] = None,
    ) -> None:
        """Initialize cached fonts, corner geometry, and optional badge images.

        Args:
            score_font: Large font for numeric scores (dot-matrix preferred).
            label_font: Font for team names (RIVER / BOCA) on the board.
            timer_font: Font for clock / status line.
            corner_radius: Rounded rectangle radius for the outer panel.
            left_badge: Pre-scaled badge Surface for the left team, or None.
            right_badge: Pre-scaled badge Surface for the right team, or None.
        """
        self._score_font = score_font
        self._label_font = label_font
        self._timer_font = timer_font
        self._corner_radius = corner_radius
        self._label_font_base_size: int = label_font.size("A")[1]
        self._asset_manager = None   # injected by load_versus_scoreboard_fonts
        self._left_badge = left_badge
        self._right_badge = right_badge

    def draw(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        *,
        left_team_upper: str,
        right_team_upper: str,
        s_left: int,
        s_right: int,
        timer_text: Optional[str],
        timer_color: Tuple[int, int, int],
        golden_goal_row: bool,
        anim_time: float,
        dt: float,
        pulse_left: float,
        pulse_right: float,
        river_name_color: Tuple[int, int, int],
        river_name_glow: Tuple[int, int, int],
        boca_name_color: Tuple[int, int, int],
        boca_name_glow: Tuple[int, int, int],
        score_led_color: Tuple[int, int, int] = (255, 212, 72),
        score_glow_color: Tuple[int, int, int] = (170, 110, 35),
        fans_left: int = 0,
        fans_right: int = 0,
    ) -> None:
        """Draw the full scoreboard into ``rect`` on ``surface``."""
        _ = dt
        self._draw_panel(surface, rect)

        inner = rect.inflate(-12, -2)
        mid_x = inner.centerx
        y = inner.top + 2

        # ── Row 1: team labels ──────────────────────────────────────────────
        lu = left_team_upper.upper()
        ru = right_team_upper.upper()

        # Auto-shrink font until both names fit side-by-side with a 12 px gap.
        label_font = self._label_font
        max_label_w = (inner.width - 24) // 2   # half the inner width minus margins
        current_size = self._label_font_base_size
        for _ in range(8):
            lw, lh = label_font.size(lu)
            rw, rh = label_font.size(ru)
            if lw <= max_label_w and rw <= max_label_w:
                break
            current_size = max(12, current_size - 4)
            if self._asset_manager is not None:
                label_font = self._asset_manager.get_versus_digital_font(current_size)
            else:
                label_font = pygame.font.SysFont("Arial", current_size, bold=True)

        lw, lh = label_font.size(lu)
        rw, rh = label_font.size(ru)
        label_row_h = max(lh, rh)
        _draw_text_glow(
            surface, lu, label_font, river_name_color, river_name_glow,
            (inner.left + 12 + lw // 2, y + label_row_h // 2), layers=3,
        )
        _draw_text_glow(
            surface, ru, label_font, boca_name_color, boca_name_glow,
            (inner.right - 12 - rw // 2, y + label_row_h // 2), layers=3,
        )
        y += label_row_h + 2

        # ── Row 2: badge + score + badge — all on the same horizontal band ──
        badge_h = 32
        badge_w = 32
        if self._left_badge:
            badge_w = self._left_badge.get_width()
            badge_h = self._left_badge.get_height()
        if self._right_badge:
            badge_w = max(badge_w, self._right_badge.get_width())
            badge_h = max(badge_h, self._right_badge.get_height())

        sh = self._score_font.get_height()
        row2_h = max(badge_h, sh)
        row2_cy = y + row2_h // 2

        # Left badge: anchored to left edge, vertically centred in row
        if self._left_badge:
            bx = inner.left + 6
            by = row2_cy - badge_h // 2
            surface.blit(self._left_badge, (bx, by))
            digit_gap_l = bx + badge_w + 8
        else:
            self._draw_mini_team_badge(surface, inner.left + badge_w // 2 + 6, row2_cy, badge_h // 2, river=True)
            digit_gap_l = inner.left + badge_w + 14

        # Right badge: anchored to right edge
        if self._right_badge:
            bx = inner.right - badge_w - 6
            by = row2_cy - badge_h // 2
            surface.blit(self._right_badge, (bx, by))
            digit_gap_r = bx - 8
        else:
            self._draw_mini_team_badge(surface, inner.right - badge_w // 2 - 6, row2_cy, badge_h // 2, river=False)
            digit_gap_r = inner.right - badge_w - 14

        # Digits: centred in the space between the two badges
        score_zone_cx = (digit_gap_l + digit_gap_r) // 2
        lc = (score_zone_cx - 46, row2_cy)
        rc = (score_zone_cx + 46, row2_cy)
        ls = str(int(s_left))
        rs = str(int(s_right))
        _draw_led_digit_block(surface, ls, self._score_font, score_led_color, score_glow_color, lc, pulse_left)
        _draw_led_digit_block(surface, rs, self._score_font, score_led_color, score_glow_color, rc, pulse_right)

        y += row2_h + 2

        if timer_text:
            th = self._timer_font.get_height()
            tg = (min(255, timer_color[0] + 40), min(255, timer_color[1] + 30), min(255, timer_color[2] + 20))
            _draw_text_glow(
                surface,
                timer_text,
                self._timer_font,
                timer_color,
                tg,
                (mid_x, y + th // 2),
                layers=2,
            )
            y += th + 1

        if golden_goal_row:
            alpha = int(180 + 75 * math.sin(anim_time * 5.0))
            alpha = max(120, min(255, alpha))
            msg = "GOL DE ORO"
            g_surf = self._timer_font.render(msg, True, (255, 210, 90))
            g_surf.set_alpha(alpha)
            gr = g_surf.get_rect(centerx=mid_x, top=y + 2)
            for ox, oy in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                halo = self._timer_font.render(msg, True, (200, 140, 40))
                halo.set_alpha(min(90, alpha // 2))
                surface.blit(halo, gr.move(ox, oy))
            surface.blit(g_surf, gr)
            y += self._timer_font.get_height() + 1

        # ── Fans row: session-wide keyword votes ─────────────────────────────
        fans_color = (130, 180, 255)
        lf_str = f"Fans: {fans_left}"
        rf_str = f"Fans: {fans_right}"
        lf_surf = self._timer_font.render(lf_str, True, fans_color)
        rf_surf = self._timer_font.render(rf_str, True, fans_color)
        fans_row_y = y + 2
        surface.blit(lf_surf, lf_surf.get_rect(left=inner.left + 6, centery=fans_row_y + lf_surf.get_height() // 2))
        surface.blit(rf_surf, rf_surf.get_rect(right=inner.right - 6, centery=fans_row_y + rf_surf.get_height() // 2))

        gloss = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pts = [
            (rect.width * 0.12, 0),
            (rect.width * 0.38, 0),
            (rect.width * 0.18, rect.height * 0.45),
            (0, rect.height * 0.35),
        ]
        pygame.draw.polygon(gloss, (255, 255, 255, 10), pts)
        surface.blit(gloss, rect.topleft)

    def _draw_panel(self, surface: pygame.Surface, rect: pygame.Rect) -> None:
        """Dark metallic frame around a flat black LED face."""
        pygame.draw.rect(
            surface,
            (32, 34, 40),
            rect,
            border_radius=self._corner_radius,
        )
        pygame.draw.rect(
            surface,
            (88, 90, 98),
            rect,
            width=1,
            border_radius=self._corner_radius,
        )
        face = rect.inflate(-8, -8)
        pygame.draw.rect(
            surface,
            (6, 6, 8),
            face,
            border_radius=max(3, self._corner_radius - 3),
        )
        inset = face.inflate(-4, -4)
        pygame.draw.rect(
            surface,
            (2, 2, 4),
            inset,
            border_radius=max(2, self._corner_radius - 4),
        )

    @staticmethod
    def _draw_mini_team_badge(
        surface: pygame.Surface,
        cx: int,
        cy: int,
        r: int,
        *,
        river: bool,
    ) -> None:
        """Small circular shield: River stripe on white, Boca stripe on blue."""
        d = r * 2 + 4
        s = pygame.Surface((d, d), pygame.SRCALPHA)
        ccx, ccy = d // 2, d // 2
        if river:
            pygame.draw.circle(s, (248, 248, 252), (ccx, ccy), r)
            pygame.draw.line(
                s,
                (215, 45, 55),
                (ccx - r + 2, ccy + r - 2),
                (ccx + r - 2, ccy - r + 2),
                max(2, r // 4),
            )
        else:
            pygame.draw.circle(s, (0, 72, 168), (ccx, ccy), r)
            stripe_h = max(3, r // 2)
            pygame.draw.rect(
                s,
                (255, 210, 55),
                (ccx - r, ccy - stripe_h // 2, r * 2, stripe_h),
            )
        pygame.draw.circle(s, (0, 0, 0, 200), (ccx, ccy), r, 1)
        surface.blit(s, (cx - ccx, cy - ccy))


def _load_badge(img_path: str, target_h: int) -> Optional[pygame.Surface]:
    """Load a PNG badge image and scale it to target_h preserving aspect ratio.

    Args:
        img_path: Absolute path to the PNG file (already resolved via resource_path).
        target_h: Desired height in pixels.

    Returns:
        Scaled RGBA Surface, or None if loading fails.
    """
    try:
        surf = pygame.image.load(img_path).convert_alpha()
        ow, oh = surf.get_size()
        if oh == 0:
            return None
        tw = max(1, int(ow * target_h / oh))
        return pygame.transform.smoothscale(surf, (tw, target_h))
    except Exception:
        return None


def load_versus_scoreboard_fonts(
    asset_manager,
    score_size: int = 58,
    label_size: int = 26,
    timer_size: int = 20,
    badge_height: int = 38,
    corner_radius: int = 10,
) -> VersusRetroScoreboard:
    """Build a scoreboard using dot-matrix fonts + PNG badge images.

    Args:
        asset_manager: Game ``AssetManager`` instance (provides ``get_versus_digital_font``
            and ``resource_path`` via its internal import).
        score_size: Pixel size for score digits.
        label_size: Pixel size for team name labels.
        timer_size: Pixel size for timer / Golden Goal text.
        badge_height: Target height (px) for the badge PNG images.
        corner_radius: Panel corner radius (should match config).

    Returns:
        Configured ``VersusRetroScoreboard`` instance.
    """
    from core.resources import resource_path
    import os
    import variants.versus.config as _vcfg

    score_font = asset_manager.get_versus_digital_font(score_size)
    label_font = asset_manager.get_versus_digital_font(max(14, label_size))
    timer_font = asset_manager.get_versus_digital_font(timer_size)

    # Resolve badge paths from the active matchup when available.
    matchup = getattr(_vcfg, "ACTIVE_MATCHUP", None)
    if matchup is not None:
        left_path_rel  = matchup.left.marcador_path or \
            os.path.join("assets", "versus", "images", f"marcador-{matchup.left.name.lower()}.png")
        right_path_rel = matchup.right.marcador_path or \
            os.path.join("assets", "versus", "images", f"marcador-{matchup.right.name.lower()}.png")
    else:
        left_path_rel  = os.path.join("assets", "versus", "images", "marcador-river.png")
        right_path_rel = os.path.join("assets", "versus", "images", "marcador-boca.png")

    left_badge  = _load_badge(resource_path(os.path.normpath(left_path_rel)),  badge_height)
    right_badge = _load_badge(resource_path(os.path.normpath(right_path_rel)), badge_height)

    sb = VersusRetroScoreboard(
        score_font,
        label_font,
        timer_font,
        corner_radius=corner_radius,
        left_badge=left_badge,
        right_badge=right_badge,
    )
    sb._asset_manager = asset_manager
    return sb
