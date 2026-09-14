"""Workspace arbiter -- Phase 5, PLAN.md's "Workspace Arbiter" section.

salience = novelty * precision * affective_weight * goal_relevance (already
a property on WorkspaceCandidate). One winner per cycle via max(). ignited
= winner.salience >= ignition_threshold(affect, mood). Sub-threshold
winners are still returned (ignited=0) -- see this module's `select()` --
and their salience (and every other candidate's) still feeds
`salience_overrides()`, which daemon.py folds into the *next* tick's
ModulationParams.salience_weight_overrides. That dual property (always
modulates, only sometimes broadcasts) is this phase's gate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from teic.models.affect import AffectState
from teic.models.workspace import WorkspaceBroadcast, WorkspaceCandidate
from teic.workspace.mineness import mineness_tag

# Calibrated empirically (same posture as Phase 3's N_BASELINE tuning):
# with the real candidate sources daemon.py builds, salience realistically
# lands in the 0.0 (idle) to ~0.2 (sustained high-arousal jitter) range --
# see phase5-plan.md scope ruling 4's verification numbers. These constants
# are chosen so idle runs never ignite (salience stays at exactly 0.0, well
# under any positive threshold) while sustained real stress reliably does.
BASE_IGNITION_THRESHOLD = 0.3
AROUSAL_GAIN = 0.2
MOOD_GAIN = 0.05
MIN_IGNITION_THRESHOLD = 0.05
MAX_IGNITION_THRESHOLD = 1.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def ignition_threshold(affect: AffectState, mood: float) -> float:
    # Mirrors modulation.py's `max(0.0, -mood)` idiom for "only negative
    # mood matters" effects: a bad mood lowers the bar, a good mood doesn't
    # raise it above the arousal-only baseline.
    return _clamp(
        BASE_IGNITION_THRESHOLD
        - affect.arousal * AROUSAL_GAIN
        - max(0.0, -mood) * MOOD_GAIN,
        MIN_IGNITION_THRESHOLD,
        MAX_IGNITION_THRESHOLD,
    )


def salience_overrides(
    candidates: list[WorkspaceCandidate], winner: WorkspaceCandidate
) -> dict[str, float]:
    """Every candidate this tick (winner included) up-weights its own
    source_module for next tick's arbiter competition, proportional to how
    close it came to winning. This is the "sub-threshold candidate
    demonstrably modulates" pathway -- it runs regardless of `ignited`."""
    return {c.source_module: 1.0 + c.salience for c in candidates}


class WorkspaceArbiter:
    def select(
        self,
        candidates: list[WorkspaceCandidate],
        affect: AffectState,
        mood: float,
        tick_id: int,
    ) -> WorkspaceBroadcast:
        if not candidates:
            raise ValueError("WorkspaceArbiter.select() requires at least one candidate")
        winner = max(candidates, key=lambda c: c.salience)
        ignited = winner.salience >= ignition_threshold(affect, mood)
        return WorkspaceBroadcast(
            broadcast_id=str(uuid.uuid4()),
            tick_id=tick_id,
            winner=winner,
            ignited=ignited,
            mineness_tag=mineness_tag(winner),
            ts=datetime.now(UTC),
        )
