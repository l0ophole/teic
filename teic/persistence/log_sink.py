from __future__ import annotations

import json
from pathlib import Path

import aiosqlite

from teic.models.log_event import LogEvent


class LogSink:
    """Writes LogEvent rows into the log_event table (the structured
    JSON-lines log layer the telemetry-reading assessment harness reads from),
    and can export a session's rows as newline-delimited JSON on demand."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._conn = conn

    async def emit(self, event: LogEvent) -> None:
        await self._conn.execute(
            "INSERT INTO log_event (session_id, tick_id, ts, level, subsystem, event_type, payload) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                event.session_id,
                event.tick_id,
                event.ts.isoformat(),
                event.level,
                event.subsystem,
                event.event_type,
                json.dumps(event.payload),
            ),
        )
        await self._conn.commit()

    async def export_jsonl(self, session_id: str, out_path: str | Path) -> int:
        """Dump a session's log_event rows as newline-delimited JSON. Returns row count."""
        cursor = await self._conn.execute(
            "SELECT session_id, tick_id, ts, level, subsystem, event_type, payload "
            "FROM log_event WHERE session_id = ? ORDER BY log_id",
            (session_id,),
        )
        rows = await cursor.fetchall()
        path = Path(out_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w") as f:
            for row in rows:
                session_id_, tick_id, ts, level, subsystem, event_type, payload = row
                record = {
                    "session_id": session_id_,
                    "tick_id": tick_id,
                    "ts": ts,
                    "level": level,
                    "subsystem": subsystem,
                    "event_type": event_type,
                    "payload": json.loads(payload),
                }
                f.write(json.dumps(record) + "\n")
        return len(rows)
