"""Phase 2: `tempo_hz_provider` feeds the heartbeat's next sleep interval,
independent of any daemon/register logic."""

from __future__ import annotations

import pytest

from teic.temporal.heartbeat import Heartbeat


@pytest.mark.asyncio
async def test_tempo_hz_provider_changes_next_interval() -> None:
    recorded_intervals: list[float] = []
    fake_clock = {"t": 0.0}
    tempo_values = [1.0, 5.0, 0.2, 8.0]
    call_count = {"n": 0}

    def time_source() -> float:
        return fake_clock["t"]

    async def sleep_fn(seconds: float) -> None:
        recorded_intervals.append(seconds)
        fake_clock["t"] += seconds

    async def on_tick(_tick_index: int, _dt_real: float) -> None:
        return None

    def tempo_hz_provider() -> float:
        value = tempo_values[call_count["n"] % len(tempo_values)]
        call_count["n"] += 1
        return value

    heartbeat = Heartbeat(
        tempo_hz=tempo_values[0],
        on_tick=on_tick,
        time_source=time_source,
        sleep_fn=sleep_fn,
        tempo_hz_provider=tempo_hz_provider,
    )
    await heartbeat.run_n_ticks(len(tempo_values))

    # First interval uses the constructor's initial tempo_hz; each
    # subsequent interval reflects the PRIOR tick's provider output.
    expected = [1.0 / tempo_values[0]] + [1.0 / v for v in tempo_values[:-1]]
    assert recorded_intervals == pytest.approx(expected)


@pytest.mark.asyncio
async def test_no_provider_keeps_tempo_fixed() -> None:
    recorded_intervals: list[float] = []
    fake_clock = {"t": 0.0}

    def time_source() -> float:
        return fake_clock["t"]

    async def sleep_fn(seconds: float) -> None:
        recorded_intervals.append(seconds)
        fake_clock["t"] += seconds

    async def on_tick(_tick_index: int, _dt_real: float) -> None:
        return None

    heartbeat = Heartbeat(
        tempo_hz=2.0,
        on_tick=on_tick,
        time_source=time_source,
        sleep_fn=sleep_fn,
    )
    await heartbeat.run_n_ticks(5)
    assert recorded_intervals == pytest.approx([0.5] * 5)
