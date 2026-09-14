"""Raw per-tick measurement layer -- Phase 1's real (minimal) sensing.

`SensorArray` computes the two channels that are genuinely observable this
early (`latency_strain` from tick timing jitter, `context_pressure` from
pending input volume) plus a derived volatility signal, and holds every
other channel at a documented placeholder until the phase that wires it:
burn_rate/budget_reserve -> 6, epistemic_tension -> 2/7, goal_gradient -> 5,
memory_fragmentation -> 4, social_contact -> 9, effector_integrity ->
whenever an LLM call is actually attempted (also 6+). `prediction_error` is
threaded through from the caller as of Phase 3 (see `teic/daemon.py`'s
`ForwardModel`/`ProtentionBuffer` wiring) rather than computed here.

Constructed once per session (not per tick): it holds a ring buffer of
recent `latency_strain` values, so state must persist across `sample()`
calls on the same instance.
"""

from __future__ import annotations

import statistics
from collections import deque

from pydantic import BaseModel

from teic.models.registers import REGISTER_CHANNELS
from teic.models.tick import TickContext

_LATENCY_HISTORY_LEN = 10


class RawSensorSample(BaseModel):
    """One float per register channel, straight off the (minimal) sensors."""

    context_pressure: float
    budget_reserve: float
    burn_rate: float
    prediction_error: float
    surprise_volatility: float
    effector_integrity: float
    latency_strain: float
    epistemic_tension: float
    goal_gradient: float
    memory_fragmentation: float
    social_contact: float


# Dev-time invariant check, not a runtime guard: this is stripped under
# `python -O`. It exists so a future edit to REGISTER_CHANNELS or
# RawSensorSample that drifts the two apart fails loudly at import time in
# normal (non-optimized) test/dev runs, rather than silently.
assert set(RawSensorSample.model_fields) == set(REGISTER_CHANNELS), (
    "RawSensorSample must have exactly one field per REGISTER_CHANNELS entry"
)


class SensorArray:
    """Per-session sensing state.

    Holds a ring buffer of the last `_LATENCY_HISTORY_LEN` `latency_strain`
    readings so `surprise_volatility` can be derived as their population
    stddev -- a proxy for "how jittery has timing been lately" until
    Phase 3 gives us a real prediction-error signal.
    """

    def __init__(self) -> None:
        self._latency_history: deque[float] = deque(maxlen=_LATENCY_HISTORY_LEN)

    def sample(self, tick_ctx: TickContext, prediction_error: float = 0.0) -> RawSensorSample:
        # Not guarded against tempo_hz == 0.0: every producer of TickContext
        # in this codebase (Heartbeat) takes tempo_hz as a positive-Hz
        # config value, so a zero tempo would already be a misconfiguration
        # upstream. Not this module's job to defend against that -- if it
        # ever needs to be, TickContext is the right place for validation.
        expected = 1.0 / tick_ctx.tempo_hz
        latency_strain = min(max(abs(tick_ctx.dt_real - expected) / expected, 0.0), 5.0)

        self._latency_history.append(latency_strain)
        surprise_volatility = statistics.pstdev(self._latency_history)

        context_pressure = min(tick_ctx.pending_input_count / 5.0, 1.0)

        return RawSensorSample(
            context_pressure=context_pressure,
            budget_reserve=1.0,  # no spend tracking until Phase 6
            burn_rate=0.0,  # wired in Phase 6 (budget/spend tracking)
            prediction_error=prediction_error,
            surprise_volatility=surprise_volatility,
            effector_integrity=1.0,  # no LLM call attempted yet
            latency_strain=latency_strain,
            epistemic_tension=0.0,  # wired in Phase 2/7
            goal_gradient=0.0,  # wired in Phase 5
            memory_fragmentation=0.0,  # wired in Phase 4
            social_contact=0.0,  # wired in Phase 9
        )
