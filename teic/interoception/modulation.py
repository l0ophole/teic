"""Non-linguistic modulation pathway -- Phase 2, the real gate.

`ModulationParams` is defined here now (Phase 0) as the shared data model that
`llm/prompt_assembly.py` depends on for its type-level enforcement boundary.
`ModulationCompute.compute()` is a placeholder until Phase 2: it must be
replaced with the concrete register-driven wiring described in PLAN.md
("Non-Linguistic Modulation Pathway") before Phase 2's gate test can pass.
"""

from __future__ import annotations

from pydantic import BaseModel

from teic.models.affect import AffectState
from teic.models.registers import RegisterState


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
    through every downstream call site. Not implemented until Phase 2 --
    raises to fail loudly rather than silently returning fixed/decorative
    values that would look like a working gate without being one."""

    def compute(
        self, registers: RegisterState, affect: AffectState, mood: float
    ) -> ModulationParams:
        raise NotImplementedError(
            "ModulationCompute.compute is a Phase 2 deliverable -- see PLAN.md "
            "'Non-Linguistic Modulation Pathway'. Do not stub this with fixed "
            "values; an unimplemented gate must fail loudly, not decoratively."
        )
