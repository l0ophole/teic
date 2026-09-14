from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class WorkspaceCandidate(BaseModel):
    """One module's bid for the current cognitive cycle's broadcast slot."""

    source_module: str
    content: dict[str, Any]
    novelty: float
    precision: float
    affective_weight: float
    goal_relevance: float

    @property
    def salience(self) -> float:
        return self.novelty * self.precision * self.affective_weight * self.goal_relevance


class WorkspaceBroadcast(BaseModel):
    """The arbiter's decision for one tick: at most one winner, tagged and logged
    regardless of whether it crossed the ignition threshold."""

    broadcast_id: str
    tick_id: int
    winner: WorkspaceCandidate
    ignited: bool
    mineness_tag: Literal["self", "other", "ambiguous"]
    ts: datetime
