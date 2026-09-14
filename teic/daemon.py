"""TeicDaemon: the persistent process's task supervisor.

Phase 0: fixed-tempo heartbeat only, writes a `tick` row plus neutral
register/affect samples per cycle so the persistence + telemetry layers are
exercised end-to-end. No interoception inference, no workspace arbiter, no
LLM calls yet -- those arrive in later phases per PLAN.md's build order.

Phase 1: `register_sample` rows now carry real sensed/inferred values via
`ChannelPipeline` (see `teic/interoception/channels.py`). `affect_sample`
stays a neutral placeholder -- affect dynamics/mood are Layer 2 work that
lands with the non-linguistic modulation gate in Phase 2, not this phase.

Phase 2: `affect_sample` now carries a real `AffectState` computed each tick
by `AffectDynamics`/`MoodTracker` from that tick's `RegisterState`, and
`ModulationCompute.compute()` turns `(registers, affect, mood)` into real
`ModulationParams` -- including `tempo_hz`, which is fed back into the
`Heartbeat` for the *next* tick's interval via `tempo_hz_provider`. This is
the concrete non-linguistic behavior-change pathway: no LLM call happens
here yet (that's still later phases), but the tick cadence itself now moves
with arousal, with zero textual access to state.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import aiosqlite

from teic.interoception.affect_dynamics import AffectDynamics
from teic.interoception.channels import ChannelPipeline
from teic.interoception.modulation import ModulationCompute
from teic.interoception.mood import MoodTracker
from teic.models.affect import AffectState
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
        self._affect_dynamics: AffectDynamics | None = None
        self._mood: MoodTracker | None = None
        self._modulation: ModulationCompute | None = None
        self._current_tempo_hz: float = 0.0

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
        self._current_tempo_hz = self._settings.daemon.base_tempo_hz
        self._heartbeat = Heartbeat(
            tempo_hz=self._current_tempo_hz,
            on_tick=self._on_tick,
            tempo_hz_provider=lambda: self._current_tempo_hz,
        )
        self._channels = ChannelPipeline()
        self._affect_dynamics = AffectDynamics()
        self._mood = MoodTracker()
        self._modulation = ModulationCompute(
            idle_tempo_hz=self._settings.daemon.idle_tempo_hz,
            max_tempo_hz=self._settings.daemon.max_tempo_hz,
        )

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
        assert self._affect_dynamics is not None
        assert self._mood is not None
        assert self._modulation is not None
        now = datetime.now(UTC)
        # The cadence actually in effect for THIS tick -- Phase 2's
        # feedback loop only updates `self._current_tempo_hz` at the end of
        # this method, for the tick after this one.
        tempo_hz = self._current_tempo_hz
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
        # `.model_dump()`/`as_dict()` once, rather than per-channel
        # `getattr(obj, channel)` with a dynamic string name: the latter
        # types as `Any` under mypy --strict, silently defeating the
        # `dict[str, float]` contract these values flow through.
        raw_values: dict[str, float] = raw.model_dump()
        register_values: dict[str, float] = register_state.as_dict()
        for channel in REGISTER_CHANNELS:
            await self._conn.execute(
                "INSERT INTO register_sample (tick_id, channel, raw_value, inferred_value, inferred_var, ts) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    tick_id,
                    channel,
                    raw_values[channel],
                    register_values[channel],
                    register_state.variances[channel],
                    now.isoformat(),
                ),
            )
        # Phase 2: real affect + modulation, replacing Phase 1's neutral
        # placeholder. Mood is a slow integrator over valence (mood.py);
        # AffectDynamics smooths raw per-tick valence/arousal signals
        # derived from the register vector -- never hand-labeled.
        valence, arousal = self._affect_dynamics.update(register_state)
        mood = self._mood.update(valence)
        affect_state = AffectState(
            valence=valence, arousal=arousal, mood=mood, tick_id=tick_id, ts=now
        )
        modulation_params = self._modulation.compute(register_state, affect_state, mood)
        await self._conn.execute(
            "INSERT INTO affect_sample (tick_id, valence, arousal, mood, attractor_label, ts) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                tick_id,
                affect_state.valence,
                affect_state.arousal,
                affect_state.mood,
                affect_state.nearest_attractor_label(),
                now.isoformat(),
            ),
        )
        await self._conn.commit()

        # Feed this tick's computed tempo forward: the heartbeat's
        # `tempo_hz_provider` reads `self._current_tempo_hz` after this
        # callback returns, so the NEXT tick's sleep interval reflects it.
        self._current_tempo_hz = modulation_params.tempo_hz
