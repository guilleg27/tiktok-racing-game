"""HypeManager - Tracks engagement rate and manages Hype Mode state machine."""

import time
import logging
from collections import deque

logger = logging.getLogger(__name__)


class HypeManager:
    """
    Tracks engagement rate (events per minute) and manages Hype Mode.

    State machine:
        IDLE     → ACTIVE   when cpm >= threshold
        ACTIVE   → COOLDOWN when cpm drops below threshold (after hype peaks)
        COOLDOWN → IDLE     after cooldown_duration seconds
    """

    def __init__(self, threshold_cpm: float = 30, cooldown_duration: float = 120.0):
        """
        Args:
            threshold_cpm: Events-per-minute to trigger hype mode.
            cooldown_duration: Seconds to wait in COOLDOWN before returning to IDLE.
        """
        self.threshold_cpm = threshold_cpm
        self.cooldown_duration = cooldown_duration

        # Rolling window of event timestamps (max age = 60 s)
        self._window_seconds = 60.0
        self._timestamps: deque[float] = deque()

        # State machine
        self._state = 'IDLE'  # 'IDLE' | 'ACTIVE' | 'COOLDOWN'
        self._cooldown_elapsed = 0.0

        # Peak CPM tracking (for display during cooldown)
        self.peak_cpm: float = 0.0

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def register_event(self) -> None:
        """Record a single engagement event (O(1))."""
        self._timestamps.append(time.monotonic())

    def update(self, dt: float) -> None:
        """
        Prune stale timestamps and advance the state machine.

        Args:
            dt: Elapsed seconds since last call.
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds
        while self._timestamps and self._timestamps[0] < cutoff:
            self._timestamps.popleft()

        cpm = self.get_cpm()
        if cpm > self.peak_cpm:
            self.peak_cpm = cpm

        if self._state == 'IDLE':
            if cpm >= self.threshold_cpm:
                self._state = 'ACTIVE'
                logger.info(f"🔥 HYPE MODE activated! CPM={cpm:.0f}")

        elif self._state == 'ACTIVE':
            if cpm < self.threshold_cpm:
                self._state = 'COOLDOWN'
                self._cooldown_elapsed = 0.0
                logger.info(f"🌙 Hype Mode ended. Peak CPM={self.peak_cpm:.0f} → COOLDOWN")

        elif self._state == 'COOLDOWN':
            self._cooldown_elapsed += dt
            if self._cooldown_elapsed >= self.cooldown_duration:
                self._state = 'IDLE'
                self._cooldown_elapsed = 0.0
                self.peak_cpm = 0.0
                logger.info("😴 Hype Mode cooldown finished → IDLE")

    def get_cpm(self) -> float:
        """Return current events-per-minute (bounded 60 s window)."""
        return float(len(self._timestamps))

    @property
    def is_hype_active(self) -> bool:
        """True while hype is in ACTIVE state."""
        return self._state == 'ACTIVE'

    @property
    def is_cooldown(self) -> bool:
        """True while hype is in COOLDOWN state."""
        return self._state == 'COOLDOWN'

    def reset(self) -> None:
        """Hard-reset to IDLE (call on full race reset if desired)."""
        self._timestamps.clear()
        self._state = 'IDLE'
        self._cooldown_elapsed = 0.0
        self.peak_cpm = 0.0
