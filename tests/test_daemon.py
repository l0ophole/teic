"""Phase 3 daemon wiring: `prediction_error` becomes a real, learned signal.

Drives `TeicDaemon._on_tick` through the same injected `time_source`/
`sleep_fn` DI pattern used by `tests/test_gates/test_phase1.py` and
`test_phase2.py`. Most ticks use `dt_real` equal to that tick's own nominal
`1 / tempo_hz`, but tick 1 is deliberately jittered to 3x nominal.

This is a stronger check than "stays near 0.0 throughout" would be: under
Phase 0-2's flat `0.0` placeholder, prediction_error is always 0.0 no
matter what dt_real does, so a test that only asserted near-zero values
could not tell a real ForwardModel-driven signal apart from that
placeholder. Instead this test asserts the jittered tick produces a large,
real error (proving the signal is genuinely computed from ForwardModel/
ProtentionBuffer, not hardcoded), and that later ticks -- back on nominal
dt_real -- decay close to 0.0 again (proving the EWMA forward model
actually adapts/re-learns, per `tick >= 2` from the plan brief, generalized
here to "after the model has had time to recover from the jitter").
"""

from __future__ import annotations

import time

import pytest

from teic.daemon import TeicDaemon
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat

N_TICKS = 16
JITTER_TICK_INDEX = 1
JITTER_MULTIPLE = 3.0


@pytest.mark.asyncio
async def test_prediction_error_reacts_to_jitter_then_settles(tmp_settings: Settings) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    fake_clock = {"t": 0.0}
    tick_counter = {"n": 0}

    def fake_time_source() -> float:
        return fake_clock["t"]

    async def fake_sleep(_seconds: float) -> None:
        # Advance by exactly this tick's own nominal period (whatever tempo
        # is currently in effect for the daemon), except for one
        # deliberately jittered tick -- so dt_real matches the ForwardModel's
        # unbiased prediction everywhere except that one induced spike.
        nominal_dt = 1.0 / daemon._current_tempo_hz
        if tick_counter["n"] == JITTER_TICK_INDEX:
            fake_clock["t"] += nominal_dt * JITTER_MULTIPLE
        else:
            fake_clock["t"] += nominal_dt
        tick_counter["n"] += 1

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=fake_time_source,
        sleep_fn=fake_sleep,
    )
    await fake_heartbeat.run_n_ticks(N_TICKS)

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT t.tick_index, rs.raw_value FROM register_sample rs "
        "JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = 'prediction_error' "
        "ORDER BY t.tick_index",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    assert len(rows) == N_TICKS
    by_tick = dict(rows)

    # Tick 0: no prior prediction exists yet, so this is trivially 0.0.
    assert by_tick[0] == 0.0

    # Tick 1: resolves the prediction made at tick 0 against the deliberate
    # 3x jitter -- a real, non-trivial error. A hardcoded 0.0 placeholder
    # (Phase 0-2 behavior) would fail this.
    assert by_tick[JITTER_TICK_INDEX] > 1.0, (
        f"expected a large real prediction_error after the induced jitter, "
        f"got {by_tick[JITTER_TICK_INDEX]}"
    )

    # By the last few ticks, dt_real has been back on-nominal long enough
    # for the ForwardModel's EWMA multiplier to re-adapt, so the error
    # should have decayed back down close to 0.0.
    for tick_index in range(N_TICKS - 3, N_TICKS):
        assert by_tick[tick_index] < 0.05, (
            f"tick {tick_index}: expected prediction_error to have settled "
            f"back near 0.0 well after the jitter, got {by_tick[tick_index]}"
        )

    await daemon.stop()


@pytest.mark.asyncio
async def test_run_n_ticks_writes_memory_and_returns_promptly(tmp_settings: Settings) -> None:
    """Phase 4: one tau1_working memory_record row per tick, and
    run_n_ticks() (used by every gate test) completes promptly -- it does
    not start/wait on the background consolidation loop, which only run()
    does. Uses the same injected fake time_source/sleep_fn DI pattern as
    the jitter test above so this doesn't burn real wall-clock seconds
    waiting on the heartbeat's own tick interval."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    fake_clock = {"t": 0.0}

    async def fake_sleep(seconds: float) -> None:
        fake_clock["t"] += seconds

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=lambda: fake_clock["t"],
        sleep_fn=fake_sleep,
    )

    n = 5
    start = time.monotonic()
    await fake_heartbeat.run_n_ticks(n)
    elapsed = time.monotonic() - start

    from teic.memory.consolidation import IDLE_THRESHOLD_S

    assert elapsed < IDLE_THRESHOLD_S

    conn = daemon.conn
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM memory_record WHERE session_id = ? AND timescale = 'tau1_working'",
        (daemon.session_id,),
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row[0] == n

    await daemon.stop()
