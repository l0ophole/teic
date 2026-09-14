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

Phase 4: `_on_tick` now writes one real `tau1_working`/`episode`
`memory_record` per tick via `MemoryStore.create()`, content = a compact
text serialization of that tick's `RegisterState`/`AffectState`. This is
real, non-fabricated data, but it is explicitly **not** "the agent
remembering a conversation" -- there is still no workspace arbiter (Phase 5)
producing real broadcast content worth remembering, so this is the same
honest-proxy-content pattern Phase 1's sensors and Phase 3's forward model
established for their own layers. `run()` (not `run_n_ticks()`, which every
prior gate test drives directly and which stays synchronous/unmodified)
also starts a background wall-clock-idle-gated consolidation loop
(`teic/memory/consolidation.py`) that periodically checks whether enough
real time has passed since the last tick and, if so, structurally merges
(not LLM-summarizes -- no cognition loop exists yet either) stale
low-activation memories into a `tau4_consolidated` record.

Phase 5: `_on_tick` now collects this tick's real
`WorkspaceCandidate`s -- one always from `"interoception"` (this tick's own
`RegisterState`/`AffectState`, the same data Phase 4 serializes into
memory) and, when the (now-prior) `memory_record` table isn't empty, one
from `"memory"` (the top result of a real `MemoryStore.query()` run
*before* this tick's own memory write, so it can't trivially match
itself) -- and arbitrates them via `WorkspaceArbiter.select()`, persisting
one `workspace_broadcast` row per tick regardless of whether the winner
ignited. Ignition never gates the Phase 4 memory write -- that's real
interoceptive data, not broadcast content, so it keeps flowing either way.
Every candidate's salience (not just the winner's, and regardless of
`ignited`) feeds `arbiter.salience_overrides()` into *next* tick's
`ModulationCompute.compute(..., prior_salience_overrides=...)` -- the
"sub-threshold candidate still modulates" pathway this phase's gate tests.
No real OpenRouter call happens on `ignited=True` yet: `llm/client.py`/
`llm/prompt_assembly.py` exist and `workspace/broadcast.py`'s
`render_prompt_if_ignited()` is the real enforcement seam, but actually
spending budget needs Phase 6's viability accounting to gate it first.
The interoception candidate's `goal_relevance` uses a fixed baseline
(`INTEROCEPTION_GOAL_RELEVANCE_BASELINE`), not `RegisterState.goal_gradient`
-- that channel is a perpetual `0.0` placeholder until real goal
representation exists (self-model/Phase 7+; see `embodiment/sensors.py`),
and multiplying salience by an always-zero term would zero it in every
real run.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from datetime import UTC, datetime

import aiosqlite

from teic.embodiment.forward_model import ForwardModel
from teic.interoception.affect_dynamics import AffectDynamics
from teic.interoception.channels import ChannelPipeline
from teic.interoception.modulation import ModulationCompute
from teic.interoception.mood import MoodTracker
from teic.memory import vector_index
from teic.memory.consolidation import IDLE_THRESHOLD_S, run_consolidation_pass
from teic.memory.embeddings import get_default_model
from teic.memory.store import MemoryStore
from teic.models.affect import AffectState
from teic.models.registers import REGISTER_CHANNELS
from teic.models.tick import TickContext
from teic.models.workspace import WorkspaceCandidate
from teic.persistence.db import open_db
from teic.persistence.log_sink import LogSink
from teic.settings import Settings
from teic.temporal.heartbeat import Heartbeat
from teic.temporal.protention import ProtentionBuffer, ProtentionEntry
from teic.workspace.arbiter import WorkspaceArbiter, salience_overrides

# How often the background consolidation loop checks wall-clock idle time.
CONSOLIDATION_POLL_INTERVAL_S = 5.0

# Phase 5 scope ruling 5: `RegisterState.goal_gradient` is a perpetually
# 0.0 placeholder (see embodiment/sensors.py's own comment) until real goal
# representation exists (self-model/Phase 7+) -- gating the interoception
# candidate's goal_relevance on it would zero its salience in every real
# run. Use a fixed baseline instead, same honest-baseline pattern as the
# "memory" candidate's own fixed goal_relevance below.
INTEROCEPTION_GOAL_RELEVANCE_BASELINE = 0.5


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


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
        self._memory_store: MemoryStore | None = None
        self._last_tick_wall_ts: float | None = None
        self._latest_tick_id: int | None = None
        self._arbiter: WorkspaceArbiter | None = None
        self._prior_salience_overrides: dict[str, float] | None = None

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
        self._arbiter = WorkspaceArbiter()
        self._protention = ProtentionBuffer()
        await vector_index.ensure_loaded(self._conn)
        await vector_index.ensure_table(self._conn)
        self._memory_store = MemoryStore(self._conn, get_default_model())

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
        """Runs the heartbeat plus a background wall-clock-idle-gated
        consolidation loop concurrently, for as long as the heartbeat runs.
        `run_n_ticks()` (used by every gate test) deliberately does **not**
        start this loop -- it stays synchronous/unmodified so no prior gate
        test's behavior changes."""
        assert self._heartbeat is not None, "call start() first"
        consolidation_task = asyncio.create_task(self._consolidation_loop())
        try:
            await self._heartbeat.run()
        finally:
            consolidation_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await consolidation_task

    async def _consolidation_loop(self) -> None:
        assert self._memory_store is not None
        while True:
            await asyncio.sleep(CONSOLIDATION_POLL_INTERVAL_S)
            if self._last_tick_wall_ts is None or self._latest_tick_id is None:
                continue
            idle_for = time.monotonic() - self._last_tick_wall_ts
            if idle_for >= IDLE_THRESHOLD_S:
                await run_consolidation_pass(
                    self._memory_store, self._session_id, self._latest_tick_id
                )

    async def _on_tick(self, tick_index: int, dt_real: float) -> None:
        assert self._conn is not None
        assert self._channels is not None
        assert self._affect_dynamics is not None
        assert self._mood is not None
        assert self._modulation is not None
        assert self._forward_model is not None
        assert self._protention is not None
        assert self._arbiter is not None
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
        modulation_params = self._modulation.compute(
            register_state, affect_state, mood,
            prior_salience_overrides=self._prior_salience_overrides,
        )
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

        # Phase 4: honest-proxy-content memory write -- see module
        # docstring's Phase 4 paragraph for why this is real interoceptive
        # data, not real cognition/broadcast content.
        assert self._memory_store is not None
        content = f"tick {tick_id}: valence={affect_state.valence:.3f} arousal={affect_state.arousal:.3f} " + " ".join(
            f"{channel}={value:.3f}" for channel, value in register_values.items()
        )

        # Phase 5: collect this tick's real candidates, arbitrate, persist
        # the broadcast, and fold every candidate's salience forward into
        # next tick's ModulationParams -- see phase5-plan.md scope ruling 1.
        # This must run before this tick's own memory write below, so the
        # "memory" candidate (if any) can't trivially match itself.
        mean_variance = sum(register_state.variances.values()) / len(register_state.variances)
        interoception_candidate = WorkspaceCandidate(
            source_module="interoception",
            content={"registers": register_values, "tick_id": tick_id},
            novelty=_clamp01(prediction_error),
            # EWMA variance is unbounded (a noisy channel like latency_strain
            # can spike its variance well past 1.0), so `1 - mean_variance`
            # would hard-clamp to 0 precisely when things are noisiest --
            # backwards for a confidence signal. 1/(1+var) saturates toward
            # 0 as variance grows without ever needing a clamp to do it.
            precision=1.0 / (1.0 + mean_variance),
            affective_weight=_clamp01((abs(affect_state.valence) + affect_state.arousal) / 2.0),
            goal_relevance=INTEROCEPTION_GOAL_RELEVANCE_BASELINE,
        )
        candidates = [interoception_candidate]
        memory_results = await self._memory_store.query(
            session_id=self._session_id,
            query_text=content,
            current_tick_id=tick_id,
            current_valence=affect_state.valence,
            current_arousal=affect_state.arousal,
            retrieval_affect_weight=modulation_params.retrieval_affect_weight,
            retrieval_k=1,
        )
        if memory_results:
            top = memory_results[0]
            candidates.append(
                WorkspaceCandidate(
                    source_module="memory",
                    content={"memory_id": top.record.memory_id, "content": top.record.content},
                    novelty=_clamp01(1.0 - top.activation_value),
                    precision=_clamp01(top.semantic_match),
                    affective_weight=_clamp01(abs(top.record.affect_valence)),
                    goal_relevance=0.3,
                )
            )
        broadcast = self._arbiter.select(candidates, affect_state, mood, tick_id)
        await self._conn.execute(
            "INSERT INTO workspace_broadcast (broadcast_id, tick_id, winner_source, salience_score, "
            "novelty, precision_w, affective_w, goal_relevance, ignited, content, mineness_tag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                broadcast.broadcast_id, tick_id, broadcast.winner.source_module,
                broadcast.winner.salience, broadcast.winner.novelty, broadcast.winner.precision,
                broadcast.winner.affective_weight, broadcast.winner.goal_relevance,
                int(broadcast.ignited), json.dumps(broadcast.winner.content), broadcast.mineness_tag,
            ),
        )
        await self._conn.commit()
        self._prior_salience_overrides = salience_overrides(candidates, broadcast.winner)

        await self._memory_store.create(
            session_id=self._session_id,
            timescale="tau1_working",
            content=content,
            content_kind="episode",
            created_tick_id=tick_id,
            base_activation=1.0,
            decay_alpha=0.5,
            affect_valence=affect_state.valence,
            affect_arousal=affect_state.arousal,
        )
        self._last_tick_wall_ts = time.monotonic()
        self._latest_tick_id = tick_id

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
