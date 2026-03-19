"""Physics world management using Pymunk - Flag Race Edition."""

import pymunk
import math
import random
import logging
from dataclasses import dataclass
from typing import Optional, TYPE_CHECKING
import pygame

from .config import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    PHYSICS_STEPS,
    PHYSICS_FIXED_HZ,
    WALL_THICKNESS,
    WALL_FRICTION,
    WALL_ELASTICITY,
    GIFT_COLORS,
    RACE_START_X,
    RACE_FINISH_X,
    FLAG_RADIUS,
    VOL_BGM,
    GAME_AREA_TOP,
    GAME_AREA_BOTTOM,
    RACE_COUNTRIES,
    LANE_HEIGHT,
)

if TYPE_CHECKING:
    from .game_engine import GameEngine

logger = logging.getLogger(__name__)


@dataclass
class FlagRacer:
    """Represents a flag racer in a lane."""
    body: pymunk.Body
    shape: pymunk.Circle
    color: tuple[int, int, int]
    country: str
    lane: int
    sprite: Optional[pygame.Surface] = None
    target_x: float = 0.0  # Target position for smooth interpolation
    y_offset: float = 0.0  # visual-only: applied at draw time, not in physics


class PhysicsWorld:
    """
    Manages the Pymunk physics simulation for Flag Race.
    
    10 lanes with flags that race horizontally when gifts are received.
    """
    
    def __init__(self, asset_manager=None, game_engine: Optional['GameEngine'] = None):
        self.space = pymunk.Space()
        self.space.gravity = (0, 0)  # NO GRAVITY - horizontal race!
        self.space.damping = 1.0     # No damping needed - direct movement
        
        self.asset_manager = asset_manager
        self.game_engine = game_engine
        
        # Flag racers by country
        self.racers: dict[str, FlagRacer] = {}
        
        # Race configuration - Using optimized constants from config
        self.num_lanes = 10  # 10 countries

        # Game area (excluding header and footer)
        self.game_area_top = GAME_AREA_TOP       # 35px below header
        self.game_area_bottom = GAME_AREA_BOTTOM # 65px for legend
        self.game_area_height = SCREEN_HEIGHT - self.game_area_top - self.game_area_bottom

        computed_lane_height = self.game_area_height // self.num_lanes
        self.lane_height = min(computed_lane_height, LANE_HEIGHT)
        num_racers = len(RACE_COUNTRIES)
        total_race_height = self.lane_height * num_racers
        self.lane_y_offset = (self.game_area_height - total_race_height) // 2
        self.start_x = RACE_START_X
        self.finish_line_x = RACE_FINISH_X

        # Countries/teams
        self.countries = list(RACE_COUNTRIES)
        
        # Winner tracking
        self.winner = None
        self.race_finished = False
        self.win_time = 0.0
        self.auto_reset_delay = 5.0
        
        self.final_leaderboard: list[tuple[int, str, float, str]] | None = None

        # Smooth movement configuration (Lerp) - Improved for smoother motion
        self.smoothing_factor = 0.12  # Increased from 0.08 for smoother interpolation

        # Hype Mode: applied as a multiplier at distance-calculation time
        self.hype_speed_multiplier: float = 1.0
        self.rosa_combo_multiplier: float = 1.0   # set by GameEngine

        # Lunar Gravity event
        self.lunar_active:  bool  = False
        self._lunar_phase:  float = 0.0   # advances each frame
        self._lunar_launch: float = 0.0   # fades launch amplitude
        self.LUNAR_AMPLITUDE       = 6.0    # steady bobbing px
        self.LUNAR_LAUNCH_EXTRA    = 18.0   # extra px at activation
        self.LUNAR_LAUNCH_DURATION = 1.5    # seconds to decay launch amplitude
        self.LUNAR_BOB_SPEED       = 2.8    # rad/s for sin wave
        self.LUNAR_ELASTICITY      = 0.85   # shape elasticity during event
        self._normal_elasticity    = 0.1    # saved value to restore

        # Combat system - freeze tracking
        self.frozen_countries: dict[str, float] = {}  # country -> remaining freeze time
        # Countries that finished their freeze this tick (consumed by game_engine each frame)
        self.just_unfrozen: list[str] = []
        
        # Combat effect constants
        self.EFFECT_ROSA_ADVANCE = 5.0      # +5 metros (píxeles)
        self.EFFECT_PESA_SETBACK = 10.0     # -10 metros al líder
        self.EFFECT_HELADO_FREEZE = 5.0     # 5 segundos de congelamiento
        
        self._create_boundaries()
        self._create_racers()
        
        logger.info("🏁 Physics world initialized - FLAG RACE MODE")
        logger.info(f"📍 Start: {self.start_x}px | Finish: {self.finish_line_x}px | Flag radius: {FLAG_RADIUS}px")
    
    def _create_boundaries(self) -> None:
        """Create invisible walls (only left/right, no gravity needed)."""
        static_body = self.space.static_body
        
        walls = [
            # Left wall
            pymunk.Segment(
                static_body,
                (WALL_THICKNESS // 2, 0),
                (WALL_THICKNESS // 2, SCREEN_HEIGHT),
                WALL_THICKNESS // 2
            ),
            # Right wall (far right, beyond finish line)
            pymunk.Segment(
                static_body,
                (SCREEN_WIDTH - WALL_THICKNESS // 2, 0),
                (SCREEN_WIDTH - WALL_THICKNESS // 2, SCREEN_HEIGHT),
                WALL_THICKNESS // 2
            ),
        ]
        
        for wall in walls:
            wall.friction = WALL_FRICTION
            wall.elasticity = WALL_ELASTICITY
            self.space.add(wall)
    
    def _create_racers(self) -> None:
        """Create flag racers in each lane."""
        for i, country in enumerate(self.countries):
            # Calculate lane center Y position (with header offset and vertical centering)
            lane_y = self.game_area_top + self.lane_y_offset + (i * self.lane_height) + (self.lane_height // 2)
            
            # Create dynamic body usando FLAG_RADIUS de config
            mass = 1.0
            moment = pymunk.moment_for_circle(mass, 0, FLAG_RADIUS)
            body = pymunk.Body(mass, moment)
            body.position = (self.start_x, lane_y)
            
            # Create circular shape
            shape = pymunk.Circle(body, FLAG_RADIUS)
            shape.friction = 0.3
            shape.elasticity = 0.1
            
            # Add to space
            self.space.add(body, shape)
            
            # Add groove joint to constrain movement to X-axis only (within race zone)
            groove = pymunk.GrooveJoint(
                self.space.static_body,
                body,
                (self.start_x, lane_y),       # Groove start (safe zone)
                (self.finish_line_x, lane_y), # Groove end (80% width)
                (0, 0)                         # Body anchor
            )
            self.space.add(groove)
            
            # Get color for country
            color = GIFT_COLORS.get(country, GIFT_COLORS["default"])
            
            # Try to load sprite
            sprite = None
            if self.asset_manager:
                sprite = self.asset_manager.get_sprite(country, FLAG_RADIUS * 2)
            
            # Create racer
            racer = FlagRacer(
                body=body,
                shape=shape,
                color=color,
                country=country,
                lane=i,
                sprite=sprite,
                target_x=self.start_x
            )
            
            self.racers[country] = racer
            
            logger.info(f"🏁 Created racer: {country} in lane {i+1}")
    
    def apply_gift_impulse(
        self, country: str, gift_name: str, diamond_count: int = 1
    ) -> tuple[bool, bool]:
        """
        Queue movement for a country's flag based on diamonds received.
        Updates target_x instead of position directly for smooth Lerp movement.
        Movement is always queued even when the country is frozen; the Lerp
        update skips frozen racers so the distance is applied once unfrozen.

        Args:
            country: Country name (must match racer)
            gift_name: Gift name (for logging)
            diamond_count: Gift value (directly affects distance)

        Returns:
            Tuple (success, was_frozen):
              success    — False only when country not found or race finished
              was_frozen — True when the country was frozen at time of the call
                           (movement queued but not immediately visible)
        """
        # Don't apply movement if race is finished
        if self.race_finished:
            return False, False

        if country not in self.racers:
            logger.warning(f"Country '{country}' not found in racers")
            return False, False

        racer = self.racers[country]
        was_frozen = self.is_country_frozen(country)

        # Direct distance scaling: diamonds = pixels to move
        distance_per_diamond = 0.8  # Each diamond = 0.8 pixels forward
        distance = (
            diamond_count
            * distance_per_diamond
            * self.hype_speed_multiplier
            * self.rosa_combo_multiplier
        )

        # Increment target position (NOT actual position)
        racer.target_x += distance

        logger.debug(
            f"🚀 {country} received {gift_name} ({diamond_count}💎) - "
            f"Target: +{distance:.1f}px → {racer.target_x:.0f}"
            + (" [FROZEN — queued]" if was_frozen else "")
        )

        # Note: Winner check happens in update() based on visual position
        return True, was_frozen
    
    def _declare_winner(self, country: str) -> None:
        """Declare a winner and trigger celebration."""
        self.winner = country
        self.race_finished = True
        self.win_time = 0.0

        # Notify game engine about victory for audio effects
        if hasattr(self, 'game_engine') and self.game_engine:
            if hasattr(self.game_engine, 'audio_manager'):
                # Stop final stretch sound and play victory sound
                self.game_engine.audio_manager.stop_final_stretch_sound()
                self.game_engine.audio_manager.play_victory_sound(winner_country=country)

        # Stop all racers and sync target_x to current position
        for r in self.racers.values():
            px = float(r.body.position.x)
            py = float(r.body.position.y)
            if not math.isfinite(px) or not math.isfinite(py):
                lane_y = (r.lane * self.lane_height) + (self.lane_height // 2)
                px = self.start_x
                py = lane_y
            
            r.body.position = (px, py)
            r.body.velocity = (0.0, 0.0)
            r.body.angular_velocity = 0.0
            r.body.force = (0.0, 0.0)
            
            # Sync target to current (stop any pending movement)
            r.target_x = px

        # Save final leaderboard snapshot
        self.final_leaderboard = []
        sorted_racers = sorted(
            self.racers.items(), 
            key=lambda x: x[1].body.position.x if math.isfinite(x[1].body.position.x) else self.start_x, 
            reverse=True
        )
        medals = ["🥇", "🥈", "🥉"] + [""] * (len(sorted_racers) - 3)
        for idx, (cntry, racer) in enumerate(sorted_racers):
            pos = idx + 1
            dist = float(racer.body.position.x) - self.start_x
            if not math.isfinite(dist):
                dist = 0.0
            medal = medals[idx]
            self.final_leaderboard.append((pos, cntry, dist, medal))

        logger.info(f"🏆 WINNER: {country}!")

        # Trigger victory flash effect (white screen flash)
        if self.game_engine:
            # Activate white flash effect
            self.game_engine.victory_flash_alpha = 255.0  # Full white
            self.game_engine.victory_flash_time = 0.0  # Reset timer
            
            # Trigger golden particle explosion at VISUAL position
            racer = self.racers[country]
            pos = (racer.body.position.x, racer.body.position.y)
            self.game_engine.emit_explosion(
                pos=pos,
                color=(255, 215, 0),
                count=100,
                power=2.5,
                diamond_count=10000
            )
    
    def _check_for_winner(self) -> None:
        """Check all racers for crossing the finish line and declare the correct winner."""
        if self.race_finished:
            return

        # Collect racers that crossed
        crossed = [(country, r.body.position.x) for country, r in self.racers.items() if r.body.position.x >= self.finish_line_x]
        if not crossed:
            return

        # Choose the one with max x (the furthest to the right)
        winner_country, _ = max(crossed, key=lambda t: t[1])
        self._declare_winner(winner_country)
    
    def update(self, dt: float) -> None:
        """Update the physics simulation with smooth Lerp movement."""
    
        # Actualizar timers de congelamiento
        self.update_freeze_timers(dt)
    
        # Smooth movement interpolation for all racers
        if not self.race_finished:
            for racer in self.racers.values():
                # Skip frozen countries
                if self.is_country_frozen(racer.country):
                    racer.body.velocity = (0.0, 0.0)
                    continue
                
                current_x = racer.body.position.x
                target_x = racer.target_x
            
                # Only interpolate if there's a difference (reduced threshold for smoother motion)
                if abs(target_x - current_x) > 0.05:  # Reduced from 0.1 for more responsive movement
                    # Smooth Lerp with adaptive factor; scale by dt so motion is identical at 60Hz and 120Hz
                    distance = abs(target_x - current_x)
                    adaptive_factor = min(self.smoothing_factor * (1.0 + distance / 100.0), 0.25)
                    step = adaptive_factor * min(1.0, dt * PHYSICS_FIXED_HZ)
                    new_x = current_x + (target_x - current_x) * step
                    # Update body position (visual position)
                    racer.body.position = (new_x, racer.body.position.y)
            
                # Keep velocity at 0 (we control position directly)
                racer.body.velocity = (0.0, 0.0)
    
        # Lunar gravity: visual Y bobbing (purely cosmetic, does not affect physics constraints)
        if self.lunar_active:
            self._lunar_phase  += self.LUNAR_BOB_SPEED * dt
            self._lunar_launch  = max(0.0, self._lunar_launch - dt)
            launch_amp = (self._lunar_launch / self.LUNAR_LAUNCH_DURATION) * self.LUNAR_LAUNCH_EXTRA
            total_amp  = self.LUNAR_AMPLITUDE + launch_amp
            for racer in self.racers.values():
                phase_offset = racer.lane * 0.5   # each lane bobs out of sync
                racer.y_offset = math.sin(self._lunar_phase + phase_offset) * total_amp

        # Run physics simulation (for constraints, collisions if any)
        step_dt = dt / PHYSICS_STEPS
        for _ in range(PHYSICS_STEPS):
            self.space.step(step_dt)
    
        # Check for winner based on VISUAL position (body.position.x)
        if not self.race_finished:
            self._check_for_winner()
    
        # Auto-reset after winner declared
        if self.race_finished:
            self.win_time += dt
            if self.win_time >= self.auto_reset_delay:
                logger.info(f"⏱️ Auto-resetting race after {self.auto_reset_delay}s")
                self.reset_race()
                if self.game_engine:
                    self.game_engine.on_physics_race_reset()
    
    def get_racers(self) -> dict[str, FlagRacer]:
        """Get all racers for rendering."""
        return self.racers
    
    def get_leader(self) -> Optional[tuple[str, float]]:
        """Get the current leader and their position."""
        if not self.racers:
            return None
        
        leader = max(self.racers.items(), key=lambda x: x[1].body.position.x)
        return leader[0], leader[1].body.position.x
    
    def get_leader_country(self) -> Optional[str]:
        """
        Obtiene el país que va en primer lugar actualmente.
        
        Returns:
            Nombre del país líder o None si no hay racers
        """
        if not self.racers:
            return None
        
        leader = max(
            self.racers.items(),
            key=lambda x: x[1].body.position.x if math.isfinite(x[1].body.position.x) else self.start_x
        )
        return leader[0]
    
    def get_leaderboard(self) -> list[tuple[int, str, float, str]]:
        """Get sorted leaderboard; return final snapshot if race finished."""
        import math
        if self.race_finished and getattr(self, "final_leaderboard", None) is not None:
            return self.final_leaderboard

        sorted_racers = sorted(
            self.racers.items(),
            key=lambda x: x[1].body.position.x if math.isfinite(x[1].body.position.x) else self.start_x,
            reverse=True
        )
        medals = ["🥇", "🥈", "🥉"] + [""] * (len(sorted_racers) - 3)

        leaderboard = []
        for idx, (country, racer) in enumerate(sorted_racers):
            position = idx + 1
            px = float(racer.body.position.x)
            if not math.isfinite(px):
                px = self.start_x
            distance = px - self.start_x
            medal = medals[idx]
            leaderboard.append((position, country, distance, medal))
        return leaderboard
    
    def apply_gift_effect(self, gift_name: str, sender_country: str) -> dict:
        """
        Aplica efectos especiales de combate según el regalo.
        
        Args:
            gift_name: Nombre del regalo (Rosa, Pesa, Helado, etc.)
            sender_country: País del usuario que envió el regalo
            
        Returns:
            dict con información del efecto aplicado:
            {
                'effect': str,  # Tipo de efecto aplicado
                'target': str,  # País afectado
                'value': float, # Valor del efecto
                'message': str  # Mensaje para debug/UI
            }
        """
        if self.race_finished:
            return {'effect': 'none', 'target': '', 'value': 0, 'message': 'Carrera terminada'}
        
        result = {
            'effect': 'none',
            'target': sender_country,
            'value': 0,
            'message': ''
        }
        
        # Normalizar nombre del regalo (case insensitive)
        gift_lower = gift_name.lower()
        
        # 🌹 ROSA: Avanza el país del usuario +5m
        if 'rosa' in gift_lower or 'rose' in gift_lower:
            if sender_country in self.racers:
                self.racers[sender_country].target_x += self.EFFECT_ROSA_ADVANCE
                result = {
                    'effect': 'advance',
                    'target': sender_country,
                    'value': self.EFFECT_ROSA_ADVANCE,
                    'message': f'🌹 {sender_country} avanza +{self.EFFECT_ROSA_ADVANCE}m!'
                }
                logger.info(result['message'])
        
        # 🏋️ PESA/WEIGHTS: Avanza +10m al país del sender
        elif 'pesa' in gift_lower or 'weight' in gift_lower:
            if sender_country in self.racers:
                self.racers[sender_country].target_x += self.EFFECT_PESA_SETBACK
                result = {
                    'effect': 'advance',
                    'target': sender_country,
                    'value': self.EFFECT_PESA_SETBACK,
                    'message': f'🏋️ {sender_country} charges forward +{self.EFFECT_PESA_SETBACK}m!'
                }
                logger.info(result['message'])
        
        # 🍦 HELADO/ICE CREAM: Congela al país en 1er lugar por 3 segundos
        elif 'helado' in gift_lower or 'ice cream' in gift_lower or 'ice' in gift_lower:
            leader = self.get_leader_country()
            if leader and leader in self.racers:
                self.frozen_countries[leader] = self.EFFECT_HELADO_FREEZE
                
                result = {
                    'effect': 'freeze',
                    'target': leader,
                    'value': self.EFFECT_HELADO_FREEZE,
                    'message': f'🍦 {leader} frozen for {self.EFFECT_HELADO_FREEZE}s!'
                }
                logger.info(result['message'])
                print(f"Attacking leader: {leader}")  # Debug console
        
        return result
    
    def is_country_frozen(self, country: str) -> bool:
        """Verifica si un país está congelado."""
        return country in self.frozen_countries and self.frozen_countries[country] > 0
    
    def update_freeze_timers(self, dt: float) -> None:
        """Actualiza los timers de congelamiento. Populates just_unfrozen for game_engine."""
        self.just_unfrozen.clear()
        countries_to_unfreeze = []

        for country, remaining_time in self.frozen_countries.items():
            new_time = remaining_time - dt
            if new_time <= 0:
                countries_to_unfreeze.append(country)
                logger.info(f"Unfreeze: {country}")
            else:
                self.frozen_countries[country] = new_time

        for country in countries_to_unfreeze:
            del self.frozen_countries[country]
            self.just_unfrozen.append(country)
    
    def set_lunar_gravity(
        self,
        active: bool,
        amplitude: float | None = None,
        elasticity: float | None = None,
    ) -> None:
        """Toggle lunar gravity mode: changes shape elasticity and activates visual bobbing."""
        self.lunar_active = active
        if active:
            if amplitude is not None:
                self.LUNAR_AMPLITUDE = amplitude
            if elasticity is not None:
                self.LUNAR_ELASTICITY = elasticity
            self._lunar_phase  = 0.0
            self._lunar_launch = self.LUNAR_LAUNCH_DURATION
            for racer in self.racers.values():
                racer.shape.elasticity = self.LUNAR_ELASTICITY
        else:
            self.LUNAR_AMPLITUDE  = 6.0
            self.LUNAR_ELASTICITY = 0.85
            for racer in self.racers.values():
                racer.shape.elasticity = self._normal_elasticity
                racer.y_offset = 0.0
            self._lunar_phase  = 0.0
            self._lunar_launch = 0.0

    def reset_race(self) -> None:
        """Reset all racers to starting position."""
        for racer in self.racers.values():
            # Usar game_area_top como offset
            start_y = self.game_area_top + (racer.lane * self.lane_height) + (self.lane_height // 2)
            
            # Reset both visual position and target
            racer.body.position = (self.start_x, start_y)
            racer.target_x = self.start_x  # Reset target to start
            
            racer.body.velocity = (0.0, 0.0)
            racer.body.angular_velocity = 0.0
            racer.body.angle = 0.0
            racer.body.force = (0.0, 0.0)
            racer.body.torque = 0.0

        self.winner = None
        self.race_finished = False
        self.win_time = 0.0
        self.final_leaderboard = None
        
        # Clear trail particles when race resets
        if self.game_engine and hasattr(self.game_engine, 'particle_manager'):
            self.game_engine.particle_manager.clear_all_trails()
        
        # Restore BGM volume and ensure it's playing
        if self.game_engine and hasattr(self.game_engine, 'audio_manager'):
            audio_manager = self.game_engine.audio_manager
            if 'bgm' in audio_manager._sound_cache:
                audio_manager._sound_cache['bgm'].set_volume(VOL_BGM)
            if not audio_manager.is_bgm_playing():
                audio_manager.play_bgm()
                logger.info("🎵 BGM restarted after race reset")
    
        logger.info("🔄 Race reset!")

    def _recreate_racer_if_needed(self, racer) -> None:
        """Emergency recreation of a racer if its body becomes corrupted."""
        try:
            # Remove from space
            self.space.remove(racer.body, racer.shape)
            
            # Recreate body
            mass = 1.0
            radius = racer.shape.radius
            moment = pymunk.moment_for_circle(mass, 0, radius)
            racer.body = pymunk.Body(mass, moment)
            
            # Reset position
            start_y = (racer.lane * self.lane_height) + (self.lane_height // 2)
            racer.body.position = (self.start_x, start_y)
            
            # Recreate shape
            racer.shape = pymunk.Circle(racer.body, radius)
            racer.shape.friction = 0.3
            racer.shape.elasticity = 0.1
            
            # Add back to space
            self.space.add(racer.body, racer.shape)
            
            # Recreate groove joint (within race zone)
            groove = pymunk.GrooveJoint(
                self.space.static_body,
                racer.body,
                (self.start_x, start_y),
                (self.finish_line_x, start_y),
                (0, 0)
            )
            self.space.add(groove)
            
            logger.info(f"Recreated racer: {racer.country}")
            
        except Exception as e:
            logger.error(f"Failed to recreate racer {racer.country}: {e}")
    
    def clear(self) -> None:
        """Clear is not needed in race mode, just reset."""
        self.reset_race()
    
    # Legacy compatibility (for older code that might reference balls)
    def get_balls(self):
        """Legacy compatibility - returns empty list."""
        return []
    
    @property
    def balls(self):
        """Legacy compatibility - returns empty list."""
        return []
    
    def _render_flag_emojis(self) -> None:
        """Render flag emojis as sprites for countries without PNG sprites."""
        emoji_map = {
            "Argentina": "🇦🇷", "Brasil": "🇧🇷", "Mexico": "🇲🇽",
            "España": "🇪🇸", "Colombia": "🇨🇴", "Chile": "🇨🇱",
            "Peru": "🇵🇪", "Venezuela": "🇻🇪"
        }
        
        for country, racer in self.racers.items():
            if not racer.sprite:  # Si no hay sprite PNG
                emoji = emoji_map.get(country)
                if emoji:
                    # Renderizar emoji como texto
                    font = pygame.font.Font(None, 36)
                    text_surface = font.render(emoji, True, racer.color)
                    text_rect = text_surface.get_rect(center=racer.body.position)
                    # Dibujar el emoji en la capa correspondiente
                    self.game_engine.screen.blit(text_surface, text_rect)
                    logger.debug(f"Rendered emoji for {country} at {text_rect.topleft}")
    
    def _handle_event(self, event) -> None:
        """Handle a game event (e.g., gift received) - nuevo para eventos de regalo."""
        from .events import EventType
        
        # Solo procesar si la carrera está en curso
        if self.race_finished:
            return
        
        # Procesar según el tipo de evento
        if event.type == EventType.GIFT:
            gift_name = event.content
            country = event.sender  # Suponiendo que el país está en el evento como 'sender'
            
            logger.info(f"🎁 {country} recibió un regalo: {gift_name}")
            
            # Aplicar efecto de combate si aplica
            combat_result = self.apply_gift_effect(
                gift_name=gift_name,
                sender_country=country
            )
            
            if combat_result['effect'] != 'none':
                # Emitir partículas especiales para combate
                if combat_result['effect'] == 'freeze':
                    # Partículas azules para freeze
                    target_racer = self.racers.get(combat_result['target'])
                    if target_racer:
                        self.emit_explosion(
                            pos=(target_racer.body.position.x, target_racer.body.position.y),
                            color=(100, 200, 255),  # Azul hielo
                            count=30,
                            power=1.0
                        )
        elif event.type == pygame.KEYDOWN:
            # Modo de prueba - teclas T, Y, 1, 2, 3 para efectos rápidos
            if event.key == pygame.K_t:  # Test mode
                countries = list(self.physics_world.racers.keys())
                country = random.choice(countries)
                diamonds = random.randint(1, 10)
                
                self.physics_world.apply_gift_impulse(
                    country=country,
                    gift_name="Test Gift",
                    diamond_count=diamonds
                )
                
                logger.info(f"TEST: {country} received {diamonds}💎")

            elif event.key == pygame.K_y:  # Y = Test Big Gift
                countries = list(self.physics_world.racers.keys())
                country = random.choice(countries)
                diamonds = random.randint(25, 50)
                
                self.physics_world.apply_gift_impulse(
                    country=country,
                    gift_name="Big Test Gift",
                    diamond_count=diamonds
                )
                
                logger.info(f"TEST BIG: {country} received {diamonds}💎")

            elif event.key == pygame.K_1:  # 1 = Test Rosa
                countries = list(self.physics_world.racers.keys())  # ← AÑADIR
                country = random.choice(countries)
                self.physics_world.apply_gift_effect("Rosa", country)
                logger.info(f"TEST ROSA: {country}")

            elif event.key == pygame.K_2:  # 2 = Test Pesa
                countries = list(self.physics_world.racers.keys())  # ← AÑADIR
                country = random.choice(countries)
                self.physics_world.apply_gift_effect("Pesa", country)
                logger.info(f"TEST PESA: attacking leader")
                
            elif event.key == pygame.K_3:  # 3 = Test Helado
                countries = list(self.physics_world.racers.keys())  # ← AÑADIR
                country = random.choice(countries)
                self.physics_world.apply_gift_effect("Helado", country)
                logger.info(f"TEST HELADO: freezing leader")