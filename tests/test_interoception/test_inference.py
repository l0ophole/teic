from __future__ import annotations

from datetime import UTC, datetime

from teic.embodiment.sensors import RawSensorSample
from teic.interoception.inference import ChannelInference
from teic.models.registers import REGISTER_CHANNELS


def _raw(value: float) -> RawSensorSample:
    return RawSensorSample(**{ch: value for ch in REGISTER_CHANNELS})


def test_repeated_identical_input_drives_variance_toward_zero() -> None:
    inference = ChannelInference()
    # Seed with a different first value so the mean has somewhere to move
    # from -- otherwise every residual would be 0 from the very first call
    # and the decay this test is meant to exercise wouldn't show up.
    inference.update("latency_strain", 0.0)

    variances = []
    for _ in range(30):
        _, var = inference.update("latency_strain", 0.5)
        variances.append(var)

    # After the first couple of updates, variance should be monotonically
    # non-increasing as the mean converges on the now-constant input and
    # residuals shrink toward 0.
    tail = variances[2:]
    assert all(tail[i] >= tail[i + 1] for i in range(len(tail) - 1))
    # Geometric decay (factor ~(1-alpha) per step once converged): well
    # below its early peak after enough repeated-identical updates.
    assert variances[-1] < variances[0] * 0.01


def test_alternating_input_keeps_variance_bounded_away_from_zero() -> None:
    inference = ChannelInference()
    variance = 0.0
    for i in range(20):
        raw = 0.0 if i % 2 == 0 else 1.0
        _, variance = inference.update("latency_strain", raw)

    assert variance > 0.01


def test_first_update_seeds_state_with_raw_value_and_zero_variance() -> None:
    inference = ChannelInference()
    mean, var = inference.update("context_pressure", 0.7)
    assert mean == 0.7
    assert var == 0.0


def test_infer_returns_register_state_with_all_channels_populated() -> None:
    inference = ChannelInference()
    ts = datetime.now(UTC)
    raw = _raw(0.25)

    state = inference.infer(raw, tick_id=42, ts=ts)

    assert state.tick_id == 42
    assert state.ts == ts
    for channel in REGISTER_CHANNELS:
        assert getattr(state, channel) == 0.25
        assert channel in state.variances
        assert state.variances[channel] == 0.0

    assert set(state.variances.keys()) == set(REGISTER_CHANNELS)
