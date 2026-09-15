"""The tick loop -- Layer 0's variable-tempo heartbeat.

Phase 0: fixed tempo only. Phase 2 adds an optional `tempo_hz_provider`
hook: after each tick, if set, it is consulted and its return value becomes
the tempo used for the *next* interval -- this is the "fed straight into the
heartbeat's next sleep interval" wiring PLAN.md's modulation section
describes. Left `None` by default so Phase 0/1's fixed-tempo gate tests,
which construct `Heartbeat` without it, are unaffected.
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
TempoHzProvider = Callable[[], float]


class Heartbeat:
    def __init__(
        self,
        tempo_hz: float,
        on_tick: TickCallback,
        time_source: TimeSource = time.monotonic,
        sleep_fn: SleepFn = asyncio.sleep,
        tempo_hz_provider: TempoHzProvider | None = None,
    ) -> None:
        self._tempo_hz = tempo_hz
        self._on_tick = on_tick
        self._time_source = time_source
        self._sleep_fn = sleep_fn
        self._tempo_hz_provider = tempo_hz_provider
        self._tick_index = 0
        self._stop_event = asyncio.Event()
        # Phase 9 cp2: TUI pause/resume control. Set == running, clear ==
        # paused. Only `run()` (the TUI's real event loop) consults this --
        # `run_n_ticks()` stays synchronous/unmodified, same rationale as
        # every prior phase's "no gate test's behavior changes" note.
        self._pause_event = asyncio.Event()
        self._pause_event.set()

    def stop(self) -> None:
        self._stop_event.set()

    def pause(self) -> None:
        self._pause_event.clear()

    def resume(self) -> None:
        self._pause_event.set()

    @property
    def paused(self) -> bool:
        return not self._pause_event.is_set()

    @property
    def tick_index(self) -> int:
        return self._tick_index

    async def run(self) -> None:
        last_ts = self._time_source()
        while not self._stop_event.is_set():
            was_paused = self.paused
            await self._pause_event.wait()
            if self._stop_event.is_set():
                break
            if was_paused:
                # Don't let paused wall-clock time leak into dt_real.
                last_ts = self._time_source()
            interval = 1.0 / self._tempo_hz
            await self._sleep_fn(interval)
            if self._stop_event.is_set():
                break
            now = self._time_source()
            dt_real = now - last_ts
            last_ts = now
            await self._on_tick(self._tick_index, dt_real)
            self._tick_index += 1
            if self._tempo_hz_provider is not None:
                self._tempo_hz = self._tempo_hz_provider()

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
            if self._tempo_hz_provider is not None:
                self._tempo_hz = self._tempo_hz_provider()
