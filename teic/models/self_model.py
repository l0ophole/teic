from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SelfModel(BaseModel):
    """One module among many -- no privileged access, built from the same
    telemetry every other module sees. Must be causally efficacious: editing
    a field here must predictably change downstream behavior (verified at the
    Phase 7 gate)."""

    body: dict[str, Any]
    agency: float
    interoception_summary: dict[str, float]
    history_summary: str
    identity_traits: dict[str, float]
    mental_state_estimate: dict[str, Any]
    temporal_self: dict[str, Any]
    version: int
    last_edited_tick_id: int
