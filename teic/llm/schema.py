from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

CallStatus = Literal["ok", "timeout", "error", "retried"]


class LLMCallLog(BaseModel):
    """Per-call log record: model, prompt/response, token usage, cost, latency.
    Written to the llm_call_log table by the caller after each completion attempt."""

    call_id: str
    tick_id: int | None
    model: str
    fallback_used: bool = False
    prompt: str
    response: str | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    estimated_cost_usd: float | None = None
    latency_ms: int | None = None
    status: CallStatus
    error_detail: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
