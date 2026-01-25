"""Camera system with screen shake effects."""

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ShakeEvent:
    """
    Represents an active screen shake event.
    
    Attributes:
        intensity: Maximum pixel offset for the shake
        duration: Total duration of the shake in seconds
        start_time: When the shake started
        decay: Whether intensity should decay over time (default True)
    """
    intensity: float
    duration: float
    start_time: float = field(default_factory=time.time)
    decay: bool = True


class ScreenShaker:
    """
    Manages screen shake effects for impactful visual feedback.
    
    Supports multiple concurrent shake events that blend together.
    Provides smooth, organic shake motion using Perlin-like noise.
    """
    
    def __init__(self):
        """Initialize the screen shaker."""
        self.active_shakes: list[ShakeEvent] = []
        self.current_offset: tuple[float, float] = (0.0, 0.0)
        self._time_accumulator: float = 0.0
        
        # Vote burst detection (for COMMENT mode)
        self.vote_timestamps: list[float] = []
        self.vote_burst_threshold = 5  # votes needed for burst
        self.vote_burst_window = 0.5  # seconds
        self.last_burst_time = 0.0
        self.burst_cooldown = 1.0  # prevent rapid bursts
    
    def shake(self, intensity: float, duration: float, decay: bool = True) -> None:
        """
        Trigger a new screen shake event.
        
        Args:
            intensity: Maximum pixel offset (1-20 typical range)
            duration: How long the shake lasts in seconds
            decay: Whether to fade out over time (default True)
        """
        self.active_shakes.append(ShakeEvent(
            intensity=intensity,
            duration=duration,
            start_time=time.time(),
            decay=decay
        ))
    
    def micro_shake(self) -> None:
        """Trigger a subtle micro-shake for vote bursts."""
        self.shake(intensity=2.0, duration=0.15, decay=True)
    
    def impact_shake(self) -> None:
        """Trigger a medium shake for attacks (Hielo, Pesa)."""
        self.shake(intensity=8.0, duration=0.3, decay=True)
    
    def big_impact_shake(self) -> None:
        """Trigger a large shake for big gifts or victories."""
        self.shake(intensity=15.0, duration=0.5, decay=True)
    
    def register_vote(self) -> bool:
        """
        Register a vote and check for vote burst.
        
        Returns:
            True if a vote burst was detected and shake triggered
        """
        current_time = time.time()
        self.vote_timestamps.append(current_time)
        
        # Clean old timestamps
        cutoff = current_time - self.vote_burst_window
        self.vote_timestamps = [t for t in self.vote_timestamps if t > cutoff]
        
        # Check for burst
        if len(self.vote_timestamps) >= self.vote_burst_threshold:
            if current_time - self.last_burst_time > self.burst_cooldown:
                self.last_burst_time = current_time
                self.micro_shake()
                self.vote_timestamps.clear()
                return True
        
        return False
    
    def update(self, dt: float) -> tuple[int, int]:
        """
        Update shake state and return current offset.
        
        Args:
            dt: Delta time since last frame
        
        Returns:
            (offset_x, offset_y) tuple to apply to render position
        """
        current_time = time.time()
        self._time_accumulator += dt
        
        # Remove expired shakes
        self.active_shakes = [
            shake for shake in self.active_shakes
            if current_time - shake.start_time < shake.duration
        ]
        
        if not self.active_shakes:
            self.current_offset = (0.0, 0.0)
            return (0, 0)
        
        # Calculate combined shake offset
        total_x = 0.0
        total_y = 0.0
        
        for shake in self.active_shakes:
            elapsed = current_time - shake.start_time
            progress = elapsed / shake.duration
            
            # Calculate intensity with optional decay
            if shake.decay:
                current_intensity = shake.intensity * (1.0 - progress)
            else:
                current_intensity = shake.intensity
            
            # Use sine waves at different frequencies for organic motion
            # This creates a more natural shake than pure random
            freq1 = 25.0  # Fast shake
            freq2 = 15.0  # Medium shake
            freq3 = 8.0   # Slow shake
            
            t = self._time_accumulator
            
            # Combine multiple frequencies for organic feel
            x_offset = (
                math.sin(t * freq1) * 0.5 +
                math.sin(t * freq2 + 0.5) * 0.3 +
                math.sin(t * freq3 + 1.0) * 0.2
            ) * current_intensity
            
            y_offset = (
                math.cos(t * freq1 + 0.3) * 0.5 +
                math.cos(t * freq2 + 0.8) * 0.3 +
                math.cos(t * freq3 + 1.5) * 0.2
            ) * current_intensity
            
            # Add slight randomness for variation
            x_offset += random.uniform(-0.5, 0.5) * current_intensity * 0.2
            y_offset += random.uniform(-0.5, 0.5) * current_intensity * 0.2
            
            total_x += x_offset
            total_y += y_offset
        
        self.current_offset = (total_x, total_y)
        return (int(total_x), int(total_y))
    
    def is_shaking(self) -> bool:
        """Check if any shake is currently active."""
        return len(self.active_shakes) > 0
    
    def clear(self) -> None:
        """Stop all active shakes immediately."""
        self.active_shakes.clear()
        self.current_offset = (0.0, 0.0)
