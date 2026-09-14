"""TeicDaemon: the persistent process's task supervisor.

Phase 0: fixed-tempo heartbeat only, writes a `tick` row plus neutral
register/affect samples per cycle so the persistence + telemetry layers are
exercised end-to-end. No interoception inference, no workspace arbiter, no
LLM calls yet -- those arrive in later phases per PLAN.md's build order.

Phase 1: `register_sample` rows now carry real sensed/inferred values via
`ChannelPipeline` (see `teic/interoception/channels.py`). `affect_sample`
stays a neutral placeholder -- affect dynamics/mood are Layer 2 work that
lands with the non-linguistic modulation gate in Phase 2, not this phase.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import aiosqlite

from teic.interoception.channels import ChannelPipeline
from teic.models.registers import REGISTER_CHANNELS
from teic.models.tick import TickContext
from teic.persistence.db import open_db
from teic.persistence.log_sink import LogSink
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat


class TeicDaemon:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._conn: aiosqlite.Connection | None = None
        self._log_sink: LogSink | None = None
        self._session_id: str = str(uuid.uuid4())
        self._heartbeat: Heartbeat | None = None
        self._channels: ChannelPipeline | None = None

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "daemon not started"
        return self._conn

    async def start(self) -> None:
        self._conn = await open_db(self._settings.daemon.db_path)
        self._log_sink = LogSink(self._conn)
        config_snapshot = self._settings.model_dump(mode="json", exclude={"openrouter_api_key"})
        await self._conn.execute(
            "INSERT INTO session (session_id, started_at, config_snapshot) VALUES (?, ?, ?)",
            (self._session_id, datetime.now(UTC).isoformat(), json.dumps(config_snapshot)),
        )
        await self._conn.commit()
        self._heartbeat = Heartbeat(
            tempo_hz=self._settings.daemon.base_tempo_hz,
            on_tick=self._on_tick,
        )
        self._channels = ChannelPipeline()

    async def stop(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.stop()
        if self._conn is not None:
            await self._conn.execute(
                "UPDATE session SET ended_at = ? WHERE session_id = ?",
                (datetime.now(UTC).isoformat(), self._session_id),
            )
            await self._conn.commit()
            await self._conn.close()
            self._conn = None

    async def run_n_ticks(self, n: int) -> None:
        assert self._heartbeat is not None, "call start() first"
        await self._heartbeat.run_n_ticks(n)

    async def run(self) -> None:
        assert self._heartbeat is not None, "call start() first"
        await self._heartbeat.run()

    async def _on_tick(self, tick_index: int, dt_real: float) -> None:
        assert self._conn is not None
        assert self._channels is not None
        now = datetime.now(UTC)
        tempo_hz = self._settings.daemon.base_tempo_hz
        cursor = await self._conn.execute(
            "INSERT INTO tick (session_id, tick_index, wall_ts, dt_real, dt_subjective, tempo_hz) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self._session_id, tick_index, now.isoformat(), dt_real, dt_real, tempo_hz),
        )
        tick_id = cursor.lastrowid
        assert tick_id is not None

        # Phase 1: real sensing + inference. No input task exists yet, so
        # idle_state/pending_input_count stay at their neutral defaults.
        tick_ctx = TickContext(
            session_id=self._session_id,
            tick_index=tick_index,
            wall_ts=now,
            dt_real=dt_real,
            dt_subjective=dt_real,
            tempo_hz=tempo_hz,
            idle_state=False,
            pending_input_count=0,
        )
        register_state = self._channels.process(tick_ctx, tick_id, now)
        raw = self._channels.last_raw
        assert raw is not None
        for channel in REGISTER_CHANNELS:
            await self._conn.execute(
                "INSERT INTO register_sample (tick_id, channel, raw_value, inferred_value, inferred_var, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tick_id,
                    channel,
                    getattr(raw, channel),
                    getattr(register_state, channel),
                    register_state.variances[channel],
                    now.isoformat(),
                ),
            )
        await self._conn.execute(
            "INSERT INTO affect_sample (tick_id, valence, arousal, mood, attractor_label, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (tick_id, 0.0, 0.0, 0.0, "neutral", now.isoformat()),
        )
        await self._conn.commit()
