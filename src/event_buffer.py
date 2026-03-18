"""
HumanizedEventBuffer — Priority-aware jitter buffer between TikTokManager
and GameEngine. Introduces 200–600 ms random delay per event to humanize
timing, while protecting GIFT/FOLLOW/JOIN from being dropped.
"""

import asyncio
import collections
import logging
import random
import time
from dataclasses import dataclass
from typing import Optional

from .events import EventType, GameEvent

logger = logging.getLogger(__name__)

_BYPASS_TYPES = frozenset({EventType.QUIT, EventType.CONNECTION_STATUS})
_HIGH_TYPES   = frozenset({EventType.GIFT, EventType.FOLLOW, EventType.JOIN})
_NORMAL_TYPES = frozenset({EventType.LIKE})
_VIEWER_TYPES = frozenset({EventType.VIEWER_COUNT})
_CHAT_TYPES   = frozenset({EventType.COMMENT, EventType.VOTE})

JITTER_MIN          = 0.15   # seconds — hard lower clamp for Gaussian draw
JITTER_MAX          = 0.70   # seconds — hard upper clamp for Gaussian draw
JITTER_MU           = 0.35   # seconds — Gaussian mean (peak reaction time)
JITTER_SIGMA        = 0.08   # seconds — std-dev (natural human variance)
CHAT_MAX            = 50
VIEWER_MAX          = 5
CHAT_WARN_THRESHOLD = 40


@dataclass
class _Pending:
    event: GameEvent
    release_at: float  # time.perf_counter() value when this may be forwarded


class HumanizedEventBuffer:
    """
    Sits between TikTokManager (_raw_queue) and GameEngine (output_queue).

    Two background asyncio tasks:
      _ingest_loop  — drains raw_queue, routes events into priority sub-structures
      _process_loop — sleeps until release_at deadline, then forwards to output_queue
    """

    def __init__(self, raw_queue: asyncio.Queue, output_queue: asyncio.Queue) -> None:
        self._raw    = raw_queue
        self._output = output_queue

        # Sub-queues (all accessed from same event-loop thread — no locks needed)
        self._high:   list[_Pending]              = []
        self._normal: list[_Pending]              = []
        self._viewer: collections.deque[_Pending] = collections.deque(maxlen=VIEWER_MAX)
        self._chat:   collections.deque[_Pending] = collections.deque(maxlen=CHAT_MAX)

        self._ready = asyncio.Event()  # set by ingest, waited on by process

        self._ingest_task:  Optional[asyncio.Task] = None
        self._process_task: Optional[asyncio.Task] = None

    def start(self) -> None:
        self._ingest_task  = asyncio.create_task(self._ingest_loop(),  name="heb_ingest")
        self._process_task = asyncio.create_task(self._process_loop(), name="heb_process")
        logger.info(
            "HumanizedEventBuffer started (jitter Gauss μ=%.0fms σ=%.0fms clamp [%.0f–%.0f]ms)",
            JITTER_MU * 1000, JITTER_SIGMA * 1000, JITTER_MIN * 1000, JITTER_MAX * 1000,
        )

    async def stop(self) -> None:
        for task in (self._ingest_task, self._process_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        logger.info("HumanizedEventBuffer stopped")

    # ------------------------------------------------------------------
    # Ingest loop
    # ------------------------------------------------------------------

    async def _ingest_loop(self) -> None:
        while True:
            event: GameEvent = await self._raw.get()

            if event.type in _BYPASS_TYPES:
                # Zero-delay: write directly to output queue
                await self._output.put(event)
                continue

            # Gaussian jitter: human reaction times cluster around JITTER_MU with
            # natural variance, unlike the suspiciously flat uniform distribution.
            jitter = max(JITTER_MIN, min(JITTER_MAX, random.gauss(JITTER_MU, JITTER_SIGMA)))
            pending = _Pending(
                event=event,
                release_at=time.perf_counter() + jitter,
            )

            if event.type in _HIGH_TYPES:
                self._high.append(pending)
            elif event.type in _NORMAL_TYPES:
                self._normal.append(pending)
            elif event.type in _VIEWER_TYPES:
                self._viewer.append(pending)  # deque auto-drops oldest at maxlen
            elif event.type in _CHAT_TYPES:
                if len(self._chat) >= CHAT_WARN_THRESHOLD:
                    logger.warning(
                        "[Buffer] CRITICAL: chat buffer at %d/%d (type=%s user=%s)",
                        len(self._chat) + 1, CHAT_MAX,
                        event.type.name, event.username,
                    )
                self._chat.append(pending)    # deque auto-drops oldest at maxlen
            else:
                # Unknown future EventType — treat as HIGH to avoid silent drops
                logger.debug("[Buffer] Unclassified EventType %s → routed as HIGH", event.type.name)
                self._high.append(pending)

            self._ready.set()

    # ------------------------------------------------------------------
    # Process loop
    # ------------------------------------------------------------------

    async def _process_loop(self) -> None:
        while True:
            await self._ready.wait()

            now = time.perf_counter()
            next_release: Optional[float] = None

            # Drain each priority tier in order
            next_release = self._drain_list(self._high,   now, next_release)
            next_release = self._drain_list(self._normal, now, next_release)
            next_release = self._drain_deque(self._viewer, now, next_release)
            next_release = self._drain_deque(self._chat,   now, next_release)

            # Clear signal only when all tiers are empty
            if not (self._high or self._normal or self._viewer or self._chat):
                self._ready.clear()

            # Sleep until next event is due (max 0.1 s to stay responsive)
            if next_release is not None:
                sleep_sec = max(0.0, min(next_release - time.perf_counter(), 0.1))
            else:
                sleep_sec = 0.01
            await asyncio.sleep(sleep_sec)

    def _drain_list(
        self, lst: list[_Pending], now: float, next_release: Optional[float]
    ) -> Optional[float]:
        remaining: list[_Pending] = []
        for item in lst:
            if item.release_at <= now:
                self._output.put_nowait(item.event)
            else:
                remaining.append(item)
                if next_release is None or item.release_at < next_release:
                    next_release = item.release_at
        lst[:] = remaining
        return next_release

    def _drain_deque(
        self, d: collections.deque, now: float, next_release: Optional[float]
    ) -> Optional[float]:
        while d:
            item = d[0]
            if item.release_at <= now:
                d.popleft()
                self._output.put_nowait(item.event)
            else:
                if next_release is None or item.release_at < next_release:
                    next_release = item.release_at
                break
        return next_release
