"""Reportability gate -- Phase 2's narrow scope, composed with Phase 7.

`docs/PlanBuildTEIC.md` lists a full "reportability gate" under Phase 7
(self-model, metacognition, confidence calibration). `PLAN.md`'s own Build
Order table nonetheless names `reportability.py` in Phase 2, because
`ModulationCompute.compute()` needs a real `speak_gate_open` value now, not a
decorative fixed one. Phase 2 scoped this narrowly: a cooldown-gated
threshold on `epistemic_tension` alone.

Phase 7 composes two more real signals onto that base gate rather than
replacing it: workspace ignition (Phase 5 -- ignited content is a second,
independent path to opening the gate) and self-model confidence (Phase 7 --
gates that second path, since ignited-but-uncertain content should prompt
more info-seeking, not speech; see `teic.selfmodel.metacognition`). The
original `epistemic_tension` threshold path is unchanged and does not
require confidence.
"""

from __future__ import annotations

SPEAK_GATE_EPISTEMIC_THRESHOLD = 0.3
IGNITION_CONFIDENCE_THRESHOLD = 0.6
REFRACTORY_TICKS = 5


class ReportabilityGate:
    """Per-session cooldown-gated threshold gate."""

    def __init__(self, refractory_ticks: int = REFRACTORY_TICKS) -> None:
        self._refractory_ticks = refractory_ticks
        # Ready immediately on session start, not "closed forever" by default.
        self._ticks_since_open = refractory_ticks

    def evaluate(
        self,
        epistemic_tension: float,
        *,
        ignited: bool = False,
        confidence: float | None = None,
    ) -> bool:
        cooldown_elapsed = self._ticks_since_open >= self._refractory_ticks
        epistemic_trigger = epistemic_tension >= SPEAK_GATE_EPISTEMIC_THRESHOLD
        ignition_trigger = (
            ignited and confidence is not None and confidence >= IGNITION_CONFIDENCE_THRESHOLD
        )
        should_open = cooldown_elapsed and (epistemic_trigger or ignition_trigger)
        if should_open:
            self._ticks_since_open = 0
        else:
            self._ticks_since_open += 1
        return should_open
