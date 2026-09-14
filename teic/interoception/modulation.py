"""Non-linguistic modulation pathway -- Phase 2, the real gate.

`ModulationParams` is the shared data model `llm/prompt_assembly.py` depends
on for its type-level enforcement boundary (defined since Phase 0).
`ModulationCompute.compute()` is now real: every field is derived from
`RegisterState`/`AffectState`/mood per PLAN.md's "Non-Linguistic Modulation
Pathway" section. Several fields (`retrieval_k`, `retrieval_affect_weight`,
`planning_depth`, `tool_risk_tolerance`) have no consumer yet --
planning/effectors land in Phase 5/6 -- but they are computed from real
inputs now, not stubbed with fixed values, so this phase's gate test can
exercise the whole struct. `retrieval_k`/`retrieval_affect_weight` gained a
real consumer in Phase 4 (`memory/retrieval.py`). `salience_weight_overrides`
gained a real consumer in Phase 5: `compute()`'s new
`prior_salience_overrides` parameter folds in the previous tick's real
per-candidate salience from `teic.workspace.arbiter.salience_overrides()`.
"""

from __future__ import annotations

from pydantic import BaseModel

from teic.interoception.reportability import ReportabilityGate
from teic.models.affect import AffectState
from teic.models.registers import RegisterState

BASE_TEMPERATURE = 0.7


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class ModulationParams(BaseModel):
    temperature: float
    top_p: float
    retrieval_k: int
    retrieval_affect_weight: float
    planning_depth: int
    tool_risk_tolerance: float
    salience_weight_overrides: dict[str, float]
    tempo_hz: float
    speak_gate_open: bool
    tick_id: int


class ModulationCompute:
    """Single entry point: called once per tick, output threaded explicitly
    through every downstream call site. No downstream module re-reads raw
    `RegisterState`/`AffectState` on its own."""

    def __init__(
        self,
        idle_tempo_hz: float,
        max_tempo_hz: float,
        base_temperature: float = BASE_TEMPERATURE,
        reportability: ReportabilityGate | None = None,
    ) -> None:
        self._idle_tempo_hz = idle_tempo_hz
        self._max_tempo_hz = max_tempo_hz
        self._base_temperature = base_temperature
        self._reportability = reportability if reportability is not None else ReportabilityGate()

    def compute(
        self,
        registers: RegisterState,
        affect: AffectState,
        mood: float,
        prior_salience_overrides: dict[str, float] | None = None,
    ) -> ModulationParams:
        # tempo_hz <- tempo_gain(arousal) * base_hz: idle at low arousal,
        # up toward max_tempo_hz as arousal rises -- fed straight into the
        # heartbeat's next sleep interval by daemon.py.
        tempo_hz = _clamp(
            self._idle_tempo_hz + affect.arousal * (self._max_tempo_hz - self._idle_tempo_hz),
            self._idle_tempo_hz,
            self._max_tempo_hz,
        )

        # temperature/top_p <- epistemic_tension (up), negative mood (narrows).
        temperature = _clamp(
            self._base_temperature
            + registers.epistemic_tension * 0.5
            - max(0.0, -mood) * 0.3,
            0.1,
            1.5,
        )
        top_p = _clamp(0.9 + registers.epistemic_tension * 0.05, 0.5, 1.0)

        # retrieval_k/weighting <- context_pressure (down), memory_fragmentation
        # (up), current affect (mood-congruent bias). Unused until Phase 4.
        retrieval_k = round(
            _clamp(
                10 - registers.context_pressure * 5 + registers.memory_fragmentation * 5,
                1,
                20,
            )
        )
        retrieval_affect_weight = _clamp(affect.valence, -1.0, 1.0)

        # planning_depth <- budget_reserve/burn_rate (down when strained),
        # goal_gradient (down when path is obvious). Unused until Phase 5/6.
        planning_depth = round(
            _clamp(
                5
                - (1 - registers.budget_reserve) * 3
                - registers.burn_rate * 2
                - registers.goal_gradient * 2,
                1,
                5,
            )
        )

        # tool_risk_tolerance <- effector_integrity, valence. Unused until an
        # effector exists.
        tool_risk_tolerance = _clamp(
            registers.effector_integrity + affect.valence * 0.2, 0.0, 1.0
        )

        # salience_weight_overrides <- per-source multipliers. "embodiment"
        # is Phase 2's own named example (latency_strain up-weights
        # embodiment candidates); Phase 5 folds in last tick's real
        # per-candidate salience (arbiter.salience_overrides) on top -- this
        # is the "sub-threshold candidate still modulates" pathway, and it
        # runs whether or not last tick's winner was ignited.
        salience_weight_overrides = {"embodiment": 1.0 + registers.latency_strain}
        if prior_salience_overrides is not None:
            salience_weight_overrides.update(prior_salience_overrides)

        # speak_gate_open <- reportability.py's cooldown-gated epistemic
        # threshold. Not yet composed with ignition (Phase 5) or self-model
        # confidence (Phase 7) -- see reportability.py's docstring.
        speak_gate_open = self._reportability.evaluate(registers.epistemic_tension)

        return ModulationParams(
            temperature=temperature,
            top_p=top_p,
            retrieval_k=retrieval_k,
            retrieval_affect_weight=retrieval_affect_weight,
            planning_depth=planning_depth,
            tool_risk_tolerance=tool_risk_tolerance,
            salience_weight_overrides=salience_weight_overrides,
            tempo_hz=tempo_hz,
            speak_gate_open=speak_gate_open,
            tick_id=registers.tick_id,
        )
