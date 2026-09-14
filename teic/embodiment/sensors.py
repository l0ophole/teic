"""Raw per-tick measurement layer -- Phase 1's real (minimal) sensing.

`SensorArray` computes the two channels that are genuinely observable this
early (`latency_strain` from tick timing jitter, `context_pressure` from
pending input volume) plus a derived volatility signal, and holds every
other channel at a documented placeholder until the phase that wires it:
burn_rate/budget_reserve -> 6, epistemic_tension -> 2/7, goal_gradient ->
whenever real goal representation exists (self-model/Phase 7+ -- Phase 5's
workspace arbiter turned out not to need a real goal_gradient value itself,
see phase5-plan.md scope ruling 5; it uses a fixed baseline instead of this
channel), memory_fragmentation -> 4, social_contact -> 9, effector_integrity ->
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
    stddev -- a proxy for "how jittery has timing been lately," computed
    here and unchanged by Phase 3. As of Phase 3, `prediction_error` is a
    separate, genuinely learned signal (from `ForwardModel`, wired in via
    `daemon.py` and threaded through `sample()`'s `prediction_error`
    parameter below) -- the two are distinct channels and should not be
    conflated: `surprise_volatility` did not change, `prediction_error`
    is what's new.
    """

    def __init__(self) -> None:
        self._latency_history: deque[float] = deque(maxlen=_LATENCY_HISTORY_LEN)

    def sample(
        self,
        tick_ctx: TickContext,
        prediction_error: float = 0.0,
        budget_reserve: float = 1.0,
        burn_rate: float = 0.0,
    ) -> RawSensorSample:
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
            # Phase 6: threaded in from the caller (teic/daemon.py), same
            # one-tick-lag pattern as prediction_error -- the real
            # ViabilityBudget ledger's post-spend state from the *previous*
            # tick, not computed here.
            budget_reserve=budget_reserve,
            burn_rate=burn_rate,
            prediction_error=prediction_error,
            surprise_volatility=surprise_volatility,
            effector_integrity=1.0,  # no LLM call attempted yet
            latency_strain=latency_strain,
            epistemic_tension=0.0,  # wired in Phase 2/7
            goal_gradient=0.0,  # wired once real goal representation exists (self-model/Phase 7+)
            memory_fragmentation=0.0,  # wired in Phase 4
            social_contact=0.0,  # wired in Phase 9
        )
