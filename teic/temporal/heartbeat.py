"""The tick loop -- Layer 0's variable-tempo heartbeat.

Phase 0: fixed tempo only (no arousal-driven modulation yet; that's Phase 2).
`time_source` and `sleep_fn` are dependency-injected rather than calling
`time.monotonic()`/`asyncio.sleep()` directly, so tests can fake elapsed
wall-clock time without waiting on it (see PLAN.md risk #2, empty-clock test).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

TickCallback = Callable[[int, float], Awaitable[None]]
TimeSource = Callable[[], float]
SleepFn = Callable[[float], Awaitable[None]]


class Heartbeat:
    def __init__(
        self,
        tempo_hz: float,
        on_tick: TickCallback,
        time_source: TimeSource = time.monotonic,
        sleep_fn: SleepFn = asyncio.sleep,
    ) -> None:
        self._tempo_hz = tempo_hz
        self._on_tick = on_tick
        self._time_source = time_source
        self._sleep_fn = sleep_fn
        self._tick_index = 0
        self._stop_event = asyncio.Event()

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def tick_index(self) -> int:
        return self._tick_index

    async def run(self) -> None:
        last_ts = self._time_source()
        while not self._stop_event.is_set():
            interval = 1.0 / self._tempo_hz
            await self._sleep_fn(interval)
            if self._stop_event.is_set():
                break
            now = self._time_source()
            dt_real = now - last_ts
            last_ts = now
            await self._on_tick(self._tick_index, dt_real)
            self._tick_index += 1

    async def run_n_ticks(self, n: int) -> None:
        """Test/dev convenience: run exactly n ticks then return."""
        last_ts = self._time_source()
        for _ in range(n):
            interval = 1.0 / self._tempo_hz
            await self._sleep_fn(interval)
            now = self._time_source()
            dt_real = now - last_ts
            last_ts = now
            await self._on_tick(self._tick_index, dt_real)
            self._tick_index += 1
