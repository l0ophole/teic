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

# Seed variance for a channel's first-ever observation. Deliberately
# nonzero: seeding at 0.0 would make a channel whose raw input never
# changes (budget_reserve, effector_integrity, and the still-placeholder
# 0.0 channels) report inferred_var == 0.0 on every tick forever, which
# looks like perfect certainty from tick one rather than a live inference
# process. Starting "uncertain" and letting that decay as evidence arrives
# is the honest behavior.
INITIAL_VARIANCE = 1.0

# Small per-tick process noise added before the EWMA decay is applied.
# Without it, a channel with a perfectly constant raw input has a zero
# residual (raw - prior_mean) every tick after the first, and the
# variance recurrence collapses to exactly 0.0 and stays pinned there --
# the same "instant fake certainty" bypass INITIAL_VARIANCE guards
# against, just one tick later. This term represents "the true signal
# could still drift even if we haven't observed it doing so yet," which
# keeps constant-input channels' variance decaying toward a small nonzero
# floor instead of hitting an exact 0.0. Small relative to ALPHA-scale
# residuals so it doesn't meaningfully change the filter's behavior on
# channels that *do* have real variation to react to.
PROCESS_NOISE = 0.01


class ChannelInference:
    """Per-channel EWMA mean/variance filter, one instance per session."""

    def __init__(self) -> None:
        # channel -> (inferred_value, variance)
        self._state: dict[str, tuple[float, float]] = {}

    def update(self, channel: str, raw: float) -> tuple[float, float]:
        if channel not in self._state:
            self._state[channel] = (raw, INITIAL_VARIANCE)
            return self._state[channel]

        prior_mean, prior_var = self._state[channel]
        new_mean = prior_mean + ALPHA * (raw - prior_mean)
        new_var = (1 - ALPHA) * (prior_var + PROCESS_NOISE) + ALPHA * (raw - prior_mean) ** 2
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
