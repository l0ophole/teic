"""Phase 9 cp2: unfiltered scrolling tail of `log_event` rows.

v1 log surface decision (`phase9-plan.md`): simple unfiltered tail, no
filtering/search/replay. Reads the existing `log_event` table via the
daemon's own connection -- no new schema, no separate write path; this
widget only tails what `LogSink.emit()` (invoked from `teic/daemon.py`)
already persists.
"""

from __future__ import annotations

import json

import aiosqlite
from textual.widgets import RichLog

_LEVEL_STYLE = {"ERROR": "bold red", "WARN": "yellow", "INFO": "dim"}


class LogView(RichLog):
    def __init__(self, max_rows: int, **kwargs: object) -> None:
        super().__init__(max_lines=max_rows, wrap=False, markup=True, **kwargs)
        self._last_log_id = 0

    async def poll(self, conn: aiosqlite.Connection, session_id: str) -> None:
        """Appends any `log_event` rows written since the last poll. Called
        on a fixed timer from `TeicApp` rather than per-tick, since log
        events (LLM failures, termination-gate fires) don't happen every
        tick and per-tick polling would be wasted work most ticks."""
        cursor = await conn.execute(
            "SELECT log_id, tick_id, level, subsystem, event_type, payload FROM log_event "
            "WHERE session_id = ? AND log_id > ? ORDER BY log_id",
            (session_id, self._last_log_id),
        )
        rows = await cursor.fetchall()
        for log_id, tick_id, level, subsystem, event_type, payload in rows:
            style = _LEVEL_STYLE.get(level, "")
            tick_label = f"t{tick_id}" if tick_id is not None else "-"
            self.write(
                f"[{style}]{level:5}[/{style}] {tick_label} {subsystem}.{event_type} "
                f"{json.loads(payload)}"
            )
            self._last_log_id = log_id

    def reset(self) -> None:
        self._last_log_id = 0
        self.clear()
