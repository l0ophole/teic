"""Turns raw, noisy sensor samples into a calibrated `RegisterState`.

`ChannelInference` is a per-channel fixed-gain EWMA (exponentially weighted
moving average) mean/variance filter -- the minimal "generative model" this
early phase needs so `RegisterState` is never hand-authored (see its
docstring in `teic/models/registers.py`). Phase 3+ may replace this with a
richer per-channel model; the `update()`/`infer()` interface is the seam.
"""

from __future__ import annotations

from datetime import datetime

from teic.embodiment.sensors import RawSensorSample
from teic.models.registers import REGISTER_CHANNELS, RegisterState

# Fixed EWMA gain. Named rather than a bare literal at the call site so its
# meaning (how quickly the filter trusts new evidence over its running
# estimate) is visible and grep-able.
ALPHA = 0.3


class ChannelInference:
    """Per-channel EWMA mean/variance filter, one instance per session."""

    def __init__(self) -> None:
        # channel -> (inferred_value, variance)
        self._state: dict[str, tuple[float, float]] = {}

    def update(self, channel: str, raw: float) -> tuple[float, float]:
        if channel not in self._state:
            self._state[channel] = (raw, 0.0)
            return self._state[channel]

        prior_mean, prior_var = self._state[channel]
        new_mean = prior_mean + ALPHA * (raw - prior_mean)
        new_var = (1 - ALPHA) * (prior_var + ALPHA * (raw - prior_mean) ** 2)
        self._state[channel] = (new_mean, new_var)
        return self._state[channel]

    def infer(self, raw: RawSensorSample, tick_id: int, ts: datetime) -> RegisterState:
        values: dict[str, float] = {}
        variances: dict[str, float] = {}
        for channel in REGISTER_CHANNELS:
            raw_value = getattr(raw, channel)
            inferred_value, variance = self.update(channel, raw_value)
            values[channel] = inferred_value
            variances[channel] = variance

        return RegisterState(
            **values,
            variances=variances,
            tick_id=tick_id,
            ts=ts,
        )
