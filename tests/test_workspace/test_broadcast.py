from datetime import UTC, datetime

from teic.interoception.modulation import ModulationCompute
from teic.models.affect import AffectState
from teic.models.registers import RegisterState
from teic.models.workspace import WorkspaceCandidate
from teic.workspace.arbiter import WorkspaceArbiter
from teic.workspace.broadcast import render_prompt_if_ignited

CHANNELS = (
    "context_pressure", "budget_reserve", "burn_rate", "prediction_error",
    "surprise_volatility", "effector_integrity", "latency_strain",
    "epistemic_tension", "goal_gradient", "memory_fragmentation", "social_contact",
)


def _affect() -> AffectState:
    return AffectState(valence=0.0, arousal=0.0, mood=0.0, tick_id=1, ts=datetime.now(UTC))


def _registers() -> RegisterState:
    base = dict.fromkeys(CHANNELS, 0.0)
    variances = dict.fromkeys(CHANNELS, 0.01)
    return RegisterState(tick_id=1, ts=datetime.now(UTC), variances=variances, **base)


def _modulation():
    return ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=5.0).compute(
        _registers(), _affect(), mood=0.0
    )


def test_subthreshold_broadcast_renders_no_prompt():
    weak = WorkspaceCandidate(
        source_module="memory", content={"text": "secret"},
        novelty=0.1, precision=0.1, affective_weight=0.1, goal_relevance=0.1,
    )
    broadcast = WorkspaceArbiter().select([weak], _affect(), mood=0.0, tick_id=1)
    assert broadcast.ignited is False
    assert render_prompt_if_ignited(broadcast, narrative_tail=[], modulation=_modulation()) is None


def test_suprathreshold_broadcast_renders_a_prompt():
    strong = WorkspaceCandidate(
        source_module="interoception", content={"text": "loud"},
        novelty=0.95, precision=0.95, affective_weight=0.95, goal_relevance=0.95,
    )
    broadcast = WorkspaceArbiter().select([strong], _affect(), mood=0.0, tick_id=1)
    assert broadcast.ignited is True
    prompt = render_prompt_if_ignited(broadcast, narrative_tail=[], modulation=_modulation())
    assert prompt is not None
    assert any("loud" in m["content"] for m in prompt.messages)
