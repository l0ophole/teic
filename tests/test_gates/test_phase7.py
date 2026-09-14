"""Phase 7 cp1 gate -- self-model-construction.

Checkpoint scope only (see docs/plans/phase7-plan.md cp1): `SelfModel` must
be built from real telemetry (RegisterState/AffectState/ForwardModel
prediction error), not hand-authored, and must version/carry forward across
ticks. Metacognition and behavioral wiring are cp2/cp3 scope, not tested
here.
"""

from __future__ import annotations

from datetime import datetime, timezone

from teic.embodiment.forward_model import ERROR_CLAMP_MAX
from teic.models.affect import AffectState
from teic.models.registers import REGISTER_CHANNELS, RegisterState
from teic.selfmodel.builder import build_self_model


def _register_state(**overrides: float) -> RegisterState:
    values = dict.fromkeys(REGISTER_CHANNELS, 0.0)
    values.update(overrides)
    return RegisterState(**values, variances=dict.fromkeys(REGISTER_CHANNELS, 0.0), tick_id=1, ts=datetime.now(timezone.utc))


def _affect_state(valence: float = 0.0, arousal: float = 0.0, mood: float = 0.0) -> AffectState:
    return AffectState(valence=valence, arousal=arousal, mood=mood, tick_id=1, ts=datetime.now(timezone.utc))


def test_self_model_built_from_real_register_and_affect_telemetry() -> None:
    register_state = _register_state(effector_integrity=0.8, latency_strain=0.3)
    affect_state = _affect_state(valence=0.4, arousal=0.2, mood=0.1)

    self_model = build_self_model(
        register_state=register_state,
        affect_state=affect_state,
        prediction_error=0.0,
        history_summary="no prior memories",
        prior=None,
        tick_id=1,
    )

    assert self_model.body["effector_integrity"] == 0.8
    assert self_model.body["latency_strain"] == 0.3
    assert self_model.interoception_summary == register_state.as_dict()
    assert self_model.mental_state_estimate == {"valence": 0.4, "arousal": 0.2, "mood": 0.1}
    assert self_model.history_summary == "no prior memories"
    assert self_model.version == 1
    assert self_model.last_edited_tick_id == 1


def test_agency_derives_from_forward_model_prediction_error_not_hardcoded() -> None:
    register_state = _register_state()
    affect_state = _affect_state()

    confident = build_self_model(
        register_state=register_state, affect_state=affect_state,
        prediction_error=0.0, history_summary="", prior=None, tick_id=1,
    )
    uncertain = build_self_model(
        register_state=register_state, affect_state=affect_state,
        prediction_error=ERROR_CLAMP_MAX, history_summary="", prior=None, tick_id=1,
    )

    assert confident.agency == 1.0
    assert uncertain.agency == 0.0
    assert confident.agency > uncertain.agency


def test_version_and_temporal_self_carry_forward_across_ticks() -> None:
    register_state = _register_state()
    affect_state = _affect_state()

    first = build_self_model(
        register_state=register_state, affect_state=affect_state,
        prediction_error=0.0, history_summary="", prior=None, tick_id=1,
    )
    second = build_self_model(
        register_state=register_state, affect_state=affect_state,
        prediction_error=0.0, history_summary="", prior=first, tick_id=2,
    )

    assert first.version == 1
    assert second.version == 2
    assert second.temporal_self["prior_version"] == 1.0
    assert second.temporal_self["prior_tick_id"] == 1.0
    assert second.last_edited_tick_id == 2


def test_goal_gradient_resolved_via_identity_traits_not_hardcoded_zero() -> None:
    register_state = _register_state()
    positive_mood = _affect_state(mood=0.6)
    negative_mood = _affect_state(mood=-0.6)

    positive = build_self_model(
        register_state=register_state, affect_state=positive_mood,
        prediction_error=0.0, history_summary="", prior=None, tick_id=1,
    )
    negative = build_self_model(
        register_state=register_state, affect_state=negative_mood,
        prediction_error=0.0, history_summary="", prior=None, tick_id=1,
    )

    # Real signal (mood), not the sensors.py/daemon.py 0.0 placeholder --
    # must actually move with the input, in the expected direction.
    assert positive.identity_traits["goal_gradient"] > 0.0
    assert negative.identity_traits["goal_gradient"] < 0.0
    assert positive.identity_traits["goal_gradient"] != negative.identity_traits["goal_gradient"]


def test_identity_traits_carry_forward_and_stay_stable_across_ticks() -> None:
    register_state = _register_state()
    affect_state = _affect_state()

    first = build_self_model(
        register_state=register_state, affect_state=affect_state,
        prediction_error=0.0, history_summary="", prior=None, tick_id=1,
    )
    second = build_self_model(
        register_state=register_state, affect_state=affect_state,
        prediction_error=0.0, history_summary="", prior=first, tick_id=2,
    )

    assert first.identity_traits["viability_preference"] == second.identity_traits["viability_preference"]
