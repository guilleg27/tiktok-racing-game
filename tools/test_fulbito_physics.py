"""
tools/test_fulbito_physics.py
Visual smoke test for FulbitoPhysicsWorld — no engine, no TikTok.

Controls:
  1-4  → impulso a ARG / BRA / MEX / COL
  A    → impulso fuerte a ARG (spam para llegar al final)
  R    → reset race
  ESC  → salir
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Patch core.config with fulbito overrides BEFORE any core/ import uses them.
import core.config as _c
import variants.fulbito.config as _fc

for k, v in vars(_fc).items():
    if not k.startswith("_"):
        setattr(_c, k, v)

import os
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")  # evitar errores de audio sin hardware

import pygame
from variants.fulbito.physics_world import FulbitoPhysicsWorld
from variants.fulbito.config import (
    FULBITO_LANE_DIRECTIONS,
    FULBITO_DEFAULT_FIXTURE,
    FULBITO_START_MARGIN,
    FLAG_RADIUS as FULBITO_FLAG_RADIUS,
)
from core.config import RACE_START_X, RACE_FINISH_X, SCREEN_WIDTH, SCREEN_HEIGHT

# ─────────────────────────────────────────────
# Constantes visuales
# ─────────────────────────────────────────────

COUNTRY_COLORS = {
    "ARG": (116, 172, 223),   # celeste
    "BRA": (0, 175, 80),      # verde
    "MEX": (206, 17, 38),     # rojo
    "COL": (252, 191, 7),     # amarillo
}
DEFAULT_COLOR = (200, 200, 200)
BG_COLOR = (20, 20, 35)

FONT_SIZE_HUD = 16
FONT_SIZE_LABEL = 14

# ─────────────────────────────────────────────
# Init
# ─────────────────────────────────────────────

pygame.init()
screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("Fulbito Physics — Test Visual")
clock = pygame.time.Clock()

font_hud = pygame.font.SysFont("monospace", FONT_SIZE_HUD)
font_label = pygame.font.SysFont("monospace", FONT_SIZE_LABEL)

pw = FulbitoPhysicsWorld()

# ─────────────────────────────────────────────
# Helpers de render
# ─────────────────────────────────────────────

def draw_text(surface, text, x, y, color=(220, 220, 220), font=None):
    if font is None:
        font = font_hud
    surf = font.render(text, True, color)
    surface.blit(surf, (x, y))


def render(screen):
    screen.fill(BG_COLOR)

    # Líneas de referencia verticales (full height)
    h = SCREEN_HEIGHT
    pygame.draw.line(screen, (180, 60, 60),   (RACE_FINISH_X, 0), (RACE_FINISH_X, h), 1)  # meta →
    pygame.draw.line(screen, (60, 100, 200),  (RACE_START_X, 0),  (RACE_START_X, h), 1)   # meta ←
    start_right = RACE_START_X + FULBITO_START_MARGIN
    start_left  = RACE_FINISH_X - FULBITO_START_MARGIN
    pygame.draw.line(screen, (80, 80, 80), (start_right, 0), (start_right, h), 1)          # salida →
    pygame.draw.line(screen, (80, 80, 80), (start_left, 0),  (start_left, h), 1)           # salida ←

    # Etiquetas de líneas
    draw_text(screen, "START→", start_right + 2, 4, (100, 100, 100), font_label)
    draw_text(screen, "←START", start_left - 52, 4, (100, 100, 100), font_label)
    draw_text(screen, "META→", RACE_FINISH_X + 2, 14, (200, 80, 80), font_label)
    draw_text(screen, "←META", RACE_START_X - 44, 14, (80, 120, 220), font_label)

    # Racers
    for country, racer in pw.racers.items():
        pos = (int(racer.body.position.x), int(racer.body.position.y))
        color = COUNTRY_COLORS.get(country, DEFAULT_COLOR)

        # Carril: sombreado suave
        lane_top = int(racer.body.position.y - pw.lane_height // 2)
        lane_rect = pygame.Rect(0, lane_top, SCREEN_WIDTH, pw.lane_height)
        lane_surf = pygame.Surface((SCREEN_WIDTH, pw.lane_height), pygame.SRCALPHA)
        lane_surf.fill((*color, 15))
        screen.blit(lane_surf, (0, lane_top))

        # Barra de progreso
        progress = pw.get_progress(country)
        bar_w = int(SCREEN_WIDTH * progress)
        bar_h = 4
        bar_y = lane_top + pw.lane_height - bar_h
        pygame.draw.rect(screen, (*color, 180), (0, bar_y, bar_w, bar_h))

        # Círculo del racer
        pygame.draw.circle(screen, color, pos, FULBITO_FLAG_RADIUS)
        pygame.draw.circle(screen, (255, 255, 255), pos, FULBITO_FLAG_RADIUS, 2)

        # Nombre del país
        draw_text(screen, country, pos[0] - 14, pos[1] - 8, (255, 255, 255), font_label)

        # Flecha de dirección a la izquierda
        going_right = FULBITO_LANE_DIRECTIONS.get(racer.lane, True)
        arrow = "→" if going_right else "←"
        arrow_color = (180, 60, 60) if going_right else (60, 100, 200)
        draw_text(screen, arrow, 4, int(racer.body.position.y) - 7, arrow_color, font_label)

    # ── HUD superior ──────────────────────────────
    hud_y = 6
    leader, leader_prog = pw.get_leader()
    draw_text(screen, f"Lider: {leader} ({leader_prog:.0%})", 4, hud_y)
    hud_y += 18

    if pw.race_finished:
        draw_text(screen, f"GANADOR: {pw.winner}", 4, hud_y, (255, 215, 0))
        hud_y += 18

    progress_parts = " | ".join(
        f"{c}: {pw.get_progress(c):.0%}" for c in FULBITO_DEFAULT_FIXTURE
    )
    draw_text(screen, progress_parts, 4, hud_y, (180, 180, 180), font_label)

    # ── Ayuda de controles (parte inferior) ──────
    controls = "[1-4] impulso  [A] spam ARG  [R] reset  [ESC] salir"
    draw_text(screen, controls, 4, SCREEN_HEIGHT - 20, (100, 100, 100), font_label)

    pygame.display.flip()


# ─────────────────────────────────────────────
# Game loop
# ─────────────────────────────────────────────

IMPULSE_DIAMONDS = 5
IMPULSE_SPAM_DIAMONDS = 15  # tecla A

running = True
while running:
    dt = clock.tick(30) / 1000.0

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False

            elif event.key == pygame.K_1:
                pw.apply_gift_impulse("ARG", "test", IMPULSE_DIAMONDS)
            elif event.key == pygame.K_2:
                pw.apply_gift_impulse("BRA", "test", IMPULSE_DIAMONDS)
            elif event.key == pygame.K_3:
                pw.apply_gift_impulse("MEX", "test", IMPULSE_DIAMONDS)
            elif event.key == pygame.K_4:
                pw.apply_gift_impulse("COL", "test", IMPULSE_DIAMONDS)

            elif event.key == pygame.K_a:
                pw.apply_gift_impulse("ARG", "spam", IMPULSE_SPAM_DIAMONDS)

            elif event.key == pygame.K_r:
                pw.reset_race()

    # Teclas mantenidas para spam continuo
    keys = pygame.key.get_pressed()
    if keys[pygame.K_a]:
        pw.apply_gift_impulse("ARG", "spam_held", 2)

    pw.update(dt)
    render(screen)

pygame.quit()
