"""Phase 2's literal gate wording as a unit test: identical prompt text,
different registers -> divergent tempo/temperature/speak-gate."""

from __future__ import annotations

from datetime import UTC, datetime

from teic.interoception.modulation import ModulationCompute
from teic.llm.prompt_assembly import assemble_prompt
from teic.models.affect import AffectState
from teic.models.registers import REGISTER_CHANNELS, RegisterState
from teic.models.workspace import WorkspaceBroadcast, WorkspaceCandidate

_TS = datetime.now(UTC)


def _registers(**overrides: float) -> RegisterState:
    values = dict.fromkeys(REGISTER_CHANNELS, 0.0)
    values["budget_reserve"] = 1.0
    values.update(overrides)
    return RegisterState(
        **values,
        variances=dict.fromkeys(REGISTER_CHANNELS, 0.0),
        tick_id=1,
        ts=_TS,
    )


def _affect(valence: float, arousal: float) -> AffectState:
    return AffectState(valence=valence, arousal=arousal, mood=0.0, tick_id=1, ts=_TS)


def _broadcast() -> WorkspaceBroadcast:
    winner = WorkspaceCandidate(
        source_module="test",
        content={"text": "identical broadcast content"},
        novelty=0.5,
        precision=0.5,
        affective_weight=0.5,
        goal_relevance=0.5,
    )
    return WorkspaceBroadcast(
        broadcast_id="bc-1",
        tick_id=1,
        winner=winner,
        ignited=True,
        mineness_tag="self",
        ts=_TS,
    )


def test_identical_prompt_text_divergent_params_on_divergent_registers() -> None:
    compute = ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=10.0)

    calm_registers = _registers(epistemic_tension=0.0, latency_strain=0.0)
    calm_affect = _affect(valence=0.0, arousal=0.0)
    calm_params = compute.compute(calm_registers, calm_affect, mood=0.0)

    strained_registers = _registers(epistemic_tension=1.0, latency_strain=1.0)
    strained_affect = _affect(valence=-0.5, arousal=1.0)
    strained_params = compute.compute(strained_registers, strained_affect, mood=-0.5)

    broadcast = _broadcast()
    narrative_tail: list[str] = ["prior line one", "prior line two"]

    calm_prompt = assemble_prompt(broadcast, narrative_tail, calm_params)
    strained_prompt = assemble_prompt(broadcast, narrative_tail, strained_params)

    assert calm_prompt.messages == strained_prompt.messages

    assert calm_prompt.temperature != strained_prompt.temperature
    assert calm_params.tempo_hz != strained_params.tempo_hz
    assert calm_params.speak_gate_open != strained_params.speak_gate_open
