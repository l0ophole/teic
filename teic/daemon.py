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

Phase 3: `prediction_error` now flows from a real `ForwardModel`/
`ProtentionBuffer` pair instead of the flat `0.0` placeholder Phases 0-2
wrote. Each tick, before its own sensing, `_on_tick` pops the prediction
made at the end of the *previous* tick (if any) and resolves it against
what actually happened (this tick's `dt_real`) via `ForwardModel.observe()`,
producing the `prediction_error` fed into this tick's `ChannelPipeline`.
Then, after this tick's own processing, it predicts the *next* tick's
`dt_real` via `ForwardModel.predict_dt_real()` and pushes a new
`ProtentionEntry` (carrying that prediction plus a naive one-step
carry-forward of this tick's register vector) for the next tick to resolve.
This still isn't a real effector-latency forward model -- tick timing
stands in for it, since no LLM/tool call exists yet to have latency of its
own -- that's Phase 5+.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime

import aiosqlite

from teic.embodiment.forward_model import ForwardModel
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
from teic.temporal.protention import ProtentionBuffer, ProtentionEntry


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
        self._forward_model: ForwardModel | None = None
        self._protention: ProtentionBuffer | None = None
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
        self._forward_model = ForwardModel()
        self._protention = ProtentionBuffer()

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
        assert self._forward_model is not None
        assert self._protention is not None
        now = datetime.now(UTC)
        tempo_hz = self._current_tempo_hz

        # Phase 3: resolve last tick's prediction (if any) against what
        # actually happened this tick, before this tick's own sensing.
        pending = self._protention.pop()
        if pending is not None:
            nominal_dt = 1.0 / tempo_hz
            prediction_error = self._forward_model.observe(
                dt_real, nominal_dt, pending.predicted_dt_real
            )
        else:
            prediction_error = 0.0

        cursor = await self._conn.execute(
            "INSERT INTO tick (session_id, tick_index, wall_ts, dt_real, dt_subjective, tempo_hz) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (self._session_id, tick_index, now.isoformat(), dt_real, dt_real, tempo_hz),
        )
        tick_id = cursor.lastrowid
        assert tick_id is not None

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
        register_state = self._channels.process(
            tick_ctx, tick_id, now, prediction_error=prediction_error
        )
        raw = self._channels.last_raw
        assert raw is not None
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

        # Phase 3: predict the *next* tick's dt_real (using the tempo
        # that will actually be in effect for it) and interoceptive
        # vector, for next tick's _on_tick to resolve.
        next_nominal_dt = 1.0 / modulation_params.tempo_hz
        predicted_dt_real = self._forward_model.predict_dt_real(next_nominal_dt)
        self._protention.push(
            ProtentionEntry(
                made_at_tick_id=tick_id,
                predicted_at=now,
                predicted_dt_real=predicted_dt_real,
                predicted_registers=register_state.as_dict(),
            )
        )
        self._current_tempo_hz = modulation_params.tempo_hz
