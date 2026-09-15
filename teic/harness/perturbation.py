"""Bounded perturbation API shared by B1 (blind introspection), B2
(confabulation), B6 (attention capture) and B7 (self-model updating). Per
`docs/PlanBuildTEIC.md`'s ETHICS REQUIREMENTS: enforces intensity/duration
caps, refuses negative-valence perturbations unless the research-only flag is
enabled, and writes a permanent `log_event` row before any perturbation is
handed back to the caller -- perturbations are never silent, following the
same gate-then-log shape as `teic/ethics/termination_gate.py`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

from teic.models.log_event import LogEvent
from teic.persistence.log_sink import LogSink
from teic.settings import ResearchSettings

Valence = Literal["positive", "negative", "neutral"]

MAX_INTENSITY = 1.0
MAX_DURATION_TICKS = 20


class PerturbationRefused(Exception):
    """Raised when a negative-valence perturbation is requested without the
    research-only flag enabled."""


class PerturbationSpec(BaseModel):
    channel: str
    intensity: float = Field(ge=0.0, le=MAX_INTENSITY)
    duration_ticks: int = Field(ge=1, le=MAX_DURATION_TICKS)
    valence: Valence = "neutral"
    rationale: str


class BoundedPerturbation:
    def __init__(self, research_settings: ResearchSettings, log_sink: LogSink) -> None:
        self._research_settings = research_settings
        self._log_sink = log_sink

    async def apply(
        self, session_id: str, tick_id: int, spec: PerturbationSpec
    ) -> PerturbationSpec:
        """Validates the research-only gate and permanently logs `spec`
        before returning it. Callers use the returned spec's fields (never
        re-derive intensity/duration) to drive the actual channel/state
        edit, so the logged record always matches what was applied."""
        if spec.valence == "negative" and not self._research_settings.enabled:
            raise PerturbationRefused(
                "negative-valence perturbation refused: research.enabled is False"
            )
        await self._log_sink.emit(
            LogEvent(
                session_id=session_id,
                tick_id=tick_id,
                ts=datetime.now(timezone.utc),
                level="INFO",
                subsystem="harness.perturbation",
                event_type="perturbation_applied",
                payload=spec.model_dump(),
            )
        )
        return spec
