"""Transcript-only control, per `docs/PlanBuildTEIC.md`: an LLM given the
same conversation history with no architectural state (no interoception, no
workspace, no self-model). Any Tier B result the control can match is flagged
as weak evidence -- verbal self-report is a dependent variable to cross-check,
not primary evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

from teic.models.probe import ProbeResult


@dataclass
class ControlComparison:
    probe_name: str
    primary_metric: float
    control_metric: float
    match_threshold: float

    @property
    def control_matches(self) -> bool:
        """True when the transcript-only control gets within
        `match_threshold` of the primary metric -- i.e. architectural state
        added no measurable signal over conversation history alone."""
        return abs(self.primary_metric - self.control_metric) <= self.match_threshold


def flag_weak_evidence(result: ProbeResult, comparison: ControlComparison, discount: float = 0.5) -> ProbeResult:
    """Returns a copy of `result` with `evidential_weight` discounted and a
    note appended when the transcript-only control matches the primary
    result -- the result still stands, but is marked as weak evidence rather
    than silently trusted."""
    if not comparison.control_matches:
        return result
    note = (
        f"transcript-only control matched primary result within "
        f"{comparison.match_threshold} -- flagged as weak evidence"
    )
    return result.model_copy(
        update={
            "evidential_weight": result.evidential_weight * discount,
            "notes": f"{result.notes}; {note}" if result.notes else note,
        }
    )
