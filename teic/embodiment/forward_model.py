"""Adaptive prediction of tick-timing latency.

`ForwardModel` predicts the daemon's own next-tick `dt_real` (wall-clock time
elapsed in the prior tick) by scaling a nominal `dt` by an adaptive multiplier.
It uses a fixed-gain EWMA filter to learn the ratio of actual to nominal timing,
allowing it to anticipate jitter and step-changes in tick latency.

Currently, tick timing stands in for effector latency (i.e. the time a tool call
would take) until Phase 5+ when real LLM/tool effectors exist. At that point,
this module may be extended to predict call latency instead, or a parallel
model may be introduced; for now, the interface mirrors the
interoception/inference.py pattern so the integration is clear.
"""

from __future__ import annotations

# Fixed EWMA gain. Same convention as inference.py: named rather than a bare
# literal at the call site so its meaning is visible and grep-able.
ALPHA = 0.3

# Seed multiplier: predicted latency equals nominal latency until evidence
# says otherwise. An unbiased prior.
INITIAL_MULTIPLIER = 1.0

# Ceiling on the error signal. Same value as sensors.py uses for latency_strain
# so the two channels are comparable in magnitude. Prevents a single extreme
# outlier from dominating the error signal across the heartbeat loop.
ERROR_CLAMP_MAX = 5.0


class ForwardModel:
    """Per-session adaptive tick timing latency predictor.

    Learns the ratio of actual tick latency (dt_real) to nominal tick period
    (1 / tempo_hz) via an EWMA filter, so predictions improve as the session
    adapts to the underlying system's behavior (e.g., garbage collection pauses,
    system load, or deliberate tempo changes).
    """

    def __init__(self) -> None:
        """Initialize with neutral (1:1) predicted-to-nominal ratio."""
        self._multiplier: float = INITIAL_MULTIPLIER

    def predict_dt_real(self, nominal_dt: float) -> float:
        """Forecast the next tick's wall-clock latency.

        Args:
            nominal_dt: The expected tick period (1 / tempo_hz), in seconds.

        Returns:
            Predicted dt_real for the next tick, using the current (not-yet-updated)
            multiplier. Computed as `nominal_dt * self._multiplier`.
        """
        return nominal_dt * self._multiplier

    def observe(
        self,
        actual_dt_real: float,
        nominal_dt: float,
        predicted_dt_real: float,
    ) -> float:
        """Observe an actual tick latency and update the model.

        The error is computed against the prediction *before* this call updates
        the model. This order ensures a step-change in tick latency produces
        a large error spike (old multiplier, wrong) followed by decay as the
        multiplier adapts, rather than an instantly-perfect prediction.

        Args:
            actual_dt_real: Observed wall-clock latency (seconds).
            nominal_dt: The tick period in effect for this tick (seconds).
            predicted_dt_real: The prediction made before this observation
                (typically from `predict_dt_real(nominal_dt)` on the same tick).

        Returns:
            Normalized prediction error, clamped to [0, ERROR_CLAMP_MAX].
            Computed as `min(abs(actual - predicted) / predicted, ERROR_CLAMP_MAX)`.
        """
        # Compute error using the old prediction (before update)
        error = min(
            abs(actual_dt_real - predicted_dt_real) / predicted_dt_real,
            ERROR_CLAMP_MAX,
        )

        # Update the multiplier using EWMA: new target is actual / nominal
        new_target = actual_dt_real / nominal_dt
        self._multiplier += ALPHA * (new_target - self._multiplier)

        return error
