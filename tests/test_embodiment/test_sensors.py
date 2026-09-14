from __future__ import annotations

from datetime import UTC, datetime

from teic.embodiment.sensors import SensorArray
from teic.models.tick import TickContext


def _tick_ctx(tick_index: int, dt_real: float, tempo_hz: float = 1.0) -> TickContext:
    return TickContext(
        session_id="s1",
        tick_index=tick_index,
        wall_ts=datetime.now(UTC),
        dt_real=dt_real,
        dt_subjective=dt_real,
        tempo_hz=tempo_hz,
        idle_state=False,
        pending_input_count=0,
    )


def test_latency_strain_zero_when_dt_real_matches_expected() -> None:
    sensors = SensorArray()
    sample = sensors.sample(_tick_ctx(0, dt_real=1.0, tempo_hz=1.0))
    assert sample.latency_strain == 0.0


def test_jittered_dt_real_produces_varying_latency_strain_and_rising_volatility() -> None:
    sensors = SensorArray()
    tempo_hz = 1.0
    expected = 1.0 / tempo_hz

    # First sample: constant strain of 0.0, and volatility must be 0.0.
    first = sensors.sample(_tick_ctx(0, dt_real=expected, tempo_hz=tempo_hz))
    assert first.latency_strain == 0.0
    assert first.surprise_volatility == 0.0

    jittered_dt_reals = [1.2, 0.8, 1.5, 0.6, 1.1, 0.9, 1.3, 0.7, 1.05]
    strains = []
    volatilities = []
    for i, dt_real in enumerate(jittered_dt_reals, start=1):
        sample = sensors.sample(_tick_ctx(i, dt_real=dt_real, tempo_hz=tempo_hz))
        strains.append(sample.latency_strain)
        volatilities.append(sample.surprise_volatility)

    # Nonzero, varying latency_strain values.
    assert any(s != 0.0 for s in strains)
    assert len(set(strains)) > 1

    # Volatility responded to the jitter: went from 0.0 to something nonzero.
    assert volatilities[-1] > 0.0


def test_latency_strain_clamped_to_five() -> None:
    sensors = SensorArray()
    # Wildly large dt_real relative to expected interval.
    sample = sensors.sample(_tick_ctx(0, dt_real=100.0, tempo_hz=1.0))
    assert sample.latency_strain == 5.0


def test_context_pressure_scales_and_clamps() -> None:
    sensors = SensorArray()
    ctx = _tick_ctx(0, dt_real=1.0, tempo_hz=1.0).model_copy(update={"pending_input_count": 2})
    sample = sensors.sample(ctx)
    assert sample.context_pressure == 2 / 5.0

    ctx_over = _tick_ctx(1, dt_real=1.0, tempo_hz=1.0).model_copy(
        update={"pending_input_count": 50}
    )
    sample_over = sensors.sample(ctx_over)
    assert sample_over.context_pressure == 1.0


def test_placeholder_channels_hold_documented_defaults() -> None:
    sensors = SensorArray()
    sample = sensors.sample(_tick_ctx(0, dt_real=1.0, tempo_hz=1.0))
    assert sample.budget_reserve == 1.0
    assert sample.effector_integrity == 1.0
    for channel in (
        "burn_rate",
        "prediction_error",
        "epistemic_tension",
        "goal_gradient",
        "memory_fragmentation",
        "social_contact",
    ):
        assert getattr(sample, channel) == 0.0
