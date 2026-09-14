"""Reportability gate -- Phase 2's narrow scope only.

`docs/PlanBuildTEIC.md` lists a full "reportability gate" under Phase 7
(self-model, metacognition, confidence calibration). `PLAN.md`'s own Build
Order table nonetheless names `reportability.py` in Phase 2, because
`ModulationCompute.compute()` needs a real `speak_gate_open` value now, not a
decorative fixed one. This module resolves that by scoping narrowly: a
cooldown-gated threshold on `epistemic_tension` alone. It does **not** yet
incorporate workspace ignition (Phase 5) or self-model confidence (Phase 7)
-- those compose with this gate later; they don't replace it. Treat this as
an intentional partial wiring, documented here so it isn't mistaken for the
finished gate.
"""

from __future__ import annotations

SPEAK_GATE_EPISTEMIC_THRESHOLD = 0.3
REFRACTORY_TICKS = 5


class ReportabilityGate:
    """Per-session cooldown-gated threshold gate."""

    def __init__(self, refractory_ticks: int = REFRACTORY_TICKS) -> None:
        self._refractory_ticks = refractory_ticks
        # Ready immediately on session start, not "closed forever" by default.
        self._ticks_since_open = refractory_ticks

    def evaluate(self, epistemic_tension: float) -> bool:
        cooldown_elapsed = self._ticks_since_open >= self._refractory_ticks
        should_open = cooldown_elapsed and epistemic_tension >= SPEAK_GATE_EPISTEMIC_THRESHOLD
        if should_open:
            self._ticks_since_open = 0
        else:
            self._ticks_since_open += 1
        return should_open
