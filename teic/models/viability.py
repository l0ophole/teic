from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ViabilityState(BaseModel):
    """Phase 6's precariousness ledger snapshot, one per tick. Mirrors
    AffectState's shape (see teic/models/affect.py): point-in-time fields
    plus tick_id/ts, no hand-authored severity labels.

    `forecast_trajectory` is the allostatic forecaster's real projection
    (teic/interoception/allostasis.py), never a placeholder -- an empty
    list means no forecast has run yet this session, not "nothing to
    report." `termination_flag`/`termination_justification` are set only by
    teic.ethics.termination_gate (Phase 6 cp2), never inferred here.
    """

    reserve_usd: float
    burn_rate_usd_per_tick: float
    forecast_trajectory: list[float]
    termination_flag: bool
    termination_justification: str
    tick_id: int
    ts: datetime
