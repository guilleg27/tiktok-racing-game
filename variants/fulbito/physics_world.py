"""
FulbitoPhysicsWorld — subclass of PhysicsWorld for the Fulbito variant.

Alternating lane directions: lanes 0, 2 go left→right (→); lanes 1, 3 go right→left (←).
Progress is measured from each racer's respective starting wall toward the opposite wall.
"""

import logging
import pymunk

from core.physics_world import PhysicsWorld, FlagRacer
from core.config import (
    SCREEN_WIDTH,
    GIFT_COLORS,
)

# Extremos físicos del campo — coinciden con la posición visual de los arcos
_TRACK_LEFT  = 8
_TRACK_RIGHT = SCREEN_WIDTH - 8  # 452px
from variants.fulbito.config import (
    FULBITO_LANE_DIRECTIONS,
    FULBITO_START_MARGIN,
    FULBITO_WIN_THRESHOLD,
    FULBITO_SUDDEN_DEATH,
    FULBITO_DEFAULT_FIXTURE,
    FLAG_RADIUS as FULBITO_FLAG_RADIUS,
)

logger = logging.getLogger(__name__)


class FulbitoPhysicsWorld(PhysicsWorld):
    """Physics world for the Fulbito variant.

    Extends PhysicsWorld with alternating lane directions so that adjacent
    racers travel toward each other, creating a head-on competition feel.
    """

    def __init__(self, countries=None, asset_manager=None, game_engine=None):
        # Store before super().__init__() so our _create_racers() override can use it.
        # super().__init__() will set self.countries = list(RACE_COUNTRIES) and then
        # call self._create_racers() — Python dispatches to our override, which
        # reassigns self.countries from _fulbito_countries before building bodies.
        self._fulbito_countries = list(countries or FULBITO_DEFAULT_FIXTURE)
        self._rotation_angles: dict[str, float] = {}
        super().__init__(asset_manager=asset_manager, game_engine=game_engine)
        self.hype_speed_multiplier = 1.0
        self.rosa_combo_multiplier = 1.0

        # Sobreescribir posiciones de inicio/fin para usar los extremos reales
        self.start_x = _TRACK_LEFT + 12          # ≈ 20px
        self.finish_line_x = _TRACK_RIGHT - 12   # ≈ 440px

        # Reposicionar racers al nuevo start_x (super() los colocó con FULBITO_START_MARGIN)
        for i, (_, racer) in enumerate(self.racers.items()):
            going_right = self._get_lane_direction(i)
            new_x = float(self.start_x if going_right else self.finish_line_x)
            racer.body.position = (new_x, racer.body.position.y)
            racer.body.velocity = (0, 0)
            racer.target_x = new_x

    # ─────────────────────────────────────────────
    # Private helpers
    # ─────────────────────────────────────────────

    def _get_lane_direction(self, lane: int) -> bool:
        """Return True if lane travels left→right, False if right→left."""
        return FULBITO_LANE_DIRECTIONS.get(lane, True)

    def _get_initial_x(self, lane: int) -> float:
        """Return the starting X position for a given lane."""
        if self._get_lane_direction(lane):
            return float(_TRACK_LEFT + FULBITO_START_MARGIN)
        else:
            return float(_TRACK_RIGHT - FULBITO_START_MARGIN)

    # ─────────────────────────────────────────────
    # Overrides
    # ─────────────────────────────────────────────

    def _create_racers(self) -> None:
        """Create flag racers with direction-aware starting positions."""
        # Apply fulbito country list (super().__init__ set self.countries = RACE_COUNTRIES).
        self.countries = self._fulbito_countries
        self.num_lanes = len(self.countries)

        # Recompute lane layout for the actual number of racers (4), not the base's 10/15.
        num_racers = len(self.countries)
        # Lee LANE_HEIGHT en runtime (game_engine lo sobreescribe a 85 antes de instanciar)
        import core.config as _cc
        fulbito_lane_height = getattr(_cc, 'LANE_HEIGHT', 85)
        computed_lane_height = self.game_area_height // max(num_racers, 1)
        self.lane_height = min(computed_lane_height, fulbito_lane_height)
        total_race_height = self.lane_height * num_racers
        self.lane_y_offset = (self.game_area_height - total_race_height) // 2

        for i, country in enumerate(self.countries):
            lane_y = (
                self.game_area_top
                + self.lane_y_offset
                + (i * self.lane_height)
                + (self.lane_height // 2)
            )
            initial_x = self._get_initial_x(i)

            mass = 1.0
            moment = pymunk.moment_for_circle(mass, 0, FULBITO_FLAG_RADIUS)
            body = pymunk.Body(mass, moment)
            body.position = (initial_x, lane_y)
            shape = pymunk.Circle(body, FULBITO_FLAG_RADIUS)

            shape.friction = 0.3
            shape.elasticity = 0.1
            self.space.add(body, shape)

            # Groove joint covers the full track so racers can travel in either direction.
            groove = pymunk.GrooveJoint(
                self.space.static_body,
                body,
                (_TRACK_LEFT, lane_y),
                (_TRACK_RIGHT, lane_y),
                (0, 0),
            )
            self.space.add(groove)

            color = GIFT_COLORS.get(country, GIFT_COLORS["default"])

            racer = FlagRacer(
                body=body,
                shape=shape,
                color=color,
                country=country,
                lane=i,
                sprite=None,
                target_x=initial_x,
                draw_radius=FULBITO_FLAG_RADIUS,
            )
            self.racers[country] = racer
            self._rotation_angles[country] = 0.0

            target_size = 54
            if self.asset_manager:
                sprite = self.asset_manager.get_sprite_for_racer(country, target_size)
                if sprite:
                    racer.sprite = sprite
                    racer.draw_radius = target_size // 2
                else:
                    logger.warning(f"No sprite found for {country}")

            logger.info(
                f"Fulbito racer: {country} lane={i} "
                f"dir={'→' if self._get_lane_direction(i) else '←'} x={initial_x:.0f}"
            )

    def update(self, dt: float) -> None:
        prev_x = {
            country: float(racer.body.position.x)
            for country, racer in self.racers.items()
        }

        super().update(dt)

        # Override the core's percentage-Lerp with constant-speed movement.
        # Revert positions to prev_x first, then apply constant-speed movement.
        from variants.fulbito.config import FULBITO_BALL_SPEED_PPS
        max_move = FULBITO_BALL_SPEED_PPS * dt
        for country, racer in self.racers.items():
            # Revert to position at start of frame
            racer.body.position = (prev_x.get(country, racer.body.position.x), racer.body.position.y)
        for country, racer in self.racers.items():
            if self.is_country_frozen(country):
                continue
            current_x = float(racer.body.position.x)  # now at prev_x position
            dist = racer.target_x - current_x
            if abs(dist) < 0.05:
                continue
            move = max(-max_move, min(max_move, dist))
            new_pos = current_x + move
            if self._get_lane_direction(racer.lane):
                new_pos = min(new_pos, _TRACK_RIGHT)
            else:
                new_pos = max(new_pos, _TRACK_LEFT)
            racer.body.position = (new_pos, racer.body.position.y)
            racer.body.velocity = (0.0, 0.0)

        PIXELS_PER_DEGREE = 0.8
        IDLE_DEG_PER_SEC = 25.0
        for i, (country, racer) in enumerate(self.racers.items()):
            new_x = float(racer.body.position.x)
            delta = new_x - prev_x.get(country, new_x)
            if abs(delta) > 0.01:
                rotation_delta = delta * PIXELS_PER_DEGREE
            else:
                direction = 1 if self._get_lane_direction(i) else -1
                rotation_delta = direction * IDLE_DEG_PER_SEC * dt
            self._rotation_angles[country] = (
                self._rotation_angles.get(country, 0.0) + rotation_delta
            ) % 360

    def apply_gift_impulse(
        self, country: str, gift_name: str, diamond_count: int = 1
    ) -> tuple[bool, bool]:
        """Queue directional movement for a country's flag based on diamonds received."""
        if self.race_finished:
            return False, False

        if country not in self.racers:
            logger.warning(f"Country '{country}' not found in racers")
            return False, False

        racer = self.racers[country]
        was_frozen = self.is_country_frozen(country)

        from variants.fulbito.config import (
            FULBITO_DISTANCE_PER_DIAMOND,
            FULBITO_MIN_GIFT_DISTANCE,
        )
        distance = max(
            FULBITO_MIN_GIFT_DISTANCE,
            diamond_count * FULBITO_DISTANCE_PER_DIAMOND
        )

        going_right = self._get_lane_direction(racer.lane)
        delta = distance if going_right else -distance
        racer.target_x += delta

        if going_right:
            racer.target_x = min(racer.target_x, _TRACK_RIGHT)
        else:
            racer.target_x = max(racer.target_x, _TRACK_LEFT)

        logger.debug(
            f"{country} received {gift_name} ({diamond_count}💎) "
            f"delta={delta:+.1f}px → target={racer.target_x:.0f}"
            + (" [FROZEN — queued]" if was_frozen else "")
        )
        return True, was_frozen

    def get_progress(self, country: str) -> float:
        """Return normalized progress (0.0–1.0) for a country toward its goal."""
        if country not in self.racers:
            return 0.0
        racer = self.racers[country]
        pos_x = racer.body.position.x
        if self._get_lane_direction(racer.lane):
            start = _TRACK_LEFT + FULBITO_START_MARGIN
            finish = _TRACK_RIGHT
            progress = (pos_x - start) / (finish - start)
        else:
            start = _TRACK_RIGHT - FULBITO_START_MARGIN
            finish = _TRACK_LEFT
            progress = (start - pos_x) / (start - finish)
        return max(0.0, min(1.0, progress))

    def get_leader(self) -> tuple[str, float]:
        """Return (country, progress) for the racer currently closest to their goal."""
        if not self.racers:
            return ("", 0.0)
        best = max(self.racers, key=lambda c: self.get_progress(c))
        return (best, self.get_progress(best))

    def _check_for_winner(self) -> None:
        """Declare winner when any racer reaches FULBITO_WIN_THRESHOLD progress."""
        if self.race_finished:
            return
        for country in list(self.racers):
            if self.get_progress(country) >= FULBITO_WIN_THRESHOLD:
                self._declare_winner(country)
                if FULBITO_SUDDEN_DEATH:
                    return

    def reset_race(self) -> None:
        """Reset all racers to their direction-aware starting positions."""
        super().reset_race()
        # super() resets every racer to self.start_x (= RACE_START_X), which is
        # wrong for right→left lanes. Re-apply the correct initial_x for each lane.
        for racer in self.racers.values():
            initial_x = self._get_initial_x(racer.lane)
            lane_y = racer.body.position.y
            racer.body.position = (initial_x, lane_y)
            racer.target_x = initial_x
            racer.body.velocity = (0.0, 0.0)
