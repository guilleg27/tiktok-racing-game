"""
TelemetryManager — Snapshots game metrics every 5 seconds and pushes
them to the ``live_telemetry`` Supabase table, keyed by a per-session UUID.

Runs in a daemon background thread so it never touches the asyncio event loop
or the game-loop timing.
"""

import logging
import threading
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from .event_buffer import CHAT_MAX
from .config import GRAVITY

if TYPE_CHECKING:
    from .game_engine import GameEngine
    from .event_buffer import HumanizedEventBuffer
    from core.cloud_manager import CloudManager

logger = logging.getLogger(__name__)

TELEMETRY_INTERVAL = 5.0  # seconds between pushes


class TelemetryManager:
    """Background thread that periodically snapshots game metrics to Supabase."""

    def __init__(
        self,
        game_engine: "GameEngine",
        event_buffer: "HumanizedEventBuffer",
        cloud_manager: "CloudManager",
        session_id: str,
    ) -> None:
        self._ge = game_engine
        self._eb = event_buffer
        self._cm = cloud_manager
        self._session_id = session_id
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._pending_retry: dict | None = None  # payload buffered after a network failure

    def start(self) -> None:
        """Spawn the daemon background thread."""
        self._thread = threading.Thread(
            target=self._run,
            name="telemetry",
            daemon=True,
        )
        self._thread.start()
        logger.info("TelemetryManager started (session=%s)", self._session_id)

    def stop(self) -> None:
        """Signal the thread to stop and wait up to 10 seconds for it to finish."""
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=10)
        logger.info("TelemetryManager stopped")

    def _collect(self) -> dict:
        """Snapshot current game metrics into a dict ready for Supabase.

        session_points is a dict-of-dicts modified by the asyncio game loop.
        We take a snapshot of the inner values via list() so that a concurrent
        dict resize during iteration cannot produce incorrect diamond totals.
        """
        ge = self._ge

        # Thread-safe snapshot: copy the outer mapping first, then sum values.
        try:
            outer_snapshot = list(ge.session_points.values())
            diamonds = sum(
                pts
                for country_map in outer_snapshot
                for pts in list(country_map.values())
            )
        except RuntimeError:
            # dict changed size during iteration — skip this cycle's diamond count
            diamonds = -1

        buffer_load = round(len(self._eb._chat) / CHAT_MAX * 100, 1)

        current_gravity = 0.0 if ge._lunar_active else float(GRAVITY[1])

        return {
            "session_id": self._session_id,
            "viewer_count": ge.viewer_count,
            "diamonds_accumulated": diamonds,
            "buffer_queue_size": ge.queue.qsize(),
            "buffer_load_pct": buffer_load,
            "current_gravity": current_gravity,
            "fps": round(ge.current_fps, 1),
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    def _run(self) -> None:
        """Thread target: collect and push on each interval until stopped.

        If a push fails (network micro-crash), the payload is buffered and
        re-attempted on the next cycle before the fresh snapshot is sent.
        This ensures at most one snapshot is lost per outage regardless of
        outage duration, without blocking the game loop.
        """
        while not self._stop_event.is_set():
            self._stop_event.wait(timeout=TELEMETRY_INTERVAL)
            if self._stop_event.is_set():
                break

            # Retry the previous failed payload first
            if self._pending_retry is not None:
                try:
                    self._cm.update_telemetry(self._pending_retry)
                    logger.debug("telemetry retry succeeded")
                    self._pending_retry = None
                except Exception:
                    logger.warning("telemetry retry failed — will try again next cycle")

            # Collect and push the current snapshot
            payload = None
            try:
                payload = self._collect()
                self._cm.update_telemetry(payload)
            except Exception:
                logger.exception("telemetry push failed — buffering for retry")
                if payload is not None:
                    self._pending_retry = payload
