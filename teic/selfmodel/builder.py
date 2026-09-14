"""Builds/updates a `SelfModel` each tick from the same telemetry every
other module sees -- no privileged access, no hand-authored fields.

`body`/`agency` reuse `ForwardModel`'s own comparator output (the prediction
error the daemon already computes each tick) rather than forking a second
comparator. `interoception_summary` is `RegisterState.as_dict()` verbatim.
`history_summary` comes from `MemoryStore.query()`, the same retrieval path
Phase 5's memory candidate uses. `temporal_self`/`version` track the prior
`SelfModel` instance across ticks.

`goal_gradient` resolution (Phase 5/6 placeholder, see
`embodiment/sensors.py` and `daemon.py`'s `INTEROCEPTION_GOAL_RELEVANCE_BASELINE`):
`RegisterState` is built by `SensorArray.sample()` *before* this module runs,
so a self-model computed this tick cannot retroactively change this tick's
`goal_gradient` -- the dependency only closes across a tick boundary. This
module resolves the value into `identity_traits["goal_gradient"]` (real
signal: mood, the slow viability-linked integrator, scaled by the stable
`viability_preference` trait) so a later tick's `SensorArray.sample()` call
can be wired to read *last* tick's `identity_traits["goal_gradient"]`
instead of a hardcoded `0.0`. That daemon-side wiring is cp3's job (task 8);
this module only produces the value.
"""

from __future__ import annotations

from teic.embodiment.forward_model import ERROR_CLAMP_MAX
from teic.models.affect import AffectState
from teic.models.registers import RegisterState
from teic.models.self_model import SelfModel

_BODY_CHANNELS: tuple[str, ...] = ("effector_integrity", "latency_strain")

# Stable trait: the system prefers positive viability trajectories. Not yet
# learned/adapted -- a fixed seed, same "unbiased prior" convention as
# ForwardModel.INITIAL_MULTIPLIER.
_VIABILITY_PREFERENCE = 1.0


def build_self_model(
    *,
    register_state: RegisterState,
    affect_state: AffectState,
    prediction_error: float,
    history_summary: str,
    prior: SelfModel | None,
    tick_id: int,
) -> SelfModel:
    """Construct this tick's `SelfModel` from real telemetry.

    `history_summary` is passed in already resolved (built by the caller via
    `MemoryStore.query()`, matching Phase 5's memory-candidate pattern) so
    this function stays synchronous and pure, like `AffectDynamics.update`.
    """
    register_values = register_state.as_dict()
    body = {ch: register_values[ch] for ch in _BODY_CHANNELS}

    # Agency: reuses ForwardModel's own comparator output (prediction_error,
    # already clamped to [0, ERROR_CLAMP_MAX] by ForwardModel.observe) rather
    # than forking a second comparator. Low error -> the system's model of
    # its own timing held -> high sense of agency.
    agency = max(0.0, 1.0 - prediction_error / ERROR_CLAMP_MAX)

    identity_traits = dict(prior.identity_traits) if prior is not None else {
        "viability_preference": _VIABILITY_PREFERENCE
    }
    identity_traits["goal_gradient"] = max(
        -1.0, min(1.0, affect_state.mood * identity_traits["viability_preference"])
    )

    mental_state_estimate = {
        "valence": affect_state.valence,
        "arousal": affect_state.arousal,
        "mood": affect_state.mood,
    }

    version = prior.version + 1 if prior is not None else 1
    temporal_self = {
        "prior_version": float(prior.version) if prior is not None else 0.0,
        "prior_tick_id": float(prior.last_edited_tick_id) if prior is not None else 0.0,
    }

    return SelfModel(
        body=body,
        agency=agency,
        interoception_summary=register_values,
        history_summary=history_summary,
        identity_traits=identity_traits,
        mental_state_estimate=mental_state_estimate,
        temporal_self=temporal_self,
        version=version,
        last_edited_tick_id=tick_id,
    )
