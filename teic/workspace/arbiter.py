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

BASE_IGNITION_THRESHOLD = 0.5
AROUSAL_GAIN = 0.3
MOOD_GAIN = 0.1
MIN_IGNITION_THRESHOLD = 0.05
MAX_IGNITION_THRESHOLD = 1.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def ignition_threshold(affect: AffectState, mood: float) -> float:
    return _clamp(
        BASE_IGNITION_THRESHOLD - affect.arousal * AROUSAL_GAIN - mood * MOOD_GAIN,
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
