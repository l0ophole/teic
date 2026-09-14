"""Phase 6's anticipatory pressure -- allostatic forecasting.

Forecasts a channel's near-future trajectory from `ChannelInference`'s own
posterior mean (via its `current()` accessor), reusing that inference
rather than forking a parallel model -- see phase6-plan.md task 4.
`anticipatory_pressure()` is what lets a caller act pre-emptively: it can
be nonzero even while the channel's *current* value is still safely on the
right side of a threshold, as long as the trend says it won't stay there.
"""

from __future__ import annotations

from teic.interoception.inference import ChannelInference


class AllostaticForecaster:
    """Per-channel linear-trend forecaster over `ChannelInference`'s
    posterior mean. One instance per session. Call `forecast()`/
    `anticipatory_pressure()` after that tick's `ChannelInference.update()`/
    `infer()` call, so the posterior it reads is current."""

    def __init__(self, inference: ChannelInference, horizon_ticks: int) -> None:
        self._inference = inference
        self._horizon_ticks = horizon_ticks
        self._last_mean: dict[str, float] = {}

    def forecast(self, channel: str) -> list[float]:
        """Projects `channel`'s posterior mean `horizon_ticks` steps
        forward, linearly extrapolating the trend (delta) since the
        previous call on this channel. A channel with no prior observed
        trend (first call, or `ChannelInference` has never seen it) returns
        a flat trajectory at the current mean (or all-zero if the channel
        has genuinely never been observed) -- an honest "no trend known
        yet," not a fabricated slope."""
        current = self._inference.current(channel)
        if current is None:
            return [0.0] * self._horizon_ticks
        mean, _ = current
        trend = mean - self._last_mean.get(channel, mean)
        self._last_mean[channel] = mean
        return [mean + trend * step for step in range(1, self._horizon_ticks + 1)]

    def anticipatory_pressure(
        self, channel: str, threshold: float, lower_is_worse: bool = True
    ) -> float:
        """Anticipatory pressure in `[0.0, 1.0]`: how soon (as a fraction of
        `horizon_ticks`, 1.0 = next tick) the forecast trajectory crosses
        `threshold`. `0.0` if it never crosses within the horizon -- no
        anticipated violation, not "safe forever." `lower_is_worse=True`
        (the default, matching `budget_reserve`: low is precarious) checks
        for the trajectory dropping to/below `threshold`; set `False` for
        channels where rising is the danger (e.g. `burn_rate`)."""
        trajectory = self.forecast(channel)
        for step, value in enumerate(trajectory, start=1):
            crossed = value <= threshold if lower_is_worse else value >= threshold
            if crossed:
                return 1.0 - (step - 1) / self._horizon_ticks
        return 0.0
