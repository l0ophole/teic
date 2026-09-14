"""Phase 3 gate: forward model, protention buffer, real prediction_error.

Same DI pattern as `test_phase1.py`/`test_phase2.py`: construct `TeicDaemon`,
`await daemon.start()`, then drive `daemon._on_tick` directly via a
separately constructed `Heartbeat` with a scripted fake `sleep_fn`. Unlike
`tests/test_daemon.py` (Task 2's smaller-scope unit-style check of the same
wiring, which jitters a single tick), this is the fuller end-to-end version:
a deliberate two-phase step function -- `N_BASELINE` ticks at nominal
`dt_real`, then a sustained `N_INJECTED` ticks at 3x that -- standing in for
"a tool's latency inflated 3x" per this plan's scope ruling (no real
effector/tool call is wired into the daemon yet; that's Phase 5+).

A subtlety this test's thresholds must respect: `dt_real` is scripted as a
literal step function, but `tempo_hz` itself is *not* held fixed -- it's
still being driven every tick by Phase 2's real `ModulationCompute`
feedback loop (arousal -> tempo_hz -> next tick's nominal interval). With
zero initial arousal, tempo drifts from `base_tempo_hz` down toward
`idle_tempo_hz` after tick 0, which (because the scripted `dt_real` no
longer matches the shrunken nominal interval) drives `latency_strain` and
therefore arousal back up, and tempo climbs toward `max_tempo_hz` and
saturates there within the baseline window. This means the *absolute*
prediction_error values during baseline are not literally ~0.0 by the end
of a 15-tick window -- they're still decaying from that early transient.
The assertions below are therefore relative/ratio-based (spike vs. baseline
mean, spike vs. end-of-run mean), computed from this run's own real
`register_sample` rows, not against hand-derived absolute numbers -- this
is robust to the tempo-feedback transient rather than fighting it.

Assertions use the `raw_value` column (the value `ForwardModel.observe()`/
`SensorArray.sample()` compute fresh each tick), matching `test_daemon.py`'s
convention -- this is the signal whose spike-then-decay shape is under
test, not `inferred_value`'s EWMA-smoothed (and therefore shape-blurred)
version.
"""

from __future__ import annotations

import pytest

from teic.daemon import TeicDaemon
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat

N_BASELINE = 15
N_INJECTED = 20
N_TICKS = N_BASELINE + N_INJECTED

BASELINE_DT_REAL = 1.0
INJECTED_DT_REAL = 3.0

# Baseline window for the "before the spike" comparison: the last few
# ticks of the baseline phase, by which point the forward model has had
# time to re-settle from the tick-0 cold-start transient described above.
BASELINE_WINDOW = range(N_BASELINE - 5, N_BASELINE)

# Window for the "has it adapted to the new regime" comparison: the final
# few ticks of the injected phase.
ADAPTATION_WINDOW = range(N_TICKS - 5, N_TICKS)

# The spike (first injected tick) must be at least this many times the
# baseline-window mean. Per the plan brief's own wording ("at least 3x").
SPIKE_MIN_RATIO = 3.0

# Floor for the baseline mean so the ratio check above is well-defined
# even if that mean were to round to (or land very near) 0.0.
BASELINE_MEAN_FLOOR = 1e-6

# The end-of-run adaptation mean must be smaller than the spike by at
# least this factor -- i.e. re-adapted, not merely "a bit lower".
ADAPTATION_MIN_SHRINK_RATIO = 10.0

# latency_strain (fixed-expectation, never adapts) must stay at least this
# large across the *entire* injected window -- i.e. it does not show
# prediction_error's spike-then-decay shape.
LATENCY_STRAIN_MIN_ELEVATED = 1.0

# ...and its own end-of-run mean must not have shrunk by more than this
# fraction of its first-injected-tick value -- proving "stays elevated",
# not just "elevated at some point".
LATENCY_STRAIN_MAX_DECAY_FRACTION = 0.5


@pytest.mark.asyncio
async def test_phase3_prediction_error_spikes_then_adapts(tmp_settings: Settings) -> None:
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()

    tick_counter = {"n": 0}
    fake_clock = {"t": 0.0}

    def fake_time_source() -> float:
        return fake_clock["t"]

    async def fake_sleep(_seconds: float) -> None:
        # Deliberate two-phase step function: flat nominal dt_real for the
        # baseline phase, then a sustained 3x-inflated dt_real for the
        # injected phase. `dt_real` never returns to baseline -- the model
        # must adapt to a *new* regime, not merely recover from a blip.
        n = tick_counter["n"]
        if n < N_BASELINE:
            fake_clock["t"] += BASELINE_DT_REAL
        else:
            fake_clock["t"] += INJECTED_DT_REAL
        tick_counter["n"] += 1

    fake_heartbeat = Heartbeat(
        tempo_hz=tmp_settings.daemon.base_tempo_hz,
        on_tick=daemon._on_tick,
        time_source=fake_time_source,
        sleep_fn=fake_sleep,
    )
    await fake_heartbeat.run_n_ticks(N_TICKS)

    conn = daemon.conn

    async def _channel_by_tick(channel: str) -> dict[int, float]:
        cursor = await conn.execute(
            "SELECT t.tick_index, rs.raw_value FROM register_sample rs "
            "JOIN tick t ON rs.tick_id = t.tick_id "
            "WHERE t.session_id = ? AND rs.channel = ? "
            "ORDER BY t.tick_index",
            (daemon.session_id, channel),
        )
        rows = await cursor.fetchall()
        assert len(rows) == N_TICKS
        return dict(rows)

    prediction_error = await _channel_by_tick("prediction_error")
    latency_strain = await _channel_by_tick("latency_strain")

    # --- Spike: the first injected tick's prediction_error jumps well
    # above the recent baseline mean. A hardcoded 0.0 placeholder
    # (Phase 0-2 behavior) or a ForwardModel that was never wired up would
    # produce a flat/zero series here and fail this outright.
    baseline_mean = sum(prediction_error[i] for i in BASELINE_WINDOW) / len(BASELINE_WINDOW)
    spike_value = prediction_error[N_BASELINE]
    assert spike_value >= SPIKE_MIN_RATIO * max(baseline_mean, BASELINE_MEAN_FLOOR), (
        f"expected the first injected tick's prediction_error ({spike_value}) to be "
        f"at least {SPIKE_MIN_RATIO}x the baseline-window mean ({baseline_mean})"
    )

    # --- Adaptation: even though dt_real never returns to baseline, the
    # model re-learns the new (3x) regime, so prediction_error decays back
    # down well below the spike by the end of the run. A ForwardModel
    # whose multiplier never updated (e.g. `observe()` computing error but
    # not updating `self._multiplier`) would keep producing this same
    # large error every injected tick and fail this assertion.
    adaptation_mean = sum(prediction_error[i] for i in ADAPTATION_WINDOW) / len(
        ADAPTATION_WINDOW
    )
    assert adaptation_mean * ADAPTATION_MIN_SHRINK_RATIO <= spike_value, (
        f"expected prediction_error to have re-adapted to the sustained 3x regime: "
        f"end-of-run mean ({adaptation_mean}) should be at least "
        f"{ADAPTATION_MIN_SHRINK_RATIO}x smaller than the spike ({spike_value})"
    )

    # --- Contrast: latency_strain is fixed-expectation (built from
    # `tick_ctx.dt_real` vs. the plain `1 / tempo_hz` nominal, never an
    # adaptive multiplier) so it does not show this spike-then-decay
    # shape -- it stays elevated across the *entire* injected window
    # instead of settling back down. This is the concrete evidence that
    # Phase 3 added a genuinely new (learned) signal rather than just
    # relabeling latency_strain.
    injected_latency_strain = [latency_strain[i] for i in range(N_BASELINE, N_TICKS)]
    assert all(v >= LATENCY_STRAIN_MIN_ELEVATED for v in injected_latency_strain), (
        f"expected latency_strain to stay elevated (>= {LATENCY_STRAIN_MIN_ELEVATED}) "
        f"across the entire injected window, got {injected_latency_strain}"
    )
    first_injected_latency_strain = latency_strain[N_BASELINE]
    latency_strain_adaptation_mean = sum(
        latency_strain[i] for i in ADAPTATION_WINDOW
    ) / len(ADAPTATION_WINDOW)
    assert latency_strain_adaptation_mean >= (
        1.0 - LATENCY_STRAIN_MAX_DECAY_FRACTION
    ) * first_injected_latency_strain, (
        "expected latency_strain's end-of-run mean "
        f"({latency_strain_adaptation_mean}) to stay close to its first-injected-tick "
        f"value ({first_injected_latency_strain}), unlike prediction_error's decay -- "
        "latency_strain never adapts"
    )

    await daemon.stop()
