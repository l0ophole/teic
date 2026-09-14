from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TickContext(BaseModel):
    """Identity and timing of a single cognitive cycle."""

    session_id: str
    tick_index: int
    wall_ts: datetime
    dt_real: float
    dt_subjective: float
    tempo_hz: float
    idle_state: bool
    pending_input_count: int
