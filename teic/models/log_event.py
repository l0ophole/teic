from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel

LogLevel = Literal["DEBUG", "INFO", "WARN", "ERROR"]


class LogEvent(BaseModel):
    """Structured telemetry record. Rows in the `log_event` table ARE the
    structured JSON-lines log the spec requires; `teic export-logs` dumps them
    as newline-delimited JSON on demand."""

    log_id: int | None = None
    session_id: str
    tick_id: int | None
    ts: datetime
    level: LogLevel
    subsystem: str
    event_type: str
    payload: dict[str, Any]
