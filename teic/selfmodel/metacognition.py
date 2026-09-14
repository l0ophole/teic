"""Metacognitive monitor -- second-order confidence from real signals.

Confidence is calibrated from two independent signals: forward-model
prediction error (lower error -> higher confidence, the same telemetry
`build_self_model`'s `agency` already derives from) and self-model
stability (how much the self-model changed since the prior tick -- a
self-model still in flux is not yet trustworthy to act on). No prior
self-model means nothing to be confident about yet, so instability is
maximal. Consumed by `ModulationCompute.compute()` and the reportability
gate (see their modules) so low confidence measurably raises
retrieval/exploration and high confidence permits committing to action,
rather than staying a number nothing reads.
"""

from __future__ import annotations

from teic.embodiment.forward_model import ERROR_CLAMP_MAX
from teic.models.metacognition import ConfidenceEstimate
from teic.models.self_model import SelfModel

_PREDICTION_ERROR_WEIGHT = 0.6
_STABILITY_WEIGHT = 0.4


def _self_model_instability(current: SelfModel, prior: SelfModel | None) -> float:
    """0..1: how much the self-model changed this tick."""
    if prior is None:
        return 1.0
    agency_delta = abs(current.agency - prior.agency)
    shared_keys = set(current.mental_state_estimate) & set(prior.mental_state_estimate)
    mental_state_delta = (
        sum(
            abs(current.mental_state_estimate[k] - prior.mental_state_estimate[k])
            for k in shared_keys
        )
        / len(shared_keys)
        if shared_keys
        else 0.0
    )
    return max(0.0, min(1.0, agency_delta + mental_state_delta))


def compute_confidence(
    *,
    self_model: SelfModel,
    prior_self_model: SelfModel | None,
    prediction_error: float,
    tick_id: int,
) -> ConfidenceEstimate:
    """Calibrated second-order confidence for this tick's `SelfModel`."""
    prediction_error_component = max(0.0, min(1.0, 1.0 - prediction_error / ERROR_CLAMP_MAX))
    stability_component = 1.0 - _self_model_instability(self_model, prior_self_model)

    confidence = max(
        0.0,
        min(
            1.0,
            _PREDICTION_ERROR_WEIGHT * prediction_error_component
            + _STABILITY_WEIGHT * stability_component,
        ),
    )

    return ConfidenceEstimate(
        confidence=confidence,
        source_signals={
            "prediction_error_component": prediction_error_component,
            "stability_component": stability_component,
        },
        tick_id=tick_id,
    )
