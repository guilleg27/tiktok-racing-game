"""Notification Manager — queued follower banners with pop animation."""

import math
from collections import deque
from dataclasses import dataclass

import pygame


_notif_font_cache: dict[tuple, "pygame.font.Font"] = {}


def _get_notif_font(size: int, bold: bool = False) -> "pygame.font.Font":
    key = (size, bold)
    if key not in _notif_font_cache:
        for name in ["Courier New", "Consolas", "Monaco", "monospace"]:
            try:
                _notif_font_cache[key] = pygame.font.SysFont(name, size, bold=bold)
                break
            except Exception:
                continue
        else:
            _notif_font_cache[key] = pygame.font.Font(None, size)
    return _notif_font_cache[key]


@dataclass
class FollowerBanner:
    """A single fixed-position follower announcement banner."""
    username: str
    lifespan: int
    max_lifespan: int
    x: int      # center x
    y: int      # center y
    width: int
    height: int

    def update(self) -> None:
        self.lifespan -= 1

    @property
    def is_alive(self) -> bool:
        return self.lifespan > 0

    def draw(self, surface: pygame.Surface, font: pygame.font.Font) -> None:
        if not self.is_alive:
            return

        life_used = 1.0 - (self.lifespan / self.max_lifespan)
        POP_END  = 0.10
        HOLD_END = 0.85

        if life_used < POP_END:
            t = life_used / POP_END
            scale = 0.4 + 0.6 * (1.0 + 0.35 * math.sin(t * math.pi))
            alpha = 255
        elif life_used < HOLD_END:
            scale = 1.0
            alpha = 255
        else:
            scale = 1.0
            t = (life_used - HOLD_END) / (1.0 - HOLD_END)
            alpha = int(255 * (1.0 - t))

        alpha = max(0, min(255, alpha))
        w = max(1, int(self.width * scale))
        h = max(1, int(self.height * scale))

        radius = 14

        # Glow halo: rounded, semi-transparent neon pink
        glow = pygame.Surface((w + 12, h + 12), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 20, 147, int(alpha * 0.35)),
                         glow.get_rect(), border_radius=radius + 4)
        glow_rect = glow.get_rect(center=(self.x, self.y))
        surface.blit(glow, glow_rect)

        # Main background: deep violet, rounded
        bg = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(bg, (60, 0, 80, int(alpha * 0.95)),
                         bg.get_rect(), border_radius=radius)
        # Neon pink outer border (3px), rounded
        pygame.draw.rect(bg, (255, 20, 147, alpha),
                         bg.get_rect(), 3, border_radius=radius)
        # Cyan inner accent line (1px inset), rounded
        inner = bg.get_rect().inflate(-6, -6)
        pygame.draw.rect(bg, (0, 255, 220, int(alpha * 0.6)),
                         inner, 1, border_radius=radius - 3)
        bg_rect = bg.get_rect(center=(self.x, self.y))
        surface.blit(bg, bg_rect)

        # "NEW FOLLOWER" label — neon cyan, size 13
        label_font = _get_notif_font(13, bold=False)
        label_surf = label_font.render("¡Gracias por unirte!", True, (0, 255, 220))
        _apply_alpha(label_surf, alpha)

        # "@username" — bright white bold, size 17
        name_font = _get_notif_font(17, bold=True)
        name_surf = name_font.render(f"@{self.username}", True, (255, 255, 255))
        _apply_alpha(name_surf, alpha)

        gap = 4
        total_h = label_surf.get_height() + gap + name_surf.get_height()
        label_rect = label_surf.get_rect(centerx=self.x, y=self.y - total_h // 2)
        name_rect  = name_surf.get_rect(centerx=self.x,  y=label_rect.bottom + gap)
        surface.blit(label_surf, label_rect)
        surface.blit(name_surf,  name_rect)


def _apply_alpha(surf: pygame.Surface, alpha: int) -> None:
    """Multiply surface alpha in-place."""
    mask = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    mask.fill((255, 255, 255, alpha))
    surf.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)


class NotificationManager:
    """Queues follower banners and displays them one at a time."""

    def __init__(self, banner_x: int, banner_y: int,
                 banner_w: int, banner_h: int, lifespan: int) -> None:
        self._queue: deque[str] = deque()
        self._active: FollowerBanner | None = None
        self.last_follower: str = ""          # Persistent HUD text
        self._banner_x = banner_x
        self._banner_y = banner_y
        self._banner_w = banner_w
        self._banner_h = banner_h
        self._lifespan = lifespan

    def enqueue(self, username: str) -> None:
        """Add a follower name to the display queue."""
        self._queue.append(username)

    def update(self) -> None:
        """Advance active banner; pop next from queue when idle."""
        if self._active:
            self._active.update()
            if not self._active.is_alive:
                self._active = None
        if not self._active and self._queue:
            username = self._queue.popleft()
            self.last_follower = username
            self._active = FollowerBanner(
                username=username,
                lifespan=self._lifespan,
                max_lifespan=self._lifespan,
                x=self._banner_x,
                y=self._banner_y,
                width=self._banner_w,
                height=self._banner_h,
            )

    def render(self, surface: pygame.Surface) -> None:
        """Draw the active banner (if any)."""
        if self._active:
            self._active.draw(surface, None)  # font arg kept for signature compat, unused
