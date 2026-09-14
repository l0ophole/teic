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

    # Variance should be monotonically non-increasing as the mean converges
    # on the now-constant input and residuals shrink toward 0.
    assert all(variances[i] >= variances[i + 1] for i in range(len(variances) - 1))
    # It decays well below its early peak -- but, thanks to PROCESS_NOISE,
    # settles on a small nonzero floor rather than hitting 0.0 outright.
    assert variances[-1] < variances[0] * 0.05
    assert variances[-1] > 0.0


def test_constant_input_variance_decays_toward_nonzero_floor_not_zero() -> None:
    """Regression test for the bypass a pure fixed-gain EWMA has: a channel
    whose raw input never changes (e.g. budget_reserve, effector_integrity,
    or any of the still-placeholder 0.0 channels) would otherwise have its
    variance collapse to exactly 0.0 from the second tick onward and stay
    pinned there forever -- fake perfect certainty rather than a live
    inference process. PROCESS_NOISE must keep it decaying tick-over-tick
    toward a small floor without ever hitting 0.0 exactly."""
    inference = ChannelInference()

    variances = []
    for _ in range(20):
        _, var = inference.update("budget_reserve", 1.0)
        variances.append(var)

    # Never exactly zero, on any tick, including the very first.
    assert all(v > 0.0 for v in variances)
    # Monotonically decaying...
    assert all(variances[i] >= variances[i + 1] for i in range(len(variances) - 1))
    # ...from an initial "uncertain" seed down toward a much smaller floor.
    assert variances[0] == 1.0
    assert variances[-1] < variances[0] * 0.05
    assert variances[-1] > 0.0


def test_alternating_input_keeps_variance_bounded_away_from_zero() -> None:
    inference = ChannelInference()
    variance = 0.0
    for i in range(20):
        raw = 0.0 if i % 2 == 0 else 1.0
        _, variance = inference.update("latency_strain", raw)

    assert variance > 0.01


def test_first_update_seeds_state_with_raw_value_and_nonzero_variance() -> None:
    inference = ChannelInference()
    mean, var = inference.update("context_pressure", 0.7)
    assert mean == 0.7
    # Nonzero on purpose -- see INITIAL_VARIANCE's docstring in inference.py.
    assert var > 0.0


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
        # First-ever observation per channel: seeded at INITIAL_VARIANCE,
        # not 0.0 (see test_constant_input_variance_decays_toward_nonzero_floor_not_zero).
        assert state.variances[channel] > 0.0

    assert set(state.variances.keys()) == set(REGISTER_CHANNELS)
