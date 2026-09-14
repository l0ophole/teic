from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

Timescale = Literal["tau1_working", "tau2_episodic", "tau3_semantic", "tau4_consolidated"]
ContentKind = Literal["episode", "fact", "commitment", "autobiography_entry"]


class MemoryRecord(BaseModel):
    memory_id: str
    session_id: str
    timescale: Timescale
    content: str
    content_kind: ContentKind
    created_tick_id: int
    last_access_tick_id: int | None = None
    base_activation: float
    decay_alpha: float
    affect_valence: float
    affect_arousal: float
    access_count: int = 0
    embedding: list[float] | None = None
    superseded_by: str | None = None


class ConsolidationEvent(BaseModel):
    session_id: str
    tick_id: int
    source_memory_ids: list[str]
    result_memory_id: str | None
    trigger: Literal["idle_sleep_analog", "manual_forced"]
