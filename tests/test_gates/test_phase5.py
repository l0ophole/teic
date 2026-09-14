"""Phase 5 gate -- PLAN.md Build Order row 5: "Sub-threshold candidate
demonstrably modulates but never broadcasts/reports."

Two-part dissociation, mirroring Phase 2/3/4's gate structure of
same-inputs-except-one-thing:

1. NEVER-BROADCASTS: a candidate engineered to be sub-threshold
   (ignited=False) has content that never reaches a rendered prompt via
   `workspace/broadcast.py`'s `render_prompt_if_ignited()` -- the actual
   enforcement seam, since `assemble_prompt()` itself is a pure formatter
   with no ignited check of its own, by design.
2. DEMONSTRABLY-MODULATES: that same sub-threshold candidate's salience
   still changes `ModulationParams.salience_weight_overrides` on the next
   tick's compute() call, via `arbiter.salience_overrides()` -- proving the
   "can-modulate but cannot-be-broadcast" dual property, not just that
   sub-threshold candidates are silently dropped.

A contrast case (supra-threshold candidate) shows the same machinery *does*
let content reach a rendered prompt when ignited -- proving
`render_prompt_if_ignited` isn't just vacuously always returning `None`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from teic.interoception.modulation import ModulationCompute
from teic.models.affect import AffectState
from teic.models.registers import RegisterState
from teic.models.workspace import WorkspaceCandidate
from teic.workspace.arbiter import WorkspaceArbiter, salience_overrides
from teic.workspace.broadcast import render_prompt_if_ignited

CHANNELS = (
    "context_pressure", "budget_reserve", "burn_rate", "prediction_error",
    "surprise_volatility", "effector_integrity", "latency_strain",
    "epistemic_tension", "goal_gradient", "memory_fragmentation", "social_contact",
)

SECRET_MARKER = "sub-threshold-secret-content"
LOUD_MARKER = "supra-threshold-loud-content"


def _affect() -> AffectState:
    return AffectState(valence=0.0, arousal=0.0, mood=0.0, tick_id=1, ts=datetime.now(UTC))


def _neutral_registers() -> RegisterState:
    base = dict.fromkeys(CHANNELS, 0.0)
    variances = dict.fromkeys(CHANNELS, 0.01)
    return RegisterState(tick_id=1, ts=datetime.now(UTC), variances=variances, **base)


def _modulation():
    return ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=5.0).compute(
        _neutral_registers(), _affect(), mood=0.0
    )


def test_subthreshold_candidate_never_reaches_rendered_prompt():
    weak = WorkspaceCandidate(
        source_module="memory", content={"text": SECRET_MARKER},
        novelty=0.1, precision=0.1, affective_weight=0.1, goal_relevance=0.1,
    )
    broadcast = WorkspaceArbiter().select([weak], _affect(), mood=0.0, tick_id=1)
    assert broadcast.ignited is False
    assert broadcast.winner.content["text"] == SECRET_MARKER  # arbiter still scored it

    prompt = render_prompt_if_ignited(broadcast, narrative_tail=[], modulation=_modulation())
    # The actual non-negotiable: below threshold, no prompt is even
    # constructed -- SECRET_MARKER never reaches a renderable message.
    assert prompt is None


def test_suprathreshold_candidate_does_reach_rendered_prompt():
    strong = WorkspaceCandidate(
        source_module="interoception", content={"text": LOUD_MARKER},
        novelty=0.95, precision=0.95, affective_weight=0.95, goal_relevance=0.95,
    )
    broadcast = WorkspaceArbiter().select([strong], _affect(), mood=0.0, tick_id=1)
    assert broadcast.ignited is True

    prompt = render_prompt_if_ignited(broadcast, narrative_tail=[], modulation=_modulation())
    assert prompt is not None
    rendered = " ".join(m["content"] for m in prompt.messages)
    assert LOUD_MARKER in rendered
    # Contrast case: proves the previous test isn't just a vacuously-always-
    # None function -- ignition really does gate content reaching a
    # rendered prompt, in both directions.


def test_subthreshold_candidate_still_shifts_next_tick_salience_overrides():
    weak = WorkspaceCandidate(
        source_module="memory", content={"text": SECRET_MARKER},
        novelty=0.1, precision=0.1, affective_weight=0.1, goal_relevance=0.1,
    )
    strong_other = WorkspaceCandidate(
        source_module="interoception", content={}, novelty=0.5, precision=0.5,
        affective_weight=0.5, goal_relevance=0.5,
    )
    broadcast = WorkspaceArbiter().select([weak, strong_other], _affect(), mood=0.0, tick_id=1)
    assert broadcast.winner.source_module == "interoception"  # weak lost the competition

    overrides = salience_overrides([weak, strong_other], broadcast.winner)
    compute = ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=5.0)
    without = compute.compute(_neutral_registers(), _affect(), mood=0.0)
    with_prior = compute.compute(
        _neutral_registers(), _affect(), mood=0.0, prior_salience_overrides=overrides
    )
    assert with_prior.salience_weight_overrides["memory"] == pytest.approx(1.0 + weak.salience)
    assert "memory" not in without.salience_weight_overrides
    # The losing, never-broadcast candidate still moved next tick's
    # modulation params -- the "demonstrably modulates" half of the gate.
