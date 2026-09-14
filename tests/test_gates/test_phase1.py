"""Phase 1 gate: telemetry -> interoceptive vector, wired into the daemon.

Drives the daemon through a synthetic-load run with a deterministic,
non-constant sequence of `dt_real` values (via the same injected
`time_source`/`sleep_fn` DI pattern `test_phase0.py` uses for its fake
clock) and checks the `register_sample` rows it produces carry real,
moving sensed/inferred values rather than Phase 0's flat placeholders.

Per the phase's gate wording, this makes no assertion about LLM calls,
prompt content, or generated text -- that's out of scope until later
phases wire an actual model call path.
"""

from __future__ import annotations

import pytest

from teic.daemon import TeicDaemon
from teic.models.registers import REGISTER_CHANNELS
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat

N_TICKS = 30

# Deterministic, non-constant jitter sequence: alternates a "fast" and a
# "slow" simulated inter-tick interval so latency_strain (computed from
# how far dt_real diverges from the 1/tempo_hz expectation) actually
# moves tick to tick instead of staying pinned at one value. Fixed, not
# `random` -- reproducible by construction, no seed needed.
_JITTER_SECONDS = [0.05, 0.25]


@pytest.mark.asyncio
async def test_phase1_register_samples_carry_real_moving_values(
    tmp_settings: Settings,
) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    # Drive daemon._on_tick through a separate Heartbeat wired to an
    # injected fake clock (same DI pattern as test_phase0.py's synthetic
    # empty-clock test), rather than the daemon's own default-clocked
    # heartbeat, so the sequence of dt_real values reaching _on_tick is
    # exact, instant, and non-constant.
    fake_clock = {"t": 0.0}
    tick_counter = {"n": 0}

    def fake_time_source() -> float:
        return fake_clock["t"]

    async def fake_sleep(_seconds: float) -> None:
        # Advance the clock by the next jitter interval, not by whatever
        # interval the heartbeat computed from tempo_hz -- this is what
        # actually makes dt_real vary tick to tick.
        idx = tick_counter["n"] % len(_JITTER_SECONDS)
        fake_clock["t"] += _JITTER_SECONDS[idx]
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
        "SELECT COUNT(*) FROM register_sample rs JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ?",
        (daemon.session_id,),
    )
    (register_row_count,) = await cursor.fetchone()  # type: ignore[misc]
    assert register_row_count == N_TICKS * len(REGISTER_CHANNELS)

    cursor = await conn.execute(
        "SELECT DISTINCT rs.inferred_value FROM register_sample rs "
        "JOIN tick t ON rs.tick_id = t.tick_id "
        "WHERE t.session_id = ? AND rs.channel = 'latency_strain'",
        (daemon.session_id,),
    )
    rows = await cursor.fetchall()
    distinct_inferred_values = {row[0] for row in rows}
    assert len(distinct_inferred_values) > 1, (
        "latency_strain inferred_value should move across ticks under "
        "jittered dt_real, not stay flat like Phase 0's placeholder"
    )

    # `inferred_var != {0.0}` alone is no longer a useful discriminator: since
    # inference.py's `INITIAL_VARIANCE`/`PROCESS_NOISE` fix, EVERY channel's
    # variance settles at a nonzero floor, even a channel whose raw input
    # never changes (e.g. `budget_reserve`, always 1.0) -- that floor works
    # out to (1 - ALPHA) * (floor + PROCESS_NOISE) = floor, i.e.
    # floor = PROCESS_NOISE * (1 - ALPHA) / ALPHA ~= 0.0233 with this
    # module's current constants. So a dead/placeholder channel would pass
    # a bare "!= {0.0}" check too, which is exactly the failure mode this
    # gate exists to catch.
    #
    # What actually distinguishes "inference is live on real data" from
    # "the filter is just idling at its constant-input floor" is that a
    # channel whose raw input genuinely varies tick to tick should settle
    # at a HIGHER final variance than that floor, because the EWMA's
    # `ALPHA * (raw - prior_mean) ** 2` residual term keeps injecting real
    # variance on top of PROCESS_NOISE. `latency_strain` moves under the
    # jittered `dt_real` above; `budget_reserve`'s raw sample is hardcoded
    # to a constant 1.0 (see `teic/embodiment/sensors.py`), so it's the
    # exact "constant-input floor" reference case. If inference silently
    # stopped running on `latency_strain` (e.g. reverted to a placeholder,
    # or fed a constant), its final variance would collapse to the same
    # floor as `budget_reserve` and this comparison would fail.
    async def _final_inferred_var(channel: str) -> float:
        cur = await conn.execute(
            "SELECT rs.inferred_var FROM register_sample rs "
            "JOIN tick t ON rs.tick_id = t.tick_id "
            "WHERE t.session_id = ? AND rs.channel = ? "
            "ORDER BY t.tick_index DESC LIMIT 1",
            (daemon.session_id, channel),
        )
        (value,) = await cur.fetchone()  # type: ignore[misc]
        return float(value)

    latency_final_var = await _final_inferred_var("latency_strain")
    budget_final_var = await _final_inferred_var("budget_reserve")
    assert latency_final_var > budget_final_var, (
        "latency_strain's final inferred_var should sit meaningfully above "
        "budget_reserve's constant-input variance floor, reflecting a live "
        "EWMA filter reacting to genuinely moving raw data -- not just an "
        "idling filter that settled at the same floor a dead channel would"
    )

    await daemon.stop()
