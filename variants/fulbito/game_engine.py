"""
FulbitoGameEngine — subclase de GameEngine para el modo fulbito (4 carriles, Mundial 2026).

Sobrescribe la lógica que difiere del core:
  • 4 equipos por partido (no 12), fixture dinámico entre partidos
  • Sistema híbrido King + Crowd + Wildcard para selección de fixture
  • Carriles alternados (→ ← → ←), cada país corre en una dirección
  • Gifts van al equipo que va último (FULBITO_GIFT_TO_LAST)
  • Intermission con votación de chat entre partidos
  • Estadísticas de sesión acumuladas
"""

import asyncio
import logging
import math
import random
import time
from collections import deque
from typing import Optional

from core.game_engine import GameEngine, FloatingText
from core.events import EventType


class _GrassBackground:
    """Replaces BackgroundManager for fulbito — draws alternating grass stripes."""

    scroll_speed = 0.0  # core reads this via: self.original_parallax_speed = self.background_manager.scroll_speed

    def __init__(self, engine: "FulbitoGameEngine") -> None:
        self._engine = engine

    def render(self, surface) -> None:
        import pygame
        from core.config import GAME_AREA_TOP, SCREEN_WIDTH

        pw = self._engine.physics_world
        if pw is None:
            return

        lane_h = pw.lane_height
        lane_y_offset = pw.lane_y_offset
        num_lanes = len(self._engine.current_fixture) if self._engine.current_fixture else 4

        STRIPE_H = 10

        LANE_COLORS = [
            ((29, 82, 16), (35, 79, 20)),
            ((24, 86, 14), (29, 90, 18)),
            ((29, 82, 16), (35, 79, 20)),
            ((24, 86, 14), (29, 90, 18)),
        ]

        surface.fill((15, 15, 15))

        for i in range(num_lanes):
            dark, light = LANE_COLORS[i % len(LANE_COLORS)]
            lane_y = GAME_AREA_TOP + lane_y_offset + i * lane_h

            stripe_idx = 0
            y = lane_y
            while y < lane_y + lane_h:
                color = dark if stripe_idx % 2 == 0 else light
                stripe_bottom = min(y + STRIPE_H, lane_y + lane_h)
                pygame.draw.rect(surface, color, (0, y, SCREEN_WIDTH, stripe_bottom - y))
                y += STRIPE_H
                stripe_idx += 1

        for i in range(1, num_lanes):
            y = GAME_AREA_TOP + lane_y_offset + i * lane_h
            pygame.draw.line(surface, (20, 55, 8), (0, y), (SCREEN_WIDTH, y), 1)

        # Las franjas de los márgenes laterales (x=0..40 y x=500..540) se pintan
        # en outer_background via _update_outer_background() — no hace falta hacerlo aquí.

        # Tribuna rendering happens directly on self.screen in FulbitoGameEngine.render()
        # to cover the full ACTUAL_WIDTH (540px) instead of only render_surface (460px).

    def update(self, dt: float) -> None:
        pass

    def activate_hype_mode(self) -> None:
        pass

    def deactivate_hype_mode(self) -> None:
        pass

    def set_scroll_speed(self, speed: float) -> None:
        pass

    def activate_warp_mode(self) -> None:
        pass

    def deactivate_warp_mode(self) -> None:
        pass

    def activate_tension_mode(self) -> None:
        pass

    def deactivate_tension_mode(self) -> None:
        pass
from core.config import MAX_MESSAGES
from variants.fulbito.config import (
    FULBITO_DEFAULT_FIXTURE,
    FULBITO_ALL_COUNTRIES,
    FULBITO_RACE_COUNTRY_COUNT,
    FULBITO_INTERMISSION_SECONDS,
    FULBITO_CROWD_PICKS,
    resolve_alias,
)

logger = logging.getLogger(__name__)


class _StadiumTribuna:
    """Stadium crowd stands with perspective, wave, raised arms, and photo flashes.

    Rendering is cached to a pre-allocated SRCALPHA surface and refreshed at
    ~16 fps (every 60 ms) to avoid thousands of per-person Surface allocations
    on every game frame. People, arms, and seat-row lines are drawn directly
    onto the cached surface — zero Surface allocations per frame during blit.
    """

    CROWD_COLORS = [
        (231, 76,  60),  (52, 152, 219), (241, 196,  15),
        (46, 204, 113),  (230, 126,  34), (155,  89, 182),
        (255, 255, 255), (255, 152,   0), (233,  30,  99),
        (0,  188, 212),
    ]
    _CACHE_INTERVAL = 0.06   # seconds between full re-renders (~16 fps)

    def __init__(self, width: int, height: int):
        self.width  = width
        self.height = height
        self.time   = 0.0
        self._rng   = lambda s: abs(math.sin(s + 1) * 10000) % 1
        self._cache = None
        self._cache_flip: bool | None = None
        self._cache_timer: float = self._CACHE_INTERVAL  # render on first call
        self._flash_surf = None

    def update(self, dt: float) -> None:
        self.time += dt
        self._cache_timer += dt

    def render(self, surface, x: int, y: int, flip: bool = False) -> None:
        import pygame
        # Lazy-init cache and flash surfaces
        if self._cache is None:
            self._cache = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            self._flash_surf = pygame.Surface((20, 20), pygame.SRCALPHA)

        # Re-render cache only when interval elapses or flip direction changes
        if self._cache_timer >= self._CACHE_INTERVAL or self._cache_flip != flip:
            self._cache_timer = 0.0
            self._cache_flip  = flip
            self._render_to_cache(flip)

        surface.blit(self._cache, (x, y))

        # Camera flashes drawn live (low frequency, reuse _flash_surf)
        self._render_flashes(surface, x, y, flip)

    def _render_to_cache(self, flip: bool) -> None:
        import pygame
        c  = self._cache
        w, h = self.width, self.height
        t  = self.time

        c.fill((0, 0, 0, 0))

        # Gradient background — draw.line directly on SRCALPHA surface
        for row_y in range(h):
            progress = row_y / h if not flip else 1 - row_y / h
            r = int(5  + progress * 8)
            g = int(5  + progress * 15)
            b = int(16 + progress * 28)
            pygame.draw.line(c, (r, g, b, 255), (0, row_y), (w, row_y))

        # Seat-row lines — draw directly, no Surface alloc
        GRADE_COUNT = h // 8
        for g_idx in range(GRADE_COUNT):
            gy = h - g_idx * 8 - 4 if flip else g_idx * 8 + 4
            alpha = max(0, min(255, int(8 + g_idx * 2)))
            pygame.draw.line(c, (255, 255, 255, alpha), (0, gy), (w, gy))

        # People — all drawn directly on cache, zero Surface allocations
        ROWS = h // 9
        for row in range(ROWS):
            progress  = (ROWS - row) / ROWS if flip else row / ROWS
            person_h  = int(4 + progress * 4)
            person_w  = int(3 + progress * 3)
            spacing   = max(5, int(7 - progress * 2))
            cols      = w // spacing
            row_alpha = 0.15 + progress * 0.65

            for col in range(cols):
                phase      = self._rng(row * 41 + col * 17) * math.pi * 2
                wave_speed = 0.8 + self._rng(row * 7 + col * 3) * 0.8
                main_wave  = math.sin(t * wave_speed + col * 0.3 + phase) * person_h * 0.6
                micro_wave = math.sin(t * 2.1 + col * 0.7 + row * 0.4) * 1.5
                total_wave = main_wave + micro_wave

                px = col * spacing + spacing // 2
                row_y = (h - row * 9 - person_h) if flip else (row * 9 + person_h)
                py    = int(row_y + total_wave)

                color_idx = int(self._rng(row * 31 + col * 13) * len(self.CROWD_COLORS))
                color = self.CROWD_COLORS[color_idx]
                alpha = row_alpha * (0.6 + math.sin(t * 0.5 + phase) * 0.4)
                a_int = int(max(0.05, min(0.95, alpha)) * 255)

                # Body — filled rect directly on cache
                pygame.draw.rect(c, (*color, a_int),
                                 (px - person_w // 2, py, person_w, person_h))

                # Head — circle directly on cache
                head_r = max(1, int(person_w * 0.55))
                pygame.draw.circle(c, (212, 165, 116, a_int),
                                   (px, py - int(person_h * 0.4) - head_r), head_r)

                # Raised arms — lines directly on cache (no Surface alloc)
                if (self._rng(row * 53 + col * 29) > 0.65
                        and math.sin(t * wave_speed + col * 0.3 + phase) > 0.3):
                    arm_a = int(alpha * 0.7 * 255)
                    arm_color = (*color, arm_a)
                    pygame.draw.line(c, arm_color,
                                     (px - person_w, py + person_h // 3),
                                     (px - person_w // 3, py - person_h // 3), 1)
                    pygame.draw.line(c, arm_color,
                                     (px + person_w, py + person_h // 3),
                                     (px + person_w // 3, py - person_h // 3), 1)

    def _render_flashes(self, surface, x: int, y: int, flip: bool) -> None:
        """Camera flashes — drawn live each frame (rare, reuse pre-allocated surf)."""
        import pygame
        w, h = self.width, self.height
        t    = self.time
        fs   = self._flash_surf
        for f in range(3):
            intensity = max(0, math.sin(t * 5 + f * 2.1))
            if intensity > 0.85:
                fx = x + int(self._rng(t * 0.3 + f * 7) * w)
                fy_ratio = self._rng(t * 0.2 + f * 11) * 0.7
                fy = int(y + h - fy_ratio * h) if flip else int(y + fy_ratio * h)
                fa = int(intensity * 150)
                fs.fill((0, 0, 0, 0))
                pygame.draw.circle(fs, (255, 255, 255, fa),     (10, 10), 2)
                pygame.draw.circle(fs, (255, 255, 255, fa // 4),(10, 10), 8)
                surface.blit(fs, (fx - 10, fy - 10))


class FulbitoEffects:
    """Transient visual effects for the Fulbito variant.

    Effect types:
    - 'ring'          : expanding circle on a ball (comments, small gifts)
    - 'fire'          : particle trail on a ball (large gifts)
    - 'crowd_flash'   : tribuna color overlay (large gifts)
    - 'goal_flash'    : full-screen color pulse (at goal moment)
    - 'goal_confetti' : confetti rain from screen top (at goal moment)

    All positional rendering follows the same coordinate convention as
    _render_gift_flashes: racer.body.position coords blitted onto self.screen.
    """

    # Tier params: duration(s), particles/frame range, radius range, speed range (px/s),
    #              Y-jitter (px), individual particle lifetime range (s)
    _TIER_PARAMS = {
        1: dict(duration=1.5, count=(3, 4),   radius=(3.0, 4.0), speed=(60,  120), jitter_y=6,  plife=(0.30, 0.50)),
        2: dict(duration=2.0, count=(6, 8),   radius=(4.0, 6.0), speed=(80,  160), jitter_y=8,  plife=(0.50, 0.80)),
        3: dict(duration=3.0, count=(12, 15), radius=(5.0, 8.0), speed=(120, 220), jitter_y=12, plife=(0.40, 0.70)),
        4: dict(duration=3.0, count=(12, 15), radius=(5.0, 8.0), speed=(120, 220), jitter_y=12, plife=(0.40, 0.70)),
    }

    def __init__(self, engine: "FulbitoGameEngine") -> None:
        self._engine = engine
        self._effects: list[dict] = []
        # Pre-allocated surface for all fire particles — avoids per-particle alloc each frame
        import pygame
        from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
        # Only covers the render_surface area (460×820), not the full window —
        # fire particles never appear in the GAME_MARGIN border.
        self._fire_surf = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT), pygame.SRCALPHA)
        # Pre-allocated surface for momentum aura glow
        # Max radius = (45+8)+12 = 65px → 130px diameter + margin → 160×160
        self._aura_surf = pygame.Surface((160, 160), pygame.SRCALPHA)

    # ── Triggers ──────────────────────────────────────────────────────────────

    def add_ring(self, country: str, color: tuple) -> None:
        self._effects.append({
            'type': 'ring',
            'country': country,
            'color': color,
            'life': 0.4,
            'total': 0.4,
        })

    def add_fire_trail(self, country: str, going_right: bool, tier: int) -> None:
        p = self._TIER_PARAMS[tier]
        self._effects.append({
            'type': 'fire',
            'country': country,
            'going_right': going_right,
            'tier': tier,
            'life': p['duration'],
            'total': p['duration'],
            'particles': [],  # [x, y, vx, vy, life, max_life, radius]
            'burst_life': 0.2 if tier == 4 else 0.0,  # tier-4 white burst
        })

    def activate_momentum(self, country: str, color: tuple) -> bool:
        """Activate or refresh the momentum aura for *country*.

        Returns True if this is a new activation (caller should spawn text),
        False if the existing aura was simply refreshed.
        """
        from variants.fulbito.config import FULBITO_MOMENTUM_DURATION
        for eff in self._effects:
            if eff['type'] == 'momentum_aura' and eff['country'] == country:
                eff['life'] = FULBITO_MOMENTUM_DURATION  # refresh
                return False
        self._effects.append({
            'type': 'momentum_aura',
            'country': country,
            'color': color,
            'life': FULBITO_MOMENTUM_DURATION,
            'total': FULBITO_MOMENTUM_DURATION,
            'pulse_t': 0.0,
        })
        return True

    def get_momentum_aura(self, country: str) -> dict | None:
        for eff in self._effects:
            if eff['type'] == 'momentum_aura' and eff['country'] == country:
                return eff
        return None

    def clear_momentum(self) -> None:
        self._effects = [e for e in self._effects if e['type'] != 'momentum_aura']

    def add_crowd_flash(self, color: tuple) -> None:
        self._effects.append({
            'type': 'crowd_flash',
            'color': color,
            'life': 0.5,
            'total': 0.5,
        })

    def add_goal_effect(self, color: tuple) -> None:
        """Full-screen flash + confetti rain triggered at the exact goal moment."""
        self._effects.append({
            'type': 'goal_flash',
            'color': color,
            'life': 1.5,
            'total': 1.5,
        })
        from core.config import ACTUAL_WIDTH
        r, g, b = int(color[0]), int(color[1]), int(color[2])
        particles = []
        for _ in range(random.randint(80, 100)):
            cr, cg, cb = (r, g, b) if random.random() < 0.5 else (255, 255, 255)
            particles.append([
                random.uniform(0.0, float(ACTUAL_WIDTH)),  # 0: x
                0.0,                                         # 1: y (starts at screen top)
                random.uniform(-1.5, 1.5),                  # 2: vx (px/s)
                random.uniform(60.0, 160.0),                 # 3: vy (px/s, downward)
                float(random.randint(3, 8)),                 # 4: size (px)
                float(cr), float(cg), float(cb),             # 5,6,7: RGB
                random.uniform(0.0, 360.0),                  # 8: rotation angle (deg)
                random.uniform(-120.0, 120.0),               # 9: spin (deg/s)
            ])
        self._effects.append({
            'type': 'goal_confetti',
            'particles': particles,
            'life': 1.5,
            'total': 1.5,
        })

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        surviving = []
        for eff in self._effects:
            eff['life'] -= dt
            if eff['life'] <= 0:
                continue
            if eff['type'] == 'fire':
                self._update_fire(eff, dt)
            elif eff['type'] == 'goal_confetti':
                self._update_confetti(eff, dt)
            elif eff['type'] == 'momentum_aura':
                eff['pulse_t'] += dt
            surviving.append(eff)
        self._effects = surviving

    def _get_racer_pos(self, country: str) -> tuple[float, float] | None:
        pw = self._engine.physics_world
        if not pw:
            return None
        racer = pw.racers.get(country)
        if not racer:
            return None
        from core.config import GAME_MARGIN
        return (
            float(racer.body.position.x) + GAME_MARGIN,
            float(racer.body.position.y) + GAME_MARGIN,
        )

    def _update_fire(self, eff: dict, dt: float) -> None:
        pos = self._get_racer_pos(eff['country'])
        if pos is None:
            return

        # Advance burst timer (tier 4 only)
        if eff['burst_life'] > 0:
            eff['burst_life'] -= dt

        tp = self._TIER_PARAMS[eff['tier']]
        # vel_x: opposite to lane direction
        sign = -1.0 if eff['going_right'] else 1.0
        jitter = tp['jitter_y']
        rlo, rhi = tp['radius']
        slo, shi = tp['speed']
        plo, phi = tp['plife']

        for _ in range(random.randint(*tp['count'])):
            spd = random.uniform(slo, shi)
            # small random angle spread (±0.5 rad) around the backward axis
            vx = sign * spd + random.uniform(-spd * 0.15, spd * 0.15)
            vy = random.uniform(-30.0, 30.0)
            plife = random.uniform(plo, phi)
            eff['particles'].append([
                pos[0] + random.uniform(-4, 4),  # 0: x
                pos[1] + random.uniform(-jitter, jitter),  # 1: y
                vx,     # 2: vx (px/s)
                vy,     # 3: vy (px/s)
                plife,  # 4: life remaining
                plife,  # 5: max_life (constant)
                random.uniform(rlo, rhi),  # 6: radius
            ])

        alive = []
        for p in eff['particles']:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[4] -= dt
            if p[4] > 0:
                alive.append(p)
        eff['particles'] = alive

    def _update_confetti(self, eff: dict, dt: float) -> None:
        gravity = 80.0  # px/s²
        for p in eff['particles']:
            p[0] += p[2] * dt
            p[1] += p[3] * dt
            p[3] += gravity * dt
            p[8] += p[9] * dt

    # ── Momentum aura — drawn on render_surface (behind the ball sprite) ──────

    def draw_aura_on_surface(self, surface, country: str, cx: float, cy: float) -> None:
        """Draw momentum glow for *country* at render_surface coords (cx, cy).

        4 concentric filled circles (largest first) produce a soft halo that
        pulses gently and fades out in the last 0.5s of the effect's life.
        """
        import pygame
        eff = self.get_momentum_aura(country)
        if eff is None:
            return

        # Oscillating base radius
        pulse = math.sin(eff['pulse_t'] * 4.0)
        base_r = 45.0 + 8.0 * pulse  # 37–53 px

        # Fade-out in last 0.5s
        fade = min(1.0, eff['life'] / 0.5)

        r, g, b = int(eff['color'][0]), int(eff['color'][1]), int(eff['color'][2])
        half = 80  # centre of 160×160 surface

        self._aura_surf.fill((0, 0, 0, 0))
        # Layers: (extra_radius, alpha) — drawn outermost → innermost
        for extra_r, layer_alpha in ((12, 25), (8, 40), (4, 60), (0, 80)):
            radius = max(1, int(base_r + extra_r))
            alpha  = int(layer_alpha * fade)
            pygame.draw.circle(
                self._aura_surf, (r, g, b, alpha), (half, half), radius
            )

        surface.blit(self._aura_surf, (int(cx) - half, int(cy) - half))

    # ── Render: game-space effects (rings, fire) on self.screen ───────────────

    def render_game_effects(self) -> None:
        """Rings and fire trails — drawn on self.screen at racer body coords."""
        screen = self._engine.screen
        for eff in self._effects:
            if eff['type'] == 'ring':
                self._render_ring(screen, eff)
            elif eff['type'] == 'fire':
                self._render_fire(screen, eff)

    def _render_ring(self, screen, eff: dict) -> None:
        import pygame
        pos = self._get_racer_pos(eff['country'])
        if pos is None:
            return
        progress = 1.0 - eff['life'] / eff['total']
        radius = int(15 + 45 * progress)
        alpha = int(200 * (1.0 - progress))
        x, y = int(pos[0]), int(pos[1])
        side = (radius + 4) * 2
        surf = pygame.Surface((side, side), pygame.SRCALPHA)
        r, g, b = int(eff['color'][0]), int(eff['color'][1]), int(eff['color'][2])
        pygame.draw.circle(surf, (r, g, b, alpha), (radius + 4, radius + 4), radius, 3)
        screen.blit(surf, (x - radius - 4, y - radius - 4))

    @staticmethod
    def _fire_color(t: float) -> tuple[int, int, int, int]:
        """Color gradient: white → yellow → orange → dark-red, alpha fades at end."""
        if t < 0.3:
            return 255, 255, 255, 200
        elif t < 0.6:
            frac = (t - 0.3) / 0.3
            return 255, int(255 - 35 * frac), int(255 * (1 - frac)), 200
        elif t < 0.8:
            frac = (t - 0.6) / 0.2
            return 255, int(220 - 120 * frac), 0, 200
        else:
            frac = (t - 0.8) / 0.2
            return int(255 - 75 * frac), int(100 - 70 * frac), 0, int(200 * (1 - frac))

    def _render_fire(self, screen, eff: dict) -> None:
        import pygame
        from core.config import GAME_MARGIN
        fs = self._fire_surf
        fs.fill((0, 0, 0, 0))
        # Particles store screen coords (+GAME_MARGIN). fire_surf is render_surface
        # size, blitted at (GAME_MARGIN, GAME_MARGIN) — subtract offset when drawing.
        gm = GAME_MARGIN

        for p in eff['particles']:
            if p[4] <= 0:
                continue
            t = 1.0 - p[4] / p[5]
            r, g, b, alpha = self._fire_color(t)
            size = max(1, int(p[6] * (1.0 - t * 0.75)))
            pygame.draw.circle(fs, (r, g, b, alpha),
                               (int(p[0]) - gm, int(p[1]) - gm), size)

        if eff['burst_life'] > 0:
            pos = self._get_racer_pos(eff['country'])
            if pos:
                burst_t = 1.0 - eff['burst_life'] / 0.2
                burst_r = int(80 * burst_t)
                burst_a = int(255 * (1.0 - burst_t))
                if burst_r > 0 and burst_a > 0:
                    pygame.draw.circle(fs, (255, 255, 255, burst_a),
                                       (int(pos[0]) - gm, int(pos[1]) - gm), burst_r, 3)

        screen.blit(fs, (gm, gm))

    # ── Render: screen-space effects (flash, confetti, crowd) ─────────────────

    def render_screen_effects(self) -> None:
        """Crowd flash, goal flash, goal confetti — drawn in screen-space coords."""
        screen = self._engine.screen
        for eff in self._effects:
            if eff['type'] == 'crowd_flash':
                self._render_crowd_flash(screen, eff)
            elif eff['type'] == 'goal_flash':
                self._render_goal_flash(screen, eff)
            elif eff['type'] == 'goal_confetti':
                self._render_goal_confetti(screen, eff)

    def _render_crowd_flash(self, screen, eff: dict) -> None:
        import pygame
        from core.config import ACTUAL_WIDTH, GAME_AREA_TOP, GAME_MARGIN
        progress = 1.0 - eff['life'] / eff['total']
        alpha = max(0, int(120 * (1.0 - progress)))
        r, g, b = int(eff['color'][0]), int(eff['color'][1]), int(eff['color'][2])
        top_surf = pygame.Surface((ACTUAL_WIDTH, GAME_AREA_TOP), pygame.SRCALPHA)
        top_surf.fill((r, g, b, alpha))
        screen.blit(top_surf, (0, 0))
        engine = self._engine
        bot_y = engine._tribuna_bot_y + GAME_MARGIN + 20
        bot_h = max(10, screen.get_height() - bot_y)
        bot_surf = pygame.Surface((ACTUAL_WIDTH, bot_h), pygame.SRCALPHA)
        bot_surf.fill((r, g, b, alpha))
        screen.blit(bot_surf, (0, bot_y))

    def _render_goal_flash(self, screen, eff: dict) -> None:
        import pygame
        elapsed = eff['total'] - eff['life']
        if elapsed < 0.3:
            alpha = int(180 * elapsed / 0.3)
        else:
            alpha = int(180 * max(0.0, 1.0 - (elapsed - 0.3) / 1.2))
        alpha = max(0, min(255, alpha))
        r, g, b = int(eff['color'][0]), int(eff['color'][1]), int(eff['color'][2])
        w, h = screen.get_size()
        surf = pygame.Surface((w, h), pygame.SRCALPHA)
        surf.fill((r, g, b, alpha))
        screen.blit(surf, (0, 0))

    def _render_goal_confetti(self, screen, eff: dict) -> None:
        import pygame
        fade = min(1.0, eff['life'] / 0.5)
        _surf = pygame.Surface((20, 20), pygame.SRCALPHA)  # single reused surface
        for p in eff['particles']:
            alpha = max(0, int(255 * fade))
            r, g, b = int(p[5]), int(p[6]), int(p[7])
            size = max(1, int(p[4]))
            _surf.fill((0, 0, 0, 0))
            pygame.draw.circle(_surf, (r, g, b, alpha), (10, 10), size)
            screen.blit(_surf, (int(p[0]) - 10, int(p[1]) - 10))


class FulbitoGameEngine(GameEngine):
    """Motor de juego para la variante Fulbito — Mundial 2026."""

    def __init__(
        self,
        queue: asyncio.Queue,
        streamer_name: str,
        database=None,
    ):
        # Patch core.config before super().__init__() so the core physics_world
        # is created with the 4 fulbito countries, not the 15 core countries.
        import core.config as _cc
        import variants.fulbito.config as _fc
        from core.config import GIFT_COLORS as _base_colors

        _FULBITO_COLORS = {
            "ARG": (116, 172, 72),
            "BRA": (0, 156, 59),
            "MEX": (206, 17, 38),
            "COL": (252, 209, 22),
            "URU": (0, 56, 168),
            "ECU": (255, 210, 0),
            "PAR": (0, 56, 168),
            "PAN": (0, 56, 168),
            "GUA": (0, 116, 54),
            "ENG": (200, 16, 46),
            "FRA": (0, 35, 149),
            "CRO": (255, 0, 0),
            "POR": (0, 102, 0),
            "ALE": (0, 0, 0),
            "PAI": (255, 102, 0),
            "ESP": (170, 21, 27),
            "USA": (60, 59, 110),
            "CAN": (255, 0, 0),
        }

        _cc.RACE_COUNTRIES = list(_fc.FULBITO_DEFAULT_FIXTURE)
        _cc.COUNTRY_ABBREV = {c: c for c in _fc.FULBITO_ALL_COUNTRIES}
        _cc.GIFT_COLORS = {**_base_colors, **_FULBITO_COLORS}

        # 4 carriles × 85px = 340px total, centrado en 721px game area
        _cc.LANE_HEIGHT = 85

        # Disable core features irrelevant to fulbito
        _cc.HYPE_TIMER_ENABLED = False
        _cc.HYPE_TIMER_INTERVAL = 99999
        _cc.METEOR_COUNT = 0
        _cc.METEOR_BOOST_MIN = 0
        _cc.METEOR_BOOST_MAX = 0

        super().__init__(queue, streamer_name, database=database)

        # Silence all background and victory audio for fulbito.
        # Monkey-patching the instance is necessary because play_bgm() re-applies
        # VOL_BGM (a module-level constant) on every call, so config overrides don't stick.
        import pygame
        pygame.mixer.stop()
        _am = self.audio_manager
        _noop = lambda *a, **kw: None
        _am.play_bgm            = _noop
        _am.play_bgm_normal     = _noop
        _am.play_bgm_tension    = _noop
        _am.stop_bgm            = _noop
        _am.play_victory_sound  = _noop
        _am.stop_victory_sound  = _noop
        _am.play_final_stretch_sound = _noop
        _am.play_combo_fire_sound    = _noop

        # Mute toggle state — initialize BEFORE starting BGM
        self._muted: bool = False

        self._start_fulbito_bgm()

        self.game_state = 'FIXTURE_SETUP'

        # Fixture y estado de partido
        self.current_fixture: list[str] = list(FULBITO_DEFAULT_FIXTURE)
        self.race_number: int = 0
        self.king: Optional[str] = None
        self.viewer_teams: dict[str, str] = {}
        self.intermission_votes: dict[str, str] = {}
        self.vote_counts: dict[str, int] = {}
        self.race_finished_timer: float = 0.0
        self.intermission_timer: float = 0.0
        self.fixture_setup_timer: float = 0.0
        self.wildcard_country: Optional[str] = None
        self._race_start_time: Optional[float] = None
        self._app_start_time: float = time.time()
        self._winner_video_cap = None
        self._winner_video_next_frame_at: float = 0.0
        self._winner_video_current_surf = None
        self._winner_video_rect: tuple = (0, 0, 1, 1)
        self._wc2026_bg = None
        self._fixture_selected_slot: int = 0
        self._fixture_error_msg: str = ''
        self._fixture_error_timer: float = 0.0
        # Randomizar fixture inicial (sin duplicados) para el sorteo FIFA
        _chosen = random.sample(range(len(FULBITO_ALL_COUNTRIES)), FULBITO_RACE_COUNTRY_COUNT)
        self._fixture_country_index: dict[int, int] = {i: _chosen[i] for i in range(FULBITO_RACE_COUNTRY_COUNT)}

        # Estado de la animación "sorteo FIFA"
        self._draw_phase: str = 'animating'            # 'animating' | 'manual'
        self._draw_slot_idx: int = 0                   # slot actualmente girando
        self._draw_slot_timer: float = 0.0             # tiempo transcurrido en este slot
        self._draw_slot_duration: float = 1.5          # segundos por slot
        self._draw_spin_time: float = 0.0              # acumulador global del giro
        self._draw_settled: list[bool] = [False] * FULBITO_RACE_COUNTRY_COUNT

        self.session_wins: dict[str, int] = {}

        # Estadísticas de sesión
        self.session_total_diamonds: int = 0
        self.session_unique_viewers: set[str] = set()
        self.session_top_donor: dict[str, int] = {}
        self.session_country_diamonds: dict[str, int] = {}

        # Visual impact flashes: country → (start_time, diamond_count)
        self._gift_flashes: dict[str, tuple[float, int]] = {}

        # Per-race, per-country donor leaderboard: country → {username → diamonds}
        self._race_country_donors: dict[str, dict[str, int]] = {}
        # MVP of the winning country: (username, diamonds) or None
        self._victory_mvp: tuple[str, int] | None = None
        # Victory particle list — each entry: [x, y, vx, vy, r, g, b, life, decay, size, kind, angle, spin]
        # kind: 0 = spark circle, 1 = confetti rectangle
        self._victory_particles: list = []
        self._firework_timer: float = 0.0

        # Stadium crowd stands
        from core.config import ACTUAL_WIDTH, GAME_AREA_TOP
        self._tribuna_top = _StadiumTribuna(ACTUAL_WIDTH, GAME_AREA_TOP - 4)
        self._tribuna_bot: _StadiumTribuna | None = None
        self._tribuna_bot_y: int = 0

        # Reemplazar physics_world con FulbitoPhysicsWorld
        self._init_fulbito_physics()

        # Tribuna inferior: calculada en _init_fulbito_physics(); GAME_MARGIN se suma en render

    def _init_fulbito_physics(self) -> None:
        import core.config as _cc
        # Asegurar que los extremos de inicio/fin usen el ancho completo de la cancha
        _cc.RACE_START_X = 20
        _cc.RACE_FINISH_X = _cc.SCREEN_WIDTH - 20

        from variants.fulbito.physics_world import FulbitoPhysicsWorld
        if self.asset_manager:
            from core.asset_manager import AssetManager
            self.asset_manager = AssetManager(
                assets_path="variants/fulbito/assets"
            )
        self.physics_world = FulbitoPhysicsWorld(
            countries=self.current_fixture,
            asset_manager=self.asset_manager,
            game_engine=self,
        )

        # Recalcular tribuna inferior en coords de self.screen (incluye GAME_MARGIN)
        from core.config import ACTUAL_WIDTH, ACTUAL_HEIGHT, GAME_MARGIN
        pw = self.physics_world
        logger.info(
            "[FULBITO PHYSICS] game_area_top=%s lane_y_offset=%s "
            "lane_height=%s countries=%s bot_y=%s tribuna_h=%s",
            pw.game_area_top, pw.lane_y_offset, pw.lane_height,
            len(pw.countries),
            pw.game_area_top + pw.lane_y_offset + pw.lane_height * len(pw.countries),
            ACTUAL_HEIGHT - (pw.game_area_top + pw.lane_y_offset + pw.lane_height * len(pw.countries)) - 4
        )
        bot_y = (pw.game_area_top + pw.lane_y_offset
                 + pw.lane_height * len(pw.countries))
        self._tribuna_bot_y = bot_y
        tribuna_h = max(10, ACTUAL_HEIGHT - (bot_y + GAME_MARGIN) - 4)
        self._tribuna_bot = _StadiumTribuna(ACTUAL_WIDTH, tribuna_h)

        self._update_outer_background()

        # Club members — persists across races for the whole session
        self._club_members: set[str] = set()

        # Chat momentum tracking: country → deque of (timestamp, username)
        self._comment_momentum: dict[str, deque] = {}

        # Visual effects system
        self.effects = FulbitoEffects(self)

    # ── Pygame init ──────────────────────────────────────────────────────────

    def init_pygame(self) -> None:
        super().init_pygame()
        import pygame
        from core.config import ACTUAL_WIDTH, ACTUAL_HEIGHT
        pygame.display.set_caption("Fulbito — Mundial 2026")
        self.outer_background = pygame.Surface((ACTUAL_WIDTH, ACTUAL_HEIGHT))
        self.outer_background.fill((10, 10, 10))
        self.background_manager = _GrassBackground(self)
        try:
            from core.resources import resource_path
            from core.config import SCREEN_HEIGHT, GAME_AREA_TOP, GAME_AREA_BOTTOM, GAME_MARGIN
            _zone_w = ACTUAL_WIDTH
            _zone_h = (SCREEN_HEIGHT - GAME_AREA_BOTTOM + GAME_MARGIN) - (GAME_AREA_TOP + GAME_MARGIN)
            _raw = pygame.image.load(resource_path("variants/fulbito/assets/wc2026.png")).convert()
            _src_w, _src_h = _raw.get_size()
            _scale = max(_zone_w / _src_w, _zone_h / _src_h)
            _scaled_w = int(_src_w * _scale)
            _scaled_h = int(_src_h * _scale)
            _scaled = pygame.transform.smoothscale(_raw, (_scaled_w, _scaled_h))
            _off_x = (_scaled_w - _zone_w) // 2
            _off_y = (_scaled_h - _zone_h) // 2
            self._wc2026_bg = _scaled.subsurface((_off_x, _off_y, _zone_w, _zone_h)).copy()
            _bw, _bh = self._wc2026_bg.get_size()
            _small = pygame.transform.smoothscale(self._wc2026_bg, (_bw // 4, _bh // 4))
            self._wc2026_bg = pygame.transform.smoothscale(_small, (_bw, _bh))
        except Exception:
            self._wc2026_bg = None

    # ── Finish line — football goals ─────────────────────────────────────────

    def _render_finish_line(self) -> None:
        """Arcos de fútbol en los extremos visuales de la pantalla."""
        import pygame
        from core.config import SCREEN_WIDTH, GAME_AREA_TOP
        from variants.fulbito.config import FULBITO_LANE_DIRECTIONS

        lane_h = self.physics_world.lane_height
        lane_y_offset = self.physics_world.lane_y_offset

        for i, country in enumerate(self.current_fixture):
            going_right = FULBITO_LANE_DIRECTIONS.get(i, True)
            goal_x = SCREEN_WIDTH - 8 if going_right else 8
            lane_cy = (
                GAME_AREA_TOP + lane_y_offset
                + i * lane_h + lane_h // 2
            )
            self._draw_goal(goal_x, lane_cy, going_right, lane_h)

        # ── Línea del medio y círculo central ────────────────────────────────
        C          = (255, 255, 255, 115)
        num_lanes  = len(self.current_fixture)
        field_top  = GAME_AREA_TOP + lane_y_offset
        field_bot  = field_top + num_lanes * lane_h
        field_h    = field_bot - field_top
        cx         = SCREEN_WIDTH // 2
        cy         = (field_top + field_bot) // 2

        # Línea vertical centrada
        line_surf = pygame.Surface((2, field_h), pygame.SRCALPHA)
        pygame.draw.line(line_surf, C, (0, 0), (0, field_h - 1), 1)
        self.render_surface.blit(line_surf, (cx, field_top))

        # Círculo central
        circle_r = int(field_h * 0.12)
        side     = (circle_r + 2) * 2
        circ_surf = pygame.Surface((side, side), pygame.SRCALPHA)
        pygame.draw.circle(circ_surf, C, (circle_r + 2, circle_r + 2), circle_r, 1)
        self.render_surface.blit(circ_surf, (cx - circle_r - 2, cy - circle_r - 2))

    def _draw_goal(
        self,
        x: int,
        center_y: int,
        facing_right: bool,
        lane_h: int,
    ) -> None:
        import pygame
        import math

        GW      = 16
        GoH     = int(lane_h * 0.55)
        SMALL_W = 26
        SMALL_H = int(lane_h * 0.70)
        BIG_W   = 50
        BIG_H   = int(lane_h * 0.90)
        PD      = (SMALL_W + BIG_W) // 2

        lx  = x
        dir = -1 if facing_right else 1
        C   = (255, 255, 255, 115)

        def line(x1, y1, x2, y2, w=1):
            surf = pygame.Surface((abs(x2 - x1) + w, abs(y2 - y1) + w), pygame.SRCALPHA)
            pygame.draw.line(surf, C,
                             (0, 0) if x1 <= x2 else (abs(x2 - x1), 0),
                             (abs(x2 - x1), abs(y2 - y1)) if x1 <= x2 else (0, abs(y2 - y1)), w)
            self.render_surface.blit(surf, (min(x1, x2), min(y1, y2)))

        def hline(y, x1, x2): line(x1, y, x2, y)
        def vline(xp, y1, y2): line(xp, y1, xp, y2)

        # Área grande
        bt  = center_y - BIG_H // 2
        bb  = center_y + BIG_H // 2
        bex = lx + dir * BIG_W
        hline(bt, min(lx, bex), max(lx, bex))
        hline(bb, min(lx, bex), max(lx, bex))
        vline(bex, bt, bb)

        # Área chica
        st  = center_y - SMALL_H // 2
        sb  = center_y + SMALL_H // 2
        sex = lx + dir * SMALL_W
        hline(st, min(lx, sex), max(lx, sex))
        hline(sb, min(lx, sex), max(lx, sex))
        vline(sex, st, sb)

        # Punto penal
        px = lx + dir * PD
        pygame.draw.circle(self.render_surface, C, (px, center_y), 3)

        # Medialuna
        moon_dy = BIG_H // 2 * 0.5
        dx      = abs(bex - px)
        moon_r  = int(math.sqrt(dx * dx + moon_dy * moon_dy))
        ha      = math.atan2(moon_dy, dx)

        points = []
        if facing_right:
            start_a = math.pi - ha
            end_a   = math.pi + ha
        else:
            start_a = -ha
            end_a   = ha

        steps = 32
        for i in range(steps + 1):
            t = start_a + (end_a - start_a) * i / steps
            mx = int(px + moon_r * math.cos(t))
            my = int(center_y + moon_r * math.sin(t))
            points.append((mx, my))

        if len(points) > 1:
            moon_surf = pygame.Surface(
                (self.render_surface.get_width(), self.render_surface.get_height()),
                pygame.SRCALPHA,
            )
            pygame.draw.lines(moon_surf, C, False, points, 1)
            self.render_surface.blit(moon_surf, (0, 0))

        # Red dentro del arco
        goal_l = lx - GW if facing_right else lx
        goal_r = lx if facing_right else lx + GW
        goal_t = center_y - GoH // 2
        goal_b = center_y + GoH // 2

        net_surf  = pygame.Surface(
            (self.render_surface.get_width(), self.render_surface.get_height()),
            pygame.SRCALPHA,
        )
        net_color = (255, 255, 255, 45)
        for nx in range(goal_l + 3, goal_r, 4):
            pygame.draw.line(net_surf, net_color, (nx, goal_t), (nx, goal_b), 1)
        for ny in range(goal_t + 3, goal_b, 4):
            pygame.draw.line(net_surf, net_color, (goal_l, ny), (goal_r, ny), 1)
        self.render_surface.blit(net_surf, (0, 0))

        # Marco del arco
        post_color = (220, 220, 220)
        pygame.draw.line(self.render_surface, post_color,
                         (goal_l, goal_t), (goal_r, goal_t), 2)
        pygame.draw.line(self.render_surface, post_color,
                         (goal_l, goal_b), (goal_r, goal_b), 2)
        back_x = goal_r if facing_right else goal_l
        pygame.draw.line(self.render_surface, post_color,
                         (back_x, goal_t), (back_x, goal_b), 2)

        # Poste delantero dorado
        front_x = goal_l if facing_right else goal_r
        pygame.draw.line(self.render_surface, (255, 215, 0),
                         (front_x, goal_t - 3), (front_x, goal_b + 3), 3)

    # ── Core render suppression ───────────────────────────────────────────────
    # No-ops for features Fulbito doesn't use.
    # NOTE: _render_hype_timer and _update_hype_timer MUST stay here even though
    # we set HYPE_TIMER_ENABLED=False at runtime — the core module binds that
    # constant at import time via "from .config import", so the patch has no
    # effect on the core's if-guards. Same for disaster flash/title.

    def _render_hype_timer(self, surface) -> None:
        pass

    def _update_hype_timer(self) -> None:
        pass

    def _render_disaster_flash(self) -> None:
        pass

    def _render_disaster_title(self) -> None:
        pass

    def _render_milestone_banner(self) -> None:
        pass

    def _render_final_stretch_announcement(self) -> None:
        pass

    def _render_final_stretch_line(self) -> None:
        pass

    def _render_lanes(self) -> None:
        pass

    def _render_victory_sequence(self) -> None:
        pass

    def _render_winner_spotlight(self, racer) -> None:
        pass

    def _render_leader_spotlight(self, racer) -> None:
        pass

    def _render_victory_flash(self) -> None:
        pass

    def _render_particles(self) -> None:
        pass

    def _render_combo_flashes(self) -> None:
        pass

    def _render_leaderboard(self) -> None:
        pass

    def _render_likes_bar(self) -> None:
        pass

    def _render_idle_screen(self) -> None:
        pass

    def _open_winner_video(self) -> None:
        try:
            import cv2
        except ImportError:
            logger.warning("cv2 not available — winner GIF disabled")
            return
        from core.resources import resource_path
        import os
        path = resource_path("variants/fulbito/assets/gol_2.GIF")
        if not os.path.exists(path):
            logger.warning("Winner GIF not found: %s", path)
            return
        cap = cv2.VideoCapture(path)
        if not cap.isOpened():
            logger.warning("Could not open winner GIF")
            return
        self._winner_video_cap = cap
        self._winner_video_next_frame_at = 0.0
        self._winner_video_current_surf = None
        from core.config import ACTUAL_WIDTH, ACTUAL_HEIGHT
        pw = self.physics_world
        video_top = pw.game_area_top + pw.lane_y_offset + pw.lane_height * len(self.current_fixture)
        self._winner_video_rect = (0, video_top, ACTUAL_WIDTH, ACTUAL_HEIGHT - video_top)
        logger.info("Winner GIF opened, rect=%s", self._winner_video_rect)

    def _advance_winner_video(self) -> None:
        try:
            import cv2
        except ImportError:
            return
        import pygame
        cap = self._winner_video_cap
        if cap is None:
            return
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        if self.race_finished_timer < self._winner_video_next_frame_at:
            return
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)  # loop GIF
            ret, frame = cap.read()
            if not ret:
                return
        self._winner_video_next_frame_at += 1.0 / fps
        h, w = frame.shape[:2]
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        surf = pygame.image.frombuffer(rgb.tobytes(), (w, h), 'RGB')
        _, _, vw, vh = self._winner_video_rect
        self._winner_video_current_surf = pygame.transform.smoothscale(surf, (vw, vh))

    def _toggle_mute(self) -> None:
        import pygame
        self._muted = not self._muted
        if self._muted:
            pygame.mixer.music.set_volume(0.0)
            pygame.mixer.pause()
        else:
            # Restore to whatever volume the game had set before muting
            pygame.mixer.music.set_volume(
                0.05 if self.game_state == 'RACE_FINISHED' else 0.3
            )
            pygame.mixer.unpause()
        logger.info("Mute toggled: %s", "ON" if self._muted else "OFF")

    def _start_fulbito_bgm(self) -> None:
        import pygame
        from core.resources import resource_path
        import os
        bgm_path = resource_path("variants/fulbito/assets/bgm_fulbito.mp3")
        if not os.path.exists(bgm_path):
            logger.warning("Fulbito BGM not found: %s", bgm_path)
            return
        try:
            pygame.mixer.music.load(bgm_path)
            pygame.mixer.music.set_volume(0.0 if self._muted else 0.3)
            pygame.mixer.music.play(loops=-1)
            logger.info("Fulbito BGM started: %s", bgm_path)
        except Exception as exc:
            logger.warning("Could not start Fulbito BGM: %s", exc)

    def _render_header(self) -> None:
        pass

    def _render_audio_toast(self) -> None:
        pass

    def _render_meteors(self) -> None:
        pass

    def _trigger_meteor_shower(self) -> None:
        pass

    def _update_meteors(self, dt: float) -> None:
        pass

    async def _handle_join_event(self, event) -> None:
        pass

    async def _handle_vote_event(self, event) -> None:
        pass

    # ── Helpers ──────────────────────────────────────────────────────────────

    def _get_last_place_country(self) -> str:
        if not self.physics_world.racers:
            return self.current_fixture[0]
        return min(
            self.current_fixture,
            key=lambda c: self.physics_world.get_progress(c),
        )

    def _pick_wildcard(self) -> str:
        candidates = [c for c in FULBITO_ALL_COUNTRIES if c not in self.current_fixture]
        if not candidates:
            return random.choice(FULBITO_ALL_COUNTRIES)
        return random.choice(candidates)

    def _build_fixture_from_votes(self) -> list[str]:
        fixture: list[str] = []

        # King se queda automáticamente
        if self.king and self.king in FULBITO_ALL_COUNTRIES:
            fixture.append(self.king)

        # Top votos del chat (excluyendo al king)
        crowd_candidates = {
            c: v for c, v in self.vote_counts.items()
            if c not in fixture and c in FULBITO_ALL_COUNTRIES
        }
        crowd_sorted = sorted(crowd_candidates, key=crowd_candidates.get, reverse=True)
        for c in crowd_sorted[:FULBITO_CROWD_PICKS]:
            fixture.append(c)

        # Rellenar hasta FULBITO_RACE_COUNTRY_COUNT con wildcard o aleatorio
        while len(fixture) < FULBITO_RACE_COUNTRY_COUNT:
            wc = self.wildcard_country
            if wc and wc not in fixture:
                fixture.append(wc)
            else:
                candidates = [c for c in FULBITO_ALL_COUNTRIES if c not in fixture]
                if candidates:
                    fixture.append(random.choice(candidates))

        return fixture[:FULBITO_RACE_COUNTRY_COUNT]

    # ── Event handlers ────────────────────────────────────────────────────────

    async def _handle_event(self, event) -> None:
        if event.created_at_sec is not None:
            latency = time.perf_counter() - event.created_at_sec
            if latency > self.LAG_WARNING_THRESHOLD_SEC:
                logger.warning("[LAG] %.0fms type=%s", latency * 1000, event.type.name)

        if event.type == EventType.QUIT:
            self.running = False
            return

        if event.type == EventType.CONNECTION_STATUS:
            if event.extra and "state" in event.extra:
                self.connection_state = event.extra["state"]
            message = event.format_message()
            self.messages.append((message, event.type))
            if len(self.messages) > MAX_MESSAGES:
                self.messages = self.messages[-MAX_MESSAGES:]

        elif event.type == EventType.GIFT:
            await self._handle_fulbito_gift(event)

        elif event.type == EventType.COMMENT:
            await self._handle_fulbito_comment(event)

        elif event.type == EventType.FOLLOW:
            await self._handle_fulbito_follow(event)

        elif event.type == EventType.SHARE:
            await self._handle_fulbito_share(event)

        elif event.type == EventType.SUBSCRIBE:
            await self._handle_fulbito_subscribe(event)

        else:
            await super()._handle_event(event)

    async def _handle_fulbito_gift(self, event) -> None:
        if self.game_state == 'FIXTURE_SETUP':
            return
        if self.game_state == 'IDLE':
            self._race_country_donors.clear()
            self._victory_mvp = None
            self._transition_to_race_running()

        if self.game_state != 'RACE_RUNNING':
            return

        username = self.sanitize_username(event.username)
        gift_name = event.content or ''
        logger.debug("[Gift raw] gift_name=%r username=%r", gift_name, username)
        diamond_count = event.extra.get('diamond_count', 1) if event.extra else 1
        gift_count = event.extra.get('count', 1) if event.extra else 1
        total_diamonds = diamond_count * gift_count

        if username in self.viewer_teams:
            country = self.viewer_teams[username]
        else:
            country = self._get_last_place_country()

        if country not in self.current_fixture:
            country = self._get_last_place_country()

        # Club member multiplier applies before any impulse
        if username in self._club_members:
            total_diamonds = int(total_diamonds * 1.25)

        # Quiéreme gift: fixed impulse, skip normal diamond calculation
        from variants.fulbito.config import (
            FULBITO_QUIEREME_NAMES, FULBITO_QUIEREME_DISTANCE,
            FULBITO_CLUB_MEMBER_MULTIPLIER,
        )
        if gift_name.lower().strip() in FULBITO_QUIEREME_NAMES:
            distance = FULBITO_QUIEREME_DISTANCE
            if username in self._club_members:
                distance = int(distance * FULBITO_CLUB_MEMBER_MULTIPLIER)
            self.physics_world.apply_gift_impulse(country, gift_name, distance)
            self._gift_flashes[country] = (time.time(), distance)
            self._add_gift_effect(country, distance)
            self._on_real_activity()
            self._add_floating_text(f"+QUIEREME → {country}", color=(255, 100, 180))
            logger.info("Quiereme gift: %s → %s (distance=%d)", username, country, distance)
            return

        self.physics_world.apply_gift_impulse(country, gift_name, total_diamonds)
        self._gift_flashes[country] = (time.time(), total_diamonds)
        self._add_gift_effect(country, total_diamonds)
        self._on_real_activity()

        self.session_total_diamonds += total_diamonds
        self.session_unique_viewers.add(username)
        self.session_top_donor[username] = (
            self.session_top_donor.get(username, 0) + total_diamonds
        )
        self.session_country_diamonds[country] = (
            self.session_country_diamonds.get(country, 0) + total_diamonds
        )
        country_donors = self._race_country_donors.setdefault(country, {})
        country_donors[username] = country_donors.get(username, 0) + total_diamonds

        if self.cloud_manager:
            asyncio.create_task(
                self.cloud_manager.sync_gift_event_v2(
                    session_id=self.session_id,
                    variant='fulbito',
                    username=username,
                    gift_name=gift_name,
                    diamond_count=diamond_count,
                    gift_count=gift_count,
                    country=country,
                    race_number=self.race_number,
                )
            )

        self._add_floating_text(f"+{total_diamonds} → {country}")

    async def _handle_fulbito_comment(self, event) -> None:
        if self.game_state == 'FIXTURE_SETUP':
            return

        username = self.sanitize_username(event.username)
        text = (event.content or '').strip().lower()
        country = resolve_alias(text)

        if not country or country not in FULBITO_ALL_COUNTRIES:
            return

        if self.game_state == 'IDLE':
            if country in self.current_fixture:
                self.viewer_teams[username] = country
                self.user_assignments[username] = country
                self.session_unique_viewers.add(username)
                self._transition_to_race_running()
            self.physics_world.apply_gift_impulse(country, "comment", 1)
            self._add_gift_effect(country, 1)

        elif self.game_state == 'RACE_RUNNING':
            if country not in self.current_fixture:
                return
            is_new = username not in self.viewer_teams
            if is_new:
                self.viewer_teams[username] = country
                self.user_assignments[username] = country
                self.session_unique_viewers.add(username)
                self._add_join_text(username, country)
            elif self.viewer_teams[username] != country:
                return
            self.physics_world.apply_gift_impulse(country, "comment", 1)
            self._add_gift_effect(country, 1)
            self._update_comment_momentum(country, username)

        elif self.game_state == 'RACE_INTERMISSION':
            self.viewer_teams[username] = country
            self.user_assignments[username] = country
            self.session_unique_viewers.add(username)
            self.intermission_votes[username] = country
            self.vote_counts = {}
            for v in self.intermission_votes.values():
                self.vote_counts[v] = self.vote_counts.get(v, 0) + 1

    async def _handle_fulbito_follow(self, event) -> None:
        if self.game_state != 'RACE_RUNNING':
            return
        from variants.fulbito.config import FULBITO_FOLLOW_DISTANCE
        username = self.sanitize_username(event.username)
        country = self.viewer_teams.get(username) or self._get_last_place_country()
        if country not in self.current_fixture:
            country = self._get_last_place_country()
        self.physics_world.apply_gift_impulse(country, "follow", FULBITO_FOLLOW_DISTANCE)
        self._add_gift_effect(country, FULBITO_FOLLOW_DISTANCE)
        self._add_floating_text(f"+FOLLOW → {country}", color=(100, 220, 255))
        logger.info("Follow: %s → %s", username, country)

    async def _handle_fulbito_share(self, event) -> None:
        if self.game_state != 'RACE_RUNNING':
            return
        from variants.fulbito.config import FULBITO_SHARE_DISTANCE
        username = self.sanitize_username(event.username)
        country = self.viewer_teams.get(username) or self._get_last_place_country()
        if country not in self.current_fixture:
            country = self._get_last_place_country()
        self.physics_world.apply_gift_impulse(country, "share", FULBITO_SHARE_DISTANCE)
        self._add_gift_effect(country, FULBITO_SHARE_DISTANCE)
        self._add_floating_text(f"+SHARE → {country}", color=(100, 255, 180))
        logger.info("Share: %s → %s", username, country)

    async def _handle_fulbito_subscribe(self, event) -> None:
        from variants.fulbito.config import FULBITO_SUBSCRIBE_DISTANCE
        from core.config import SCREEN_WIDTH
        username = self.sanitize_username(event.username)
        self._club_members.add(username)
        logger.info("Subscribe (club): %s — total members: %d", username, len(self._club_members))
        if self.game_state == 'RACE_RUNNING':
            country = self.viewer_teams.get(username) or self._get_last_place_country()
            if country not in self.current_fixture:
                country = self._get_last_place_country()
            self.physics_world.apply_gift_impulse(country, "subscribe", FULBITO_SUBSCRIBE_DISTANCE)
            self._add_gift_effect(country, FULBITO_SUBSCRIBE_DISTANCE)
        # Big centered text visible in all states
        self._add_floating_text(
            f"NUEVO MIEMBRO DEL CLUB: {username}",
            color=(255, 215, 0),
            x=float(SCREEN_WIDTH / 2),
            y=float(self.physics_world.game_area_top + self.physics_world.lane_y_offset // 2),
        )
        # Increase lifespan of this text by bumping max_lifespan
        if self.floating_texts:
            self.floating_texts[-1].lifespan = 60   # 2s at 30 FPS
            self.floating_texts[-1].max_lifespan = 60
            self.floating_texts[-1].font_size = 22

    def _add_floating_text(
        self,
        text: str,
        color: tuple[int, int, int] = (255, 255, 100),
        x: Optional[float] = None,
        y: Optional[float] = None,
    ) -> None:
        from core.config import SCREEN_WIDTH, SCREEN_HEIGHT
        fx = x if x is not None else SCREEN_WIDTH / 2
        fy = y if y is not None else SCREEN_HEIGHT / 2
        self.floating_texts.append(
            FloatingText(text=text, x=fx, y=fy, color=color, font_size=18)
        )
        if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
            self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]

    def _add_join_text(self, username: str, country: str) -> None:
        """Mundial 2026-styled join notification: country name + @username rising from the racer."""
        from core.config import GAME_AREA_TOP


        pw = self.physics_world
        try:
            lane_idx = self.current_fixture.index(country)
        except ValueError:
            lane_idx = 0

        lane_cy = (
            GAME_AREA_TOP + pw.lane_y_offset
            + lane_idx * pw.lane_height + pw.lane_height // 2
        )
        racer = pw.racers.get(country)
        fx = float(racer.body.position.x) if racer else 230.0

        self.floating_texts.append(FloatingText(
            text=f"{username} → {country}",
            x=fx,
            y=float(lane_cy),
            color=(200, 200, 255),
            font_size=18,
        ))
        if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
            self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]

    def _update_comment_momentum(self, country: str, username: str) -> None:
        from variants.fulbito.config import (
            FULBITO_MOMENTUM_THRESHOLD, FULBITO_MOMENTUM_WINDOW,
        )
        from core.config import GIFT_COLORS, GAME_AREA_TOP
        now = time.time()
        dq = self._comment_momentum.setdefault(country, deque(maxlen=20))
        dq.append((now, username))
        # Prune entries outside the sliding window
        while dq and (now - dq[0][0]) > FULBITO_MOMENTUM_WINDOW:
            dq.popleft()
        unique_viewers = len({u for _, u in dq})
        if unique_viewers < FULBITO_MOMENTUM_THRESHOLD:
            return
        color = GIFT_COLORS.get(country, (255, 220, 60))
        newly_activated = self.effects.activate_momentum(country, color)
        if newly_activated:
            # Text centered on lane, 25px above lane center — never clips at edges
            from core.config import SCREEN_WIDTH
            pw = self.physics_world
            try:
                lane_idx = self.current_fixture.index(country)
            except ValueError:
                lane_idx = 0
            lane_cy = (
                GAME_AREA_TOP + pw.lane_y_offset
                + lane_idx * pw.lane_height + pw.lane_height // 2
            )
            self.floating_texts.append(FloatingText(
                text="¡AL ATAQUE!",
                x=float(SCREEN_WIDTH / 2),   # FloatingText anchors at center
                y=float(lane_cy - 25),
                color=(255, 255, 255),
                font_size=16,
            ))
            if len(self.floating_texts) > self.MAX_FLOATING_TEXTS:
                self.floating_texts = self.floating_texts[-self.MAX_FLOATING_TEXTS:]

    def _add_gift_effect(self, country: str, total_diamonds: int) -> None:
        """Dispatch ring + optional fire trail based on diamond tier."""
        if country not in self.physics_world.racers:
            return
        from core.config import GIFT_COLORS
        from variants.fulbito.config import (
            FULBITO_LANE_DIRECTIONS,
            FULBITO_FIRE_TIER_1, FULBITO_FIRE_TIER_2,
            FULBITO_FIRE_TIER_3, FULBITO_FIRE_TIER_4,
        )
        color = GIFT_COLORS.get(country, (255, 220, 60))
        try:
            idx = self.current_fixture.index(country)
        except ValueError:
            idx = 0
        going_right = FULBITO_LANE_DIRECTIONS.get(idx, True)

        # Ring fires for every gift regardless of tier
        self.effects.add_ring(country, color)

        # Determine fire tier
        if total_diamonds >= FULBITO_FIRE_TIER_4:
            tier = 4
        elif total_diamonds >= FULBITO_FIRE_TIER_3:
            tier = 3
        elif total_diamonds >= FULBITO_FIRE_TIER_2:
            tier = 2
        elif total_diamonds >= FULBITO_FIRE_TIER_1:
            tier = 1
        else:
            tier = 0

        if tier >= 1:
            self.effects.add_fire_trail(country, going_right, tier)
        if tier >= 2:
            self.effects.add_crowd_flash(color)

    # ── State transitions ─────────────────────────────────────────────────────

    def _transition_to_race_running(self) -> None:
        self.game_state = 'RACE_RUNNING'
        self.race_number += 1
        self._race_start_time = time.time()
        self._comment_momentum.clear()
        self.effects.clear_momentum()
        logger.info("Partido %d arrancando: %s", self.race_number, self.current_fixture)

    def _play_goal_sound(self) -> None:
        import pygame
        from core.resources import resource_path
        import os
        path = resource_path("variants/fulbito/assets/goal_sound.mp3")
        if not os.path.exists(path):
            logger.warning("Goal sound not found: %s", path)
            return
        try:
            sound = pygame.mixer.Sound(path)
            sound.set_volume(1.0)
            sound.play()
        except Exception as exc:
            logger.warning("Could not play goal sound: %s", exc)

    def _render_session_podio(self) -> None:
        import pygame
        from core.config import GAME_AREA_TOP, ACTUAL_WIDTH, GAME_MARGIN

        if not self.session_wins:
            return

        sorted_wins = sorted(self.session_wins.items(), key=lambda x: x[1], reverse=True)[:3]

        pw = self.physics_world
        first_lane_top = GAME_MARGIN + GAME_AREA_TOP + pw.lane_y_offset
        # Base de los bloques con mínimo padding antes del primer carril
        # ISO text (~12px) + 2px gap + 4px padding = 18px sobre first_lane_top
        PODIO_BASE_Y = first_lane_top - 30
        cx = ACTUAL_WIDTH // 2

        CONFIGS = [
            {'pos': 2, 'bh': 18, 'bw': 38, 'mcolor': (192, 192, 192)},  # 2do
            {'pos': 1, 'bh': 26, 'bw': 46, 'mcolor': (255, 215, 0)},    # 1ro
            {'pos': 3, 'bh': 14, 'bw': 38, 'mcolor': (205, 127, 50)},   # 3ro
        ]
        SHIELD_SIZE = 20
        GAP = 4

        # Orden visual: 2do | 1ro | 3ro
        # (wins_idx, config_idx): wins[1]=2do→CONFIGS[0](plata), wins[0]=1ro→CONFIGS[1](oro), wins[2]=3ro→CONFIGS[2](bronce)
        visual_slots = [(1, 0), (0, 1), (2, 2)]
        visual_order = [
            (sorted_wins[wi] if wi < len(sorted_wins) else None, CONFIGS[ci])
            for wi, ci in visual_slots
        ]

        total_w = sum(c['bw'] for _, c in visual_order) + GAP * (len(visual_order) - 1)
        start_x = cx - total_w // 2

        font_wins  = pygame.font.SysFont('Arial', 11, bold=True)
        font_iso   = pygame.font.SysFont('Arial', 9,  bold=True)

        x = start_x
        for entry, config in visual_order:
            bw     = config['bw']
            bh     = config['bh']
            mcolor = config['mcolor']
            bcx    = x + bw // 2
            by     = PODIO_BASE_Y - bh

            if entry:
                country, wins = entry

                block = pygame.Surface((bw, bh), pygame.SRCALPHA)
                for row in range(bh):
                    alpha = int(85 * (1 - row / bh) + 34)
                    pygame.draw.line(block, (*mcolor, alpha), (0, row), (bw, row))
                self.screen.blit(block, (x, by))
                pygame.draw.rect(self.screen, (*mcolor, 170), (x, by, bw, bh), 1)

                wins_surf = font_wins.render(f"{wins}v", True, mcolor)
                self.screen.blit(wins_surf, (
                    bcx - wins_surf.get_width() // 2,
                    by + bh // 2 - wins_surf.get_height() // 2,
                ))

                # Escudo desde /escudos/
                from core.resources import resource_path as _rp
                import os as _os
                shield_path = _rp(f"variants/fulbito/assets/escudos/{country}.png")
                shield = None
                try:
                    if _os.path.exists(shield_path):
                        _img = pygame.image.load(shield_path).convert_alpha()
                        shield = pygame.transform.smoothscale(_img, (SHIELD_SIZE, SHIELD_SIZE))
                except Exception:
                    pass
                if shield is None:
                    shield = self._get_country_sprite(country, SHIELD_SIZE)

                shield_y = by - SHIELD_SIZE - 2
                pygame.draw.circle(self.screen, (20, 20, 20), (bcx, shield_y + SHIELD_SIZE // 2), SHIELD_SIZE // 2 + 2)
                pygame.draw.circle(self.screen, mcolor, (bcx, shield_y + SHIELD_SIZE // 2), SHIELD_SIZE // 2 + 2, 1)
                if shield:
                    self.screen.blit(shield, (bcx - SHIELD_SIZE // 2, shield_y))

                # Código ISO debajo del bloque
                iso_surf = font_iso.render(country, True, mcolor)
                self.screen.blit(iso_surf, (bcx - iso_surf.get_width() // 2, PODIO_BASE_Y + 2))

            x += bw + GAP

    def _on_race_finished(self) -> None:
        winner = self.physics_world.winner
        self.king = winner
        if winner:
            self.session_wins[winner] = self.session_wins.get(winner, 0) + 1
        self.game_state = 'RACE_FINISHED'
        self.race_finished_timer = 0.0
        duration = int(time.time() - self._race_start_time) if self._race_start_time else 0
        if self.cloud_manager:
            asyncio.create_task(
                self.cloud_manager.sync_match_result(
                    session_id=self.session_id,
                    variant='fulbito',
                    teams=self.current_fixture,
                    winner=winner,
                    duration_secs=duration,
                )
            )
        logger.info("Partido %d terminado. Ganador: %s", self.race_number, winner)
        import pygame
        pygame.mixer.music.set_volume(0.0 if self._muted else 0.05)
        self._play_goal_sound()
        if winner:
            from core.config import GIFT_COLORS
            winner_color = GIFT_COLORS.get(winner, (255, 215, 0))
            self.effects.add_goal_effect(winner_color)
        self._open_winner_video()

        # Compute race MVP for the winning country.
        self._victory_mvp = None
        if winner and winner in self._race_country_donors:
            donors = self._race_country_donors[winner]
            if donors:
                mvp_user = max(donors, key=donors.__getitem__)
                self._victory_mvp = (mvp_user, donors[mvp_user])

        # Kick off victory particle system.
        self._victory_particles.clear()
        self._firework_timer = 0.0
        if winner and winner in self.physics_world.racers:
            from core.config import GIFT_COLORS
            racer = self.physics_world.racers[winner]
            color = GIFT_COLORS.get(winner, (255, 215, 0))
            bx = float(racer.body.position.x)
            by = float(racer.body.position.y)
            self._spawn_victory_burst(bx, by, color, count=50, speed_range=(3.0, 14.0))

    def _start_intermission(self) -> None:
        self.game_state = 'RACE_INTERMISSION'
        self.intermission_timer = 0.0
        self.intermission_votes = {}
        self.vote_counts = {}
        self.wildcard_country = self._pick_wildcard()
        self._victory_particles.clear()
        if self._winner_video_cap is not None:
            self._winner_video_cap.release()
            self._winner_video_cap = None
            self._winner_video_current_surf = None
        import pygame
        pygame.mixer.music.set_volume(0.0 if self._muted else 0.3)
        logger.info("Intermission. King=%s Wildcard=%s", self.king, self.wildcard_country)

    def _resolve_next_fixture(self) -> list[str]:
        return self._build_fixture_from_votes()

    def _start_next_race(self) -> None:
        new_fixture = self._resolve_next_fixture()
        self.current_fixture = new_fixture
        self._init_fulbito_physics()
        self.viewer_teams = {
            u: c for u, c in self.viewer_teams.items()
            if c in self.current_fixture
        }
        self._race_country_donors.clear()
        self._victory_mvp = None
        self._transition_to_race_running()

    def _confirm_fixture(self) -> None:
        self.current_fixture = [
            FULBITO_ALL_COUNTRIES[self._fixture_country_index[i]]
            for i in range(FULBITO_RACE_COUNTRY_COUNT)
        ]
        self._init_fulbito_physics()
        self.game_state = 'IDLE'
        logger.info("Fixture confirmado: %s", self.current_fixture)

    # ── Update ────────────────────────────────────────────────────────────────

    def update(self, dt: float) -> None:
        self.effects.update(dt)
        self._tribuna_top.update(dt)
        self._tribuna_bot.update(dt)

        if self.game_state == 'FIXTURE_SETUP':
            self.fixture_setup_timer += dt

            if self._draw_phase == 'animating':
                self._draw_spin_time += dt
                self._draw_slot_timer += dt
                if self._draw_slot_timer >= self._draw_slot_duration:
                    self._draw_settled[self._draw_slot_idx] = True
                    self._draw_slot_idx += 1
                    self._draw_slot_timer = 0.0
                    if self._draw_slot_idx >= FULBITO_RACE_COUNTRY_COUNT:
                        self._draw_phase = 'manual'
            else:
                if self._fixture_error_timer > 0:
                    self._fixture_error_timer -= dt
                    if self._fixture_error_timer <= 0:
                        self._fixture_error_msg = ''

            if self.fixture_setup_timer >= 120.0:
                self._confirm_fixture()
            return

        super().update(dt)

        if self.game_state == 'RACE_RUNNING':
            if self.physics_world.race_finished:
                self._on_race_finished()

        elif self.game_state == 'RACE_FINISHED':
            self.race_finished_timer += dt
            if self.physics_world.winner:
                self.winner_animation_time += dt
                pulse_speed = 2.0
                self.winner_scale_pulse = 1.0 + 0.3 * math.sin(
                    self.winner_animation_time * pulse_speed * math.pi
                )
            self._update_victory_particles(dt)
            self._firework_timer += dt
            if self._firework_timer >= 0.75:
                self._firework_timer = 0.0
                self._spawn_random_fireworks()
                self._spawn_confetti_rain()
            if self.race_finished_timer >= 7.0:
                self._start_intermission()

        elif self.game_state == 'RACE_INTERMISSION':
            self.intermission_timer += dt
            if self.intermission_timer >= FULBITO_INTERMISSION_SECONDS:
                self._start_next_race()

    # ── Fixture setup keys ────────────────────────────────────────────────────

    def _handle_fixture_setup_keys(self, event) -> None:
        import pygame
        if self._draw_phase == 'animating':
            return
        if event.key == pygame.K_UP:
            self._fixture_selected_slot = (
                self._fixture_selected_slot - 1
            ) % FULBITO_RACE_COUNTRY_COUNT

        elif event.key == pygame.K_DOWN:
            self._fixture_selected_slot = (
                self._fixture_selected_slot + 1
            ) % FULBITO_RACE_COUNTRY_COUNT

        elif event.key == pygame.K_LEFT:
            slot = self._fixture_selected_slot
            self._fixture_country_index[slot] = (
                self._fixture_country_index.get(slot, 0) - 1
            ) % len(FULBITO_ALL_COUNTRIES)

        elif event.key == pygame.K_RIGHT:
            slot = self._fixture_selected_slot
            self._fixture_country_index[slot] = (
                self._fixture_country_index.get(slot, 0) + 1
            ) % len(FULBITO_ALL_COUNTRIES)

        elif event.key == pygame.K_RETURN:
            selected = [
                FULBITO_ALL_COUNTRIES[self._fixture_country_index.get(i, 0)]
                for i in range(FULBITO_RACE_COUNTRY_COUNT)
            ]
            if len(set(selected)) < FULBITO_RACE_COUNTRY_COUNT:
                self._fixture_error_msg = 'Hay países duplicados'
                self._fixture_error_timer = 2.5
                return
            self.current_fixture = selected
            self._confirm_fixture()

    # ── Pygame event loop ─────────────────────────────────────────────────────

    def handle_pygame_events(self) -> None:
        import pygame
        # Handle all events in one pass to avoid double-consuming the queue.
        # Common events (QUIT, ESC) are handled inline; super() is NOT called
        # since core.handle_pygame_events() would drain pygame.event.get() first.
        try:
            events = pygame.event.get()
        except Exception as e:
            logger.exception("Error getting pygame events: %s", e)
            return

        for event in events:
            if event.type == pygame.QUIT:
                self.running = False
                return
            if event.type != pygame.KEYDOWN:
                continue

            if event.key == pygame.K_ESCAPE:
                _now = time.time()
                if not self._esc_quit_requested:
                    self._esc_quit_requested = True
                    self._esc_quit_time = _now
                elif (_now - self._esc_quit_time) < self._esc_quit_window:
                    self.running = False
                else:
                    self._esc_quit_requested = True
                    self._esc_quit_time = _now
                continue

            if event.key == pygame.K_m:
                self._toggle_mute()
                continue

            if self.game_state == 'FIXTURE_SETUP':
                self._handle_fixture_setup_keys(event)
                continue

            # Demo keys — cualquier estado excepto FIXTURE_SETUP
            if event.key == pygame.K_f:
                from core.events import GameEvent
                fake = GameEvent(
                    type=EventType.GIFT,
                    username='testviewer',
                    content='Hand Heart',
                    extra={'diamond_count': 500, 'count': 1},
                )
                asyncio.create_task(self._handle_fulbito_gift(fake))

            elif event.key == pygame.K_c:
                from core.events import GameEvent
                fake = GameEvent(
                    type=EventType.COMMENT,
                    username='testviewer',
                    content='ARG',
                    extra={},
                )
                asyncio.create_task(self._handle_fulbito_comment(fake))

            elif event.key == pygame.K_w:
                if self.game_state == 'RACE_INTERMISSION':
                    self.wildcard_country = self._pick_wildcard()
                    logger.info("Wildcard rerolleado: %s", self.wildcard_country)

            elif event.key == pygame.K_RETURN:
                if self.game_state == 'RACE_INTERMISSION':
                    self._start_next_race()

            elif event.key == pygame.K_t:
                # Test: tier 0 — ring only (< 10💎)
                from core.events import GameEvent
                fake = GameEvent(type=EventType.GIFT, username='testviewer',
                                 content='Rosa', extra={'diamond_count': 5, 'count': 1})
                asyncio.create_task(self._handle_fulbito_gift(fake))

            elif event.key == pygame.K_1:
                # Test: tier 1 fire — 10–49💎
                from core.events import GameEvent
                fake = GameEvent(type=EventType.GIFT, username='testviewer',
                                 content='Perfume', extra={'diamond_count': 10, 'count': 1})
                asyncio.create_task(self._handle_fulbito_gift(fake))

            elif event.key == pygame.K_2:
                # Test: tier 2 fire — 50–199💎
                from core.events import GameEvent
                fake = GameEvent(type=EventType.GIFT, username='testviewer',
                                 content='TikTok', extra={'diamond_count': 50, 'count': 1})
                asyncio.create_task(self._handle_fulbito_gift(fake))

            elif event.key == pygame.K_3:
                # Test: tier 3 fire — 200–499💎
                from core.events import GameEvent
                fake = GameEvent(type=EventType.GIFT, username='testviewer',
                                 content='Galaxy', extra={'diamond_count': 200, 'count': 1})
                asyncio.create_task(self._handle_fulbito_gift(fake))

            elif event.key == pygame.K_4:
                # Test: tier 4 fire + burst — 500+💎
                from core.events import GameEvent
                fake = GameEvent(type=EventType.GIFT, username='testviewer',
                                 content='Universe', extra={'diamond_count': 500, 'count': 1})
                asyncio.create_task(self._handle_fulbito_gift(fake))

            elif event.key == pygame.K_g:
                # Test: force goal for first country in fixture → goal flash + confetti
                if self.game_state == 'RACE_RUNNING' and self.current_fixture:
                    winner = self.current_fixture[0]
                    self.physics_world.winner = winner
                    self.physics_world.race_finished = True
                    logger.info("[TEST] Forced goal for %s", winner)

            elif event.key == pygame.K_r:
                self.game_state = 'FIXTURE_SETUP'
                self.fixture_setup_timer = 0.0
                self.race_number = 0
                self.king = None
                self.viewer_teams = {}
                self.current_fixture = list(FULBITO_DEFAULT_FIXTURE)
                self._init_fulbito_physics()
                logger.info("Reset completo a FIXTURE_SETUP")

    # ── Render ────────────────────────────────────────────────────────────────

    def render_background(self) -> None:
        import pygame
        logger.debug("[RENDER_BG] outer_background size=%s",
            (self.outer_background.get_width(),
             self.outer_background.get_height())
            if self.outer_background else None
        )
        if self.screen:
            self.screen.blit(self.outer_background, (0, 0))

    def _update_outer_background(self) -> None:
        """Pinta las franjas verdes de los carriles en outer_background (ancho completo).

        outer_background se blit-ea al inicio de cada frame ANTES del render_surface.
        render_surface cubre x=40..500; los márgenes x=0..40 y x=500..540 quedan del
        outer_background, por lo que las franjas aquí extienden el campo de borde a borde.
        """
        import pygame
        from core.config import ACTUAL_WIDTH, GAME_MARGIN, GAME_AREA_TOP
        ob = getattr(self, 'outer_background', None)
        pw = getattr(self, 'physics_world', None)
        if ob is None or pw is None:
            return
        # Resetear antes de redibujar para no acumular contenido de partidas anteriores
        ob.fill((10, 10, 10))
        STRIPE_H = 10
        LANE_COLORS = [
            ((29, 82, 16), (35, 79, 20)),
            ((24, 86, 14), (29, 90, 18)),
            ((29, 82, 16), (35, 79, 20)),
            ((24, 86, 14), (29, 90, 18)),
        ]
        for i in range(len(self.current_fixture)):
            dark, light = LANE_COLORS[i % len(LANE_COLORS)]
            lane_y_s = GAME_MARGIN + GAME_AREA_TOP + pw.lane_y_offset + i * pw.lane_height
            stripe_idx = 0
            y = lane_y_s
            while y < lane_y_s + pw.lane_height:
                color = dark if stripe_idx % 2 == 0 else light
                stripe_bottom = min(y + STRIPE_H, lane_y_s + pw.lane_height)
                pygame.draw.rect(ob, color, (0, y, ACTUAL_WIDTH, stripe_bottom - y))
                y += STRIPE_H
                stripe_idx += 1
        for i in range(1, len(self.current_fixture)):
            y = GAME_MARGIN + GAME_AREA_TOP + pw.lane_y_offset + i * pw.lane_height
            pygame.draw.line(ob, (20, 55, 8), (0, y), (ACTUAL_WIDTH, y), 1)
        logger.info(
            "[OB UPDATE] fixture=%s lane_h=%s lane_y_offset=%s "
            "ob_size=%s carriles_dibujados=%s",
            self.current_fixture,
            pw.lane_height,
            pw.lane_y_offset,
            (ob.get_width(), ob.get_height()),
            len(self.current_fixture)
        )

    def _render_tribunas(self) -> None:
        """Renderiza tribuna top y bottom directamente en self.screen (ACTUAL_WIDTH completo)."""
        if hasattr(self, '_tribuna_top'):
            self._tribuna_top.render(self.screen, x=0, y=0, flip=False)
        if getattr(self, '_tribuna_bot', None):
            from core.config import GAME_MARGIN
            self._tribuna_bot.render(self.screen, x=0,
                y=self._tribuna_bot_y + GAME_MARGIN + 20, flip=True)

    def render(self) -> None:
        import pygame
        if self.game_state == 'FIXTURE_SETUP':
            self.render_background()
            self._render_tribunas()
            self._render_fixture_setup()
            pygame.display.flip()
            return
        super().render()
        # Fulbito HUD is injected via _pre_flip_screen_overlay(),
        # called by super().render() just before display.flip().

    def _render_racer(self, racer, is_winner: bool = False) -> None:
        import pygame
        import math
        import random

        if racer.sprite is None:
            super()._render_racer(racer, is_winner)
            return

        country = racer.country
        angle = self.physics_world._rotation_angles.get(country, 0.0)

        x = float(racer.body.position.x)
        y = float(racer.body.position.y) + (racer.y_offset if hasattr(racer, 'y_offset') else 0.0)

        is_frozen = self.physics_world.is_country_frozen(country)
        if is_frozen:
            x += random.uniform(-3, 3)
            y += random.uniform(-2, 2)
        elif country in self.on_fire_countries:
            x += random.uniform(-2, 2)
            y += random.uniform(-2, 2)

        scale = self.winner_scale_pulse if is_winner else 1.0
        size = int(racer.draw_radius * 2 * scale)
        if size < 4:
            return

        scaled = pygame.transform.smoothscale(racer.sprite, (size, size))
        rotated = pygame.transform.rotate(scaled, -angle)

        blit_x = self._safe_int(x, self.physics_world.start_x) - rotated.get_width() // 2
        blit_y = self._safe_int(y, 0) - rotated.get_height() // 2
        # Draw momentum aura BEFORE the sprite so the ball appears on top
        self.effects.draw_aura_on_surface(self.render_surface, country, x, y)
        self.render_surface.blit(rotated, (blit_x, blit_y))

        if is_winner:
            glow = pygame.Surface((rotated.get_width(), rotated.get_height()), pygame.SRCALPHA)
            pygame.draw.circle(
                glow, (255, 215, 0, 40),
                (rotated.get_width() // 2, rotated.get_height() // 2),
                rotated.get_width() // 2,
            )
            self.render_surface.blit(glow, (blit_x, blit_y))

    def _pre_flip_screen_overlay(self) -> None:
        self._render_tribunas()
        if self.game_state == 'IDLE':
            self._render_overlay_text()
        elif self.game_state == 'RACE_RUNNING':
            self.effects.render_game_effects()
            self.effects.render_screen_effects()
            self._render_gift_flashes()
            self._render_direction_arrows()
            self._render_country_names()
            self._render_session_podio()
            self._render_overlay_text()
        elif self.game_state == 'RACE_FINISHED':
            self._render_country_names()
            self._render_winner_banner()
            self.effects.render_screen_effects()  # goal flash + confetti on top of banner
        elif self.game_state == 'RACE_INTERMISSION':
            self._render_country_names()
            self._render_intermission_panel()

    def _render_gift_flashes(self) -> None:
        """Draw a brief impact flash on racers that just received a gift impulse.

        Two-phase effect lasting ``_FLASH_DURATION`` seconds:
        - Phase 1 (0–0.2 s): white burst ring expands outward + bright filled core.
        - Phase 2 (0.2–1.0 s): country-colored glow ring fades out.

        Larger diamond counts produce a proportionally bigger burst radius.
        """
        import pygame
        _FLASH_DURATION = 1.0
        _BURST_END = 0.2

        now = time.time()
        expired = []

        for country, (start_t, diamonds) in list(self._gift_flashes.items()):
            elapsed = now - start_t
            if elapsed >= _FLASH_DURATION:
                expired.append(country)
                continue

            if country not in self.physics_world.racers:
                expired.append(country)
                continue

            racer = self.physics_world.racers[country]
            from core.config import GAME_MARGIN as _GM
            cx = int(racer.body.position.x) + _GM
            cy = int(racer.body.position.y) + _GM
            base_r = racer.draw_radius

            # Scale burst with gift size: small, medium, large tiers.
            scale = 1.0 + min(0.8, diamonds / 50.0)

            from core.config import GIFT_COLORS
            country_color = GIFT_COLORS.get(country, (255, 220, 60))

            if elapsed < _BURST_END:
                t = elapsed / _BURST_END  # 0 → 1

                # White burst ring expanding outward.
                ring_r = int(base_r * scale * (1.0 + t * 1.8))
                ring_alpha = int(255 * (1.0 - t * 0.5))
                ring_surf = pygame.Surface((ring_r * 2 + 6, ring_r * 2 + 6), pygame.SRCALPHA)
                pygame.draw.circle(
                    ring_surf, (255, 255, 255, ring_alpha),
                    (ring_r + 3, ring_r + 3), ring_r, 4,
                )
                self.screen.blit(ring_surf, (cx - ring_r - 3, cy - ring_r - 3))

                # Bright country-colored filled core that fades quickly.
                core_r = int(base_r * scale * (0.9 - t * 0.6))
                if core_r > 0:
                    core_alpha = int(220 * (1.0 - t))
                    bright = tuple(min(255, int(c * 1.5)) for c in country_color)
                    core_surf = pygame.Surface((core_r * 2, core_r * 2), pygame.SRCALPHA)
                    pygame.draw.circle(
                        core_surf, (*bright, core_alpha),
                        (core_r, core_r), core_r,
                    )
                    self.screen.blit(core_surf, (cx - core_r, cy - core_r))

            else:
                t = (elapsed - _BURST_END) / (_FLASH_DURATION - _BURST_END)  # 0 → 1

                # Country-colored glow ring that shrinks and fades.
                glow_r = int(base_r * scale * (2.5 - t * 1.2))
                glow_alpha = int(180 * (1.0 - t))
                glow_surf = pygame.Surface((glow_r * 2 + 4, glow_r * 2 + 4), pygame.SRCALPHA)
                pygame.draw.circle(
                    glow_surf, (*country_color, glow_alpha),
                    (glow_r + 2, glow_r + 2), glow_r, 3,
                )
                self.screen.blit(glow_surf, (cx - glow_r - 2, cy - glow_r - 2))

        for c in expired:
            self._gift_flashes.pop(c, None)

    def _render_overlay_text(self, text: str = '') -> None:
        import pygame
        from core.config import GAME_AREA_TOP, GAME_MARGIN, ACTUAL_WIDTH
        from variants.fulbito.config import FULBITO_COUNTRY_NAMES

        if not self.current_fixture:
            return

        font_big   = pygame.font.SysFont('Arial', 18, bold=True)
        font_small = pygame.font.SysFont('Arial', 14)

        line1 = "Escribi el nombre de tu pais en el chat para unirte:"
        names = [FULBITO_COUNTRY_NAMES.get(c, c) for c in self.current_fixture]
        line2 = "  |  ".join(names)

        surf1 = font_big.render(line1, True, (255, 255, 180))
        surf2 = font_small.render(line2, True, (255, 230, 50))

        pw = self.physics_world
        num_lanes = len(self.current_fixture)
        last_lane_bottom = GAME_AREA_TOP + pw.lane_y_offset + num_lanes * pw.lane_height
        y1 = last_lane_bottom + GAME_MARGIN + 10
        y2 = y1 + surf1.get_height() + 4

        PAD_X, PAD_Y = 14, 8
        box_w = max(surf1.get_width(), surf2.get_width()) + PAD_X * 2
        box_h = surf1.get_height() + surf2.get_height() + PAD_Y * 2 + 4
        box_x = ACTUAL_WIDTH // 2 - box_w // 2
        box_y = y1 - PAD_Y

        bg = pygame.Surface((box_w, box_h), pygame.SRCALPHA)
        bg.fill((0, 0, 0, 175))
        pygame.draw.rect(bg, (255, 255, 180, 60), (0, 0, box_w, box_h), 1, border_radius=6)
        self.screen.blit(bg, (box_x, box_y))

        x1 = ACTUAL_WIDTH // 2 - surf1.get_width() // 2
        x2 = ACTUAL_WIDTH // 2 - surf2.get_width() // 2
        self.screen.blit(font_big.render(line1, True, (0, 0, 0)), (x1 + 1, y1 + 1))
        self.screen.blit(surf1, (x1, y1))
        self.screen.blit(font_small.render(line2, True, (0, 0, 0)), (x2 + 1, y2 + 1))
        self.screen.blit(surf2, (x2, y2))

    def _render_direction_arrows(self) -> None:
        import pygame
        from core.config import GAME_AREA_TOP, SCREEN_WIDTH
        from variants.fulbito.config import FULBITO_LANE_DIRECTIONS

        BAR_H   = 8    # altura de la barra
        BAR_W   = 60   # ancho de la barra sin la punta
        ARROW_W = 12   # ancho de la punta triangular
        ARROW_H = 16   # altura total de la punta

        for i, country in enumerate(self.current_fixture):
            if country not in self.physics_world.racers:
                continue
            racer = self.physics_world.racers[country]
            cy = int(racer.body.position.y)
            going_right = FULBITO_LANE_DIRECTIONS.get(i, True)

            if going_right:
                bar_x = 8
                bar_y = cy - BAR_H // 2
                color_solid = (100, 255, 100)
                grad_surf = pygame.Surface((BAR_W, BAR_H), pygame.SRCALPHA)
                for px in range(BAR_W):
                    alpha = int(255 * (px / BAR_W))
                    pygame.draw.line(grad_surf, (*color_solid, alpha),
                                     (px, 0), (px, BAR_H))
                self.screen.blit(grad_surf, (bar_x, bar_y))
                tip_x = bar_x + BAR_W
                pygame.draw.polygon(self.screen, color_solid, [
                    (tip_x, cy - ARROW_H // 2),
                    (tip_x + ARROW_W, cy),
                    (tip_x, cy + ARROW_H // 2),
                ])
            else:
                color_solid = (100, 150, 255)
                # Tip points LEFT; right edge of arrowhead at SCREEN_WIDTH - 8
                tip_x = SCREEN_WIDTH - 8 - ARROW_W
                bar_x = tip_x + ARROW_W
                bar_y = cy - BAR_H // 2

                pygame.draw.polygon(self.screen, color_solid, [
                    (tip_x,           cy),
                    (tip_x + ARROW_W, cy - ARROW_H // 2),
                    (tip_x + ARROW_W, cy + ARROW_H // 2),
                ])

                grad_surf = pygame.Surface((BAR_W, BAR_H), pygame.SRCALPHA)
                for px in range(BAR_W):
                    alpha = int(255 * (1 - px / BAR_W))
                    pygame.draw.line(grad_surf, (*color_solid, alpha),
                                     (px, 0), (px, BAR_H))
                self.screen.blit(grad_surf, (bar_x, bar_y))

    # ── Victory particle system ───────────────────────────────────────────────

    def _spawn_victory_burst(
        self,
        cx: float,
        cy: float,
        color: tuple,
        count: int = 30,
        speed_range: tuple = (2.0, 9.0),
    ) -> None:
        """Emit a radial burst of sparks and confetti from (cx, cy).

        Args:
            cx: Horizontal center of the burst in screen coordinates.
            cy: Vertical center of the burst in screen coordinates.
            color: Base RGB tuple for the burst; alternated with gold.
            count: Number of particles to emit.
            speed_range: (min, max) initial speed in px/frame.
        """
        r, g, b = int(color[0]), int(color[1]), int(color[2])
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(*speed_range)
            cr, cg, cb = (r, g, b) if random.random() < 0.5 else (255, 210, 30)
            kind = 1 if random.random() < 0.35 else 0
            # [x, y, vx, vy, r, g, b, life, decay, size, kind, angle, spin]
            self._victory_particles.append([
                cx + random.uniform(-6, 6),
                cy + random.uniform(-6, 6),
                math.cos(angle) * speed,
                math.sin(angle) * speed - random.uniform(0, 2.5),
                cr, cg, cb,
                1.0,
                random.uniform(0.45, 1.1),
                random.randint(3, 7),
                kind,
                random.uniform(0.0, 360.0),
                random.uniform(-9.0, 9.0),
            ])

    def _spawn_random_fireworks(self) -> None:
        """Launch 2–3 firework bursts at random positions across the game area.

        Uses the winning country's color mixed with gold and white accents.
        """
        from core.config import GAME_AREA_TOP, SCREEN_HEIGHT, GAME_AREA_BOTTOM, ACTUAL_WIDTH, GIFT_COLORS
        winner = self.physics_world.winner or ''
        base_color = GIFT_COLORS.get(winner, (255, 215, 0))
        game_top = GAME_AREA_TOP
        game_bottom = SCREEN_HEIGHT - GAME_AREA_BOTTOM
        burst_colors = [base_color, (255, 210, 30), (255, 255, 255)]
        for _ in range(random.randint(2, 3)):
            bx = random.uniform(ACTUAL_WIDTH * 0.15, ACTUAL_WIDTH * 0.85)
            by = random.uniform(game_top + 20, game_top + (game_bottom - game_top) * 0.55)
            color = random.choice(burst_colors)
            self._spawn_victory_burst(bx, by, color, count=random.randint(22, 32), speed_range=(2.5, 10.0))

    def _spawn_confetti_rain(self, count: int = 12) -> None:
        """Release confetti pieces falling from the top of the game area.

        Args:
            count: Number of confetti pieces to spawn.
        """
        from core.config import GAME_AREA_TOP, ACTUAL_WIDTH
        colors = [
            (255, 80, 80), (80, 200, 80), (80, 120, 255),
            (255, 220, 50), (200, 80, 200), (60, 210, 210),
            (255, 140, 30),
        ]
        for _ in range(count):
            cr, cg, cb = random.choice(colors)
            self._victory_particles.append([
                random.uniform(15.0, float(ACTUAL_WIDTH) - 15.0),
                float(GAME_AREA_TOP),
                random.uniform(-1.2, 1.2),
                random.uniform(2.0, 4.5),
                cr, cg, cb,
                1.0,
                random.uniform(0.12, 0.3),
                random.randint(4, 8),
                1,
                random.uniform(0.0, 360.0),
                random.uniform(-5.0, 5.0),
            ])

    def _update_victory_particles(self, dt: float) -> None:
        """Advance physics for all victory particles and remove expired ones.

        Args:
            dt: Frame delta time in seconds.
        """
        gravity = 0.20
        friction = 0.982
        surviving = []
        for p in self._victory_particles:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += gravity
            p[2] *= friction
            p[7] -= p[8] * dt
            p[11] += p[12]
            if p[7] > 0:
                surviving.append(p)
        self._victory_particles = surviving

    def _render_victory_particles(self) -> None:
        """Blit all active victory particles onto the screen surface."""
        import pygame
        for p in self._victory_particles:
            life = p[7]
            if life <= 0:
                continue
            alpha = min(255, int(255 * life))
            x, y = int(p[0]), int(p[1])
            size = max(1, int(p[9]))
            color = (int(p[4]), int(p[5]), int(p[6]))
            kind = int(p[10])
            if kind == 0:
                diam = size * 2
                surf = pygame.Surface((diam, diam), pygame.SRCALPHA)
                pygame.draw.circle(surf, (*color, alpha), (size, size), size)
                self.screen.blit(surf, (x - size, y - size))
            else:
                w, h = size + 2, max(1, size // 2 + 1)
                base = pygame.Surface((w, h), pygame.SRCALPHA)
                base.fill((*color, alpha))
                rotated = pygame.transform.rotate(base, p[11])
                rw, rh = rotated.get_size()
                self.screen.blit(rotated, (x - rw // 2, y - rh // 2))

    # ── Winner banner ─────────────────────────────────────────────────────────

    def _render_winner_banner(self) -> None:
        """Render the victory overlay: fireworks, winner flag, country name, MVP, countdown."""
        import pygame
        from core.config import (
            SCREEN_HEIGHT, GAME_AREA_TOP, GAME_AREA_BOTTOM, ACTUAL_WIDTH, GIFT_COLORS,
            GAME_MARGIN,
        )
        from variants.fulbito.config import FULBITO_COUNTRY_NAMES

        winner = self.physics_world.winner or ''
        if not winner:
            return

        remaining = max(0, 7.0 - self.race_finished_timer)
        winner_name = FULBITO_COUNTRY_NAMES.get(winner, winner)
        country_color = GIFT_COLORS.get(winner, (255, 215, 0))

        game_top    = GAME_AREA_TOP + GAME_MARGIN
        game_bottom = (SCREEN_HEIGHT - GAME_AREA_BOTTOM) + GAME_MARGIN
        game_h      = game_bottom - game_top
        center_x    = ACTUAL_WIDTH // 2
        center_y    = game_top + game_h // 2

        # ── Background overlay ────────────────────────────────────────────────
        if self._wc2026_bg is not None:
            self.screen.blit(self._wc2026_bg, (0, game_top))
        else:
            overlay = pygame.Surface((ACTUAL_WIDTH, game_h), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 210))
            self.screen.blit(overlay, (0, game_top))

        # ── Fireworks / confetti ──────────────────────────────────────────────
        self._render_victory_particles()

        # ── Pulsing country flag sprite ───────────────────────────────────────
        if winner in self.physics_world.racers:
            racer = self.physics_world.racers[winner]
            if racer.sprite:
                sprite_size = int(120 * self.winner_scale_pulse)
                scaled = pygame.transform.smoothscale(racer.sprite, (sprite_size, sprite_size))
                self.screen.blit(
                    scaled,
                    (center_x - sprite_size // 2, center_y - sprite_size // 2 - 55),
                )

        # ── "¡GANÓ!" ──────────────────────────────────────────────────────────
        font_gano = pygame.font.SysFont('Arial', 26, bold=True)
        _gano_base = font_gano.render("¡GANÓ!", True, (255, 255, 255))
        gx = center_x - _gano_base.get_width() // 2
        gy = center_y + 42
        _gano_outlined = self._render_text_enhanced("¡GANÓ!", font_gano, (255, 255, 255), (0, 0, 0), 2)
        self.screen.blit(_gano_outlined, (gx - 2, gy - 2))

        # ── Country name ──────────────────────────────────────────────────────
        font_name = pygame.font.SysFont('Arial', 46, bold=True)
        _name_base = font_name.render(winner_name, True, (255, 220, 0))
        nx = center_x - _name_base.get_width() // 2
        ny = center_y + 70
        _name_outlined = self._render_text_enhanced(winner_name, font_name, (255, 220, 0), (0, 0, 0), 3)
        self.screen.blit(_name_outlined, (nx - 3, ny - 3))

        # ── Winner video (below last lane → bottom of screen) ────────────────
        self._advance_winner_video()
        if self._winner_video_current_surf:
            vx, vy, _, _ = self._winner_video_rect
            self.screen.blit(self._winner_video_current_surf, (vx, vy))

        # ── Countdown ─────────────────────────────────────────────────────────
        cd_y = center_y + 150
        font_cd = pygame.font.SysFont('Arial', 15)
        cd_text = f"Próximo partido en {remaining:.0f}s"
        cd_surf = font_cd.render(cd_text, True, (170, 170, 170))
        cx2 = center_x - cd_surf.get_width() // 2
        self.screen.blit(font_cd.render(cd_text, True, (0, 0, 0)), (cx2 + 1, cd_y + 1))
        self.screen.blit(cd_surf, (cx2, cd_y))

    def _render_intermission_panel(self) -> None:
        import pygame
        from core.config import (
            SCREEN_WIDTH, SCREEN_HEIGHT,
            GAME_AREA_TOP, GAME_AREA_BOTTOM,
            ACTUAL_WIDTH, GAME_MARGIN,
        )
        from variants.fulbito.config import (
            FULBITO_COUNTRY_NAMES,
            FULBITO_INTERMISSION_SECONDS
        )

        remaining = max(0, FULBITO_INTERMISSION_SECONDS - self.intermission_timer)
        game_top    = GAME_AREA_TOP + GAME_MARGIN
        game_bottom = (SCREEN_HEIGHT - GAME_AREA_BOTTOM) + GAME_MARGIN
        game_h      = game_bottom - game_top
        cx          = ACTUAL_WIDTH // 2
        cy          = game_top + game_h // 2

        # Overlay oscuro sobre todo el game area
        overlay = pygame.Surface((ACTUAL_WIDTH, game_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 215))
        self.screen.blit(overlay, (0, game_top))

        # Countdown grande centrado
        font_cd = pygame.font.SysFont('Arial', 56, bold=True)
        cd_text = f"{remaining:.0f}"
        cd_color = (255, 60, 60) if remaining <= 5 else (255, 100, 100)
        cd_surf = font_cd.render(cd_text, True, cd_color)
        cdx = cx - cd_surf.get_width() // 2
        cdy = cy - 120
        self.screen.blit(font_cd.render(cd_text, True, (0,0,0)), (cdx+2, cdy+2))
        self.screen.blit(cd_surf, (cdx, cdy))

        # Título justo encima del countdown
        font_title = pygame.font.SysFont('Arial', 16, bold=True)
        title_surf = font_title.render("PRÓXIMO PARTIDO", True, (255, 255, 255))
        tx = cx - title_surf.get_width() // 2
        ty = cdy - title_surf.get_height() - 6
        self.screen.blit(font_title.render("PRÓXIMO PARTIDO", True, (0, 0, 0)), (tx + 2, ty + 2))
        self.screen.blit(title_surf, (tx, ty))

        # "segundos para votar"
        font_sub = pygame.font.SysFont('Arial', 13)
        sub_surf = font_sub.render("segundos para votar", True, (200, 200, 200))
        self.screen.blit(sub_surf,
            (cx - sub_surf.get_width()//2, cdy + 70))

        # ── CTA dinámico ─────────────────────────────────────────────────────
        # Rotates every 5 s, pulses at ~3 Hz. Sits in the gap between the
        # countdown subtext and the candidates separator.
        CTA_MESSAGES = [
            (
                "\u00bfTu pa\u00eds no est\u00e1? \u00a1Coment\u00e1lo ahora!",
                "Los 2 m\u00e1s comentados entran a la pr\u00f3xima",
            ),
            (
                "\u00a1El chat decide el fixture!",
                "Escrib\u00ed el nombre de tu pa\u00eds para votar",
            ),
            (
                "\u00a1Llev\u00e1 a tu selecci\u00f3n a la victoria!",
                "M\u00e1s comentarios = m\u00e1s posibilidades de entrar",
            ),
        ]
        pulse = 0.5 + 0.5 * math.sin(self.intermission_timer * math.pi * 3.0)
        msg_idx = int(self.intermission_timer / 5) % len(CTA_MESSAGES)
        cta_line1, cta_line2 = CTA_MESSAGES[msg_idx]

        cta_margin = 18
        cta_top = cdy + 90
        cta_h = 68
        cta_w = ACTUAL_WIDTH - cta_margin * 2

        # Semi-transparent warm background
        bg_alpha = int(35 + 25 * pulse)
        cta_bg = pygame.Surface((cta_w, cta_h), pygame.SRCALPHA)
        cta_bg.fill((255, 160, 0, bg_alpha))
        self.screen.blit(cta_bg, (cta_margin, cta_top))

        # Pulsing border
        border_alpha = int(140 + 115 * pulse)
        border_surf = pygame.Surface((cta_w, cta_h), pygame.SRCALPHA)
        pygame.draw.rect(border_surf, (255, 210, 30, border_alpha),
                         (0, 0, cta_w, cta_h), 2)
        self.screen.blit(border_surf, (cta_margin, cta_top))

        # Line 1 — main CTA message
        font_cta1 = pygame.font.SysFont('Arial', 14, bold=True)
        s1 = font_cta1.render(cta_line1, True, (255, 240, 80))
        x1 = cx - s1.get_width() // 2
        y1 = cta_top + 8
        self.screen.blit(font_cta1.render(cta_line1, True, (0, 0, 0)), (x1 + 1, y1 + 1))
        self.screen.blit(s1, (x1, y1))

        # Line 2 — supporting text
        font_cta2 = pygame.font.SysFont('Arial', 12)
        s2 = font_cta2.render(cta_line2, True, (255, 255, 255))
        x2 = cx - s2.get_width() // 2
        y2 = cta_top + 28
        self.screen.blit(font_cta2.render(cta_line2, True, (0, 0, 0)), (x2 + 1, y2 + 1))
        self.screen.blit(s2, (x2, y2))

        # Animated ">>> COMENTÁ >>>" arrows — intensity grows as time runs out
        urgency = 1.0 - max(0.0, remaining / FULBITO_INTERMISSION_SECONDS)
        arrow_count = 1 + int(urgency * 2)  # 1-3 arrows
        arrows = '>' * arrow_count
        arrow_text = f"{arrows}  COMENT\u00c1  {arrows[::-1]}"
        arrow_r = int(220 + 35 * pulse)
        arrow_g = int(100 + 80 * (1.0 - urgency))
        font_arrow = pygame.font.SysFont('Arial', 11, bold=True)
        arrow_surf = font_arrow.render(arrow_text, True, (arrow_r, arrow_g, 0))
        ax = cx - arrow_surf.get_width() // 2 + int(3 * pulse)
        self.screen.blit(arrow_surf, (ax, cta_top + 48))

        # Línea separadora
        pygame.draw.line(self.screen,
            (255, 255, 255, 30),
            (20, cy + 50),
            (ACTUAL_WIDTH - 20, cy + 50), 1)

        # Candidatos — pelotas con etiquetas
        # Resolver fixture siguiente: King + Wildcard + slot de votos
        candidates = []

        # King
        if self.king:
            candidates.append({
                'code': self.king,
                'name': FULBITO_COUNTRY_NAMES.get(self.king, self.king),
                'tag': 'KING',
                'tag_color': (255, 215, 0),
            })

        # Top votos Crowd
        sorted_votes = sorted(
            self.vote_counts.items(),
            key=lambda x: x[1], reverse=True
        )
        for country, votes in sorted_votes[:2]:
            if country != self.king:
                candidates.append({
                    'code': country,
                    'name': FULBITO_COUNTRY_NAMES.get(country, country),
                    'tag': f'{votes} votos',
                    'tag_color': (150, 220, 255),
                })

        # Wildcard
        if self.wildcard_country and self.wildcard_country not in [c['code'] for c in candidates]:
            candidates.append({
                'code': self.wildcard_country,
                'name': FULBITO_COUNTRY_NAMES.get(self.wildcard_country, self.wildcard_country),
                'tag': 'Wildcard',
                'tag_color': (150, 255, 150),
            })

        # Distribuir pelotas horizontalmente
        n = len(candidates)
        if n > 0:
            ball_y = cy + 65
            spacing = ACTUAL_WIDTH // (n + 1)
            font_ball  = pygame.font.SysFont('Arial', 9, bold=True)
            font_tag   = pygame.font.SysFont('Arial', 11)

            for i, cand in enumerate(candidates):
                bx = spacing * (i + 1)
                radius = 32

                code = cand['code']
                sprite = self._get_country_sprite(code, radius * 2)
                roll_angle = math.sin(self.intermission_timer * 1.4 + i * 1.1) * 18
                if sprite:
                    rotated = pygame.transform.rotate(sprite, roll_angle)
                    self.screen.blit(rotated, (bx - rotated.get_width() // 2, ball_y - rotated.get_height() // 2))
                else:
                    pygame.draw.circle(self.screen, (100, 100, 100), (bx, ball_y), radius)

                # Nombre del país
                name_s = font_ball.render(cand['name'], True, (255,255,255))
                self.screen.blit(name_s,
                    (bx - name_s.get_width()//2, ball_y + radius + 4))

                # Tag (King / votos / Wildcard)
                tag_s = font_tag.render(cand['tag'], True, cand['tag_color'])
                self.screen.blit(tag_s,
                    (bx - tag_s.get_width()//2, ball_y + radius + 18))

        # ── Bottom urgency hint ───────────────────────────────────────────────
        # Color shifts from calm white→yellow to urgent red as time runs low.
        urgency_b = 1.0 - max(0.0, remaining / FULBITO_INTERMISSION_SECONDS)
        if remaining <= 5:
            hint_color = (255, int(80 * (remaining / 5)), 0)
            hint = f"\u00a1{remaining:.0f}s! \u00a1ESCRIB\u00cd TU PA\u00cdS EN EL CHAT YA!"
        else:
            t = urgency_b
            hint_color = (255, int(255 - 75 * t), int(180 - 180 * t))
            hint = "\u25ba  Escrib\u00ed el nombre de tu pa\u00eds para votar  \u25c4"
        font_hint = pygame.font.SysFont('Arial', 12, bold=(remaining <= 5))
        hint_surf = font_hint.render(hint, True, hint_color)
        hint_shadow = font_hint.render(hint, True, (0, 0, 0))
        hx = cx - hint_surf.get_width() // 2
        hy = cy + 65 + 32 + 30
        self.screen.blit(hint_shadow, (hx + 1, hy + 1))
        self.screen.blit(hint_surf, (hx, hy))

    def _get_country_sprite(self, country: str, size: int):
        import pygame
        from core.resources import resource_path
        if country in self.physics_world.racers:
            racer = self.physics_world.racers[country]
            if racer.sprite:
                return pygame.transform.smoothscale(racer.sprite, (size, size))
        path = resource_path(f"variants/fulbito/assets/{country}.png")
        try:
            img = pygame.image.load(path).convert_alpha()
            return pygame.transform.smoothscale(img, (size, size))
        except Exception:
            return None

    def _render_country_names(self) -> None:
        import pygame
        from core.config import GAME_AREA_TOP, ACTUAL_WIDTH
        from variants.fulbito.config import FULBITO_COUNTRY_NAMES

        if not self.current_fixture:
            return

        font = pygame.font.SysFont('Arial', 13, bold=True)
        lane_h = self.physics_world.lane_height
        lane_y_offset = self.physics_world.lane_y_offset

        for i, country in enumerate(self.current_fixture):
            name = FULBITO_COUNTRY_NAMES.get(country, country)

            cx = ACTUAL_WIDTH // 2
            cy = GAME_AREA_TOP + lane_y_offset + i * lane_h + lane_h // 2

            name_surf = font.render(name, True, (255, 255, 255))
            pad = 6
            bg_w = name_surf.get_width() + pad * 2
            bg_h = name_surf.get_height() + pad
            bg = pygame.Surface((bg_w, bg_h), pygame.SRCALPHA)
            pygame.draw.rect(bg, (0, 0, 0, 90),
                             (0, 0, bg_w, bg_h), border_radius=8)
            bx = cx - bg_w // 2
            by = cy - bg_h // 2
            self.screen.blit(bg, (bx, by))

            shadow = font.render(name, True, (0, 0, 0))
            tx = cx - name_surf.get_width() // 2
            ty = cy - name_surf.get_height() // 2
            self.screen.blit(shadow, (tx + 1, ty + 1))
            self.screen.blit(name_surf, (tx, ty))

    def _render_fixture_setup(self) -> None:
        import pygame
        from core.config import (
            SCREEN_WIDTH, SCREEN_HEIGHT,
            GAME_AREA_TOP, GAME_AREA_BOTTOM,
            ACTUAL_WIDTH
        )
        from variants.fulbito.config import (
            FULBITO_ALL_COUNTRIES,
            FULBITO_COUNTRY_NAMES,
            FULBITO_RACE_COUNTRY_COUNT,
        )

        game_top    = GAME_AREA_TOP
        game_bottom = SCREEN_HEIGHT - GAME_AREA_BOTTOM
        game_h      = game_bottom - game_top
        cx          = ACTUAL_WIDTH // 2
        cy          = game_top + game_h // 2

        # Fondo negro base
        self.screen.fill((10, 10, 10))

        # Overlay oscuro sobre game area
        overlay = pygame.Surface((ACTUAL_WIDTH, game_h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 230))
        self.screen.blit(overlay, (0, game_top))

        # Título
        font_title = pygame.font.SysFont('Arial', 22, bold=True)
        title = font_title.render("FULBITO — MUNDIAL 2026", True, (255, 255, 180))
        tx = cx - title.get_width() // 2
        self.screen.blit(font_title.render("FULBITO — MUNDIAL 2026", True, (0,0,0)),
                        (tx+2, game_top+22+2))
        self.screen.blit(title, (tx, game_top + 22))

        # Subtítulo
        font_sub = pygame.font.SysFont('Arial', 13)
        sub = font_sub.render("Configura el fixture inicial", True, (180, 180, 180))
        self.screen.blit(sub, (cx - sub.get_width()//2, game_top + 52))

        # Línea separadora
        pygame.draw.line(self.screen,
            (255, 255, 255, 40),
            (30, game_top + 68),
            (ACTUAL_WIDTH - 30, game_top + 68), 1)

        # Slots — 4 filas con pelota del país
        font_slot  = pygame.font.SysFont('Arial', 18, bold=True)
        font_hint  = pygame.font.SysFont('Arial', 12)
        slot_start_y = cy - 90
        slot_spacing = 55

        # Detectar duplicados (solo relevante en fase manual)
        all_selected = [
            FULBITO_ALL_COUNTRIES[self._fixture_country_index.get(i, 0)]
            for i in range(FULBITO_RACE_COUNTRY_COUNT)
        ]
        is_duplicate = [
            all_selected.count(all_selected[i]) > 1
            for i in range(FULBITO_RACE_COUNTRY_COUNT)
        ]

        # Índice visual del slot actualmente girando
        if self._draw_phase == 'animating' and self._draw_slot_idx < FULBITO_RACE_COUNTRY_COUNT:
            spin_progress = min(1.0, self._draw_slot_timer / self._draw_slot_duration)
            spin_speed    = 20.0 * max(0.0, 1.0 - spin_progress ** 0.5)
            spin_vis_idx  = int(self._draw_spin_time * spin_speed) % len(FULBITO_ALL_COUNTRIES)
        else:
            spin_vis_idx  = 0

        for i in range(FULBITO_RACE_COUNTRY_COUNT):
            sy     = slot_start_y + i * slot_spacing
            is_sel = (i == self._fixture_selected_slot)
            is_dup = is_duplicate[i] if self._draw_phase == 'manual' else False

            # ── Slot no alcanzado aún (gris, "???") ──────────────────────
            if self._draw_phase == 'animating' and i > self._draw_slot_idx:
                pending = pygame.Surface((ACTUAL_WIDTH - 60, 42), pygame.SRCALPHA)
                pending.fill((40, 40, 40, 120))
                self.screen.blit(pending, (30, sy - 5))
                pygame.draw.rect(self.screen, (80, 80, 80),
                    (30, sy - 5, ACTUAL_WIDTH - 60, 42), 1, border_radius=4)
                unk = font_slot.render("???", True, (80, 80, 80))
                self.screen.blit(unk, (cx - 76, sy + 1))
                continue

            # ── Slot actualmente girando ──────────────────────────────────
            if self._draw_phase == 'animating' and i == self._draw_slot_idx:
                spin_country = FULBITO_ALL_COUNTRIES[spin_vis_idx]
                spin_name    = FULBITO_COUNTRY_NAMES.get(spin_country, spin_country)
                # Borde blanco pulsante
                pulse_alpha = int(180 + 75 * math.sin(self._draw_spin_time * 10))
                spin_surf = pygame.Surface((ACTUAL_WIDTH - 60, 42), pygame.SRCALPHA)
                spin_surf.fill((255, 255, 255, 18))
                self.screen.blit(spin_surf, (30, sy - 5))
                pygame.draw.rect(self.screen, (255, 255, 255),
                    (30, sy - 5, ACTUAL_WIDTH - 60, 42), 1, border_radius=4)
                # Sprite girando
                sp = self._get_country_sprite(spin_country, 36)
                if sp:
                    self.screen.blit(sp, (cx - 120, sy - 2))
                # Nombre girando
                spin_color = (pulse_alpha, pulse_alpha, pulse_alpha)
                ns = font_slot.render(spin_name, True, spin_color)
                self.screen.blit(font_slot.render(spin_name, True, (0, 0, 0)), (cx - 75, sy + 2))
                self.screen.blit(ns, (cx - 76, sy + 1))
                continue

            # ── Slot fijado / fase manual ─────────────────────────────────
            idx     = self._fixture_country_index.get(i, 0)
            country = FULBITO_ALL_COUNTRIES[idx]
            name    = FULBITO_COUNTRY_NAMES.get(country, country)

            if is_dup:
                border_color = (220, 50, 50)
                fill_color   = (220, 50, 50, 20)
            elif is_sel:
                border_color = (255, 215, 0)
                fill_color   = (255, 215, 0, 25)
            elif self._draw_settled[i] and self._draw_phase == 'animating':
                # Recién fijado — borde verde tenue
                border_color = (80, 200, 80)
                fill_color   = (80, 200, 80, 15)
            else:
                border_color = None
                fill_color   = None

            if border_color:
                sel_surf = pygame.Surface((ACTUAL_WIDTH - 60, 42), pygame.SRCALPHA)
                sel_surf.fill(fill_color)
                self.screen.blit(sel_surf, (30, sy - 5))
                pygame.draw.rect(self.screen, border_color,
                    (30, sy - 5, ACTUAL_WIDTH - 60, 42), 1, border_radius=4)

            sprite = self._get_country_sprite(country, 36)
            if sprite:
                self.screen.blit(sprite, (cx - 120, sy - 2))

            if is_dup:
                color = (220, 80, 80)
            elif is_sel:
                color = (255, 215, 0)
            else:
                color = (220, 220, 220)
            name_surf = font_slot.render(name, True, color)
            shadow    = font_slot.render(name, True, (0, 0, 0))
            self.screen.blit(shadow, (cx - 75, sy + 2))
            self.screen.blit(name_surf, (cx - 76, sy + 1))

        # Hints de navegación
        remaining = max(0, 120 - self.fixture_setup_timer)
        if self._draw_phase == 'animating':
            hints = ["Sorteando fixture..."]
        else:
            hints = [
                "Arriba/Abajo: cambiar slot   Izquierda/Derecha: cambiar pais",
                f"ENTER para confirmar  |  Auto en {remaining:.0f}s",
            ]
        for j, hint in enumerate(hints):
            h = font_hint.render(hint, True, (140, 140, 160))
            self.screen.blit(h, (cx - h.get_width()//2,
                                 game_bottom - 40 + j * 18))

        # Mensaje de error (duplicados)
        if self._fixture_error_msg:
            font_err = pygame.font.SysFont('Arial', 14, bold=True)
            err_surf = font_err.render(self._fixture_error_msg, True, (220, 80, 80))
            ex = cx - err_surf.get_width() // 2
            ey = game_bottom - 60
            self.screen.blit(font_err.render(self._fixture_error_msg, True, (0, 0, 0)),
                            (ex+1, ey+1))
            self.screen.blit(err_surf, (ex, ey))

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def cleanup(self) -> None:
        top_donor = max(
            self.session_top_donor,
            key=self.session_top_donor.get,
            default='',
        ) if self.session_top_donor else ''
        top_country = max(
            self.session_country_diamonds,
            key=self.session_country_diamonds.get,
            default='',
        ) if self.session_country_diamonds else ''
        if self.cloud_manager:
            try:
                asyncio.create_task(
                    self.cloud_manager.sync_session_summary(
                        session_id=self.session_id,
                        variant='fulbito',
                        streamer=self.streamer_name,
                        total_races=self.race_number,
                        total_diamonds=self.session_total_diamonds,
                        unique_viewers=len(self.session_unique_viewers),
                        duration_secs=int(time.time() - self._app_start_time),
                        top_donor=top_donor,
                        top_country=top_country,
                    )
                )
            except Exception as e:
                logger.warning("Session summary sync failed: %s", e)
        super().cleanup()
