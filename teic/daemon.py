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

Phase 6: `_on_tick` now reads the real `ViabilityBudget` ledger's
`reserve_channel()`/`burn_rate_channel()` *before* this tick's own sensing
-- the same one-tick-lag pattern Phase 3 established for `prediction_error`,
since this tick's own spend/replenish outcome isn't known until after
arbitration. `AllostaticForecaster.anticipatory_pressure()` (sharing
`ChannelPipeline.inference`, not a forked model) runs right after that
sensing and, when positive, adds a real `"viability"` `WorkspaceCandidate`
to the arbitration pool -- the mechanism behind "regulation is visible as
agent behavior, not a background cron job." After arbitration,
`render_prompt_if_ignited()` (Phase 5's seam) is finally exercised: an
ignited broadcast's real assembled prompt is costed via
`teic.llm.cost.PricingCache.estimate_cost_usd()` and charged to the ledger
via `spend()` -- no network call is made (that integration stays out of
scope for this phase's task list), so only prompt tokens are charged, never
completion tokens. If the ignited winner is the `"viability"` candidate
itself, that is the one and only path that calls `replenish()` -- an
explicit, workspace-arbitrated effector action, not a silent top-up. If the
ledger's `reserve_usd` hits zero, `_on_tick` calls `TerminationGate.fire()`;
a refusal (unconfigured settings) is caught and logged nowhere further (the
gate itself writes nothing on refusal), while a successful fire sets
`self._terminated` and stops the heartbeat. `self._terminated` also makes
`_on_tick` a no-op on any further call, since `Heartbeat.run_n_ticks()`
(unlike `run()`) has no stop-event check of its own.

Phase 7: after this tick's memory query (so `history_summary` reuses the
same `MemoryStore.query()` results the "memory" workspace candidate reads,
rather than a second query), `_on_tick` builds this tick's real `SelfModel`
via `build_self_model()` from `register_state`/`affect_state`/
`prediction_error`/the prior `SelfModel` and computes `ConfidenceEstimate`
via `compute_confidence()`, persisting one `self_model` row per tick. Both
the confidence estimate and the tick's own `broadcast.ignited` outcome are
only known *after* this tick's own arbitration, so -- the same one-tick-lag
pattern Phase 3/5/6 established for `prediction_error`/
`salience_overrides`/`budget_reserve` -- they are stored on `self` and fed
into *next* tick's `ModulationCompute.compute(confidence=..., prior_ignited=...)`
call, not this tick's. Likewise, `identity_traits["goal_gradient"]` from this
tick's self-model is stored and passed into *next* tick's
`ChannelPipeline.process(goal_gradient=...)`, resolving `sensors.py`'s
former `0.0` placeholder into a real (one-tick-lagged) signal.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

import aiosqlite

from teic.embodiment.forward_model import ForwardModel
from teic.ethics.termination_gate import TerminationGate, TerminationRefused
from teic.interoception.affect_dynamics import AffectDynamics
from teic.interoception.allostasis import AllostaticForecaster
from teic.interoception.channels import ChannelPipeline
from teic.interoception.modulation import ModulationCompute
from teic.interoception.mood import MoodTracker
from teic.llm.client import ChatPrompt, OpenRouterClient
from teic.llm.cost import PricingCache
from teic.llm.schema import CallStatus, LLMCallLog
from teic.embodiment.viability_budget import ViabilityBudget
from teic.memory import vector_index
from teic.memory.consolidation import IDLE_THRESHOLD_S, run_consolidation_pass
from teic.memory.embeddings import get_default_model
from teic.memory.store import MemoryStore
from teic.models.affect import AffectState
from teic.models.metacognition import ConfidenceEstimate
from teic.models.registers import REGISTER_CHANNELS
from teic.models.self_model import SelfModel
from teic.models.log_event import LogEvent
from teic.models.tick import TickContext
from teic.models.workspace import WorkspaceCandidate
from teic.persistence.db import open_db
from teic.persistence.log_sink import LogSink
from teic.selfmodel.builder import build_self_model
from teic.selfmodel.metacognition import compute_confidence
from teic.settings import Settings
from teic.workspace.narrative_constructor import build_narrative_tail
from teic.temporal.heartbeat import Heartbeat
from teic.temporal.protention import ProtentionBuffer, ProtentionEntry
from teic.workspace.arbiter import WorkspaceArbiter, salience_overrides
from teic.workspace.broadcast import render_prompt_if_ignited

# How often the background consolidation loop checks wall-clock idle time.
CONSOLIDATION_POLL_INTERVAL_S = 5.0

# Phase 5 scope ruling 5: `RegisterState.goal_gradient` is a perpetually
# 0.0 placeholder (see embodiment/sensors.py's own comment) until real goal
# representation exists (self-model/Phase 7+) -- gating the interoception
# candidate's goal_relevance on it would zero its salience in every real
# run. Use a fixed baseline instead, same honest-baseline pattern as the
# "memory" candidate's own fixed goal_relevance below.
INTEROCEPTION_GOAL_RELEVANCE_BASELINE = 0.5

# Below this normalized budget_reserve value, the forecaster's anticipated
# crossing is treated as worth bidding into the workspace over. Matches the
# threshold exercised by the cp1 gate test
# (tests/test_gates/test_phase6.py::test_allostatic_forecast_raises_pressure_before_actual_violation).
VIABILITY_PRESSURE_THRESHOLD = 0.2

# The viability candidate's precision/affective_weight/goal_relevance are
# fixed at 1.0 (unlike the interoception/memory candidates' derived values)
# -- an anticipated resource crisis is not a noisy or partial signal the way
# sensed registers are, so salience reduces to `novelty == pressure` itself.
VIABILITY_GOAL_RELEVANCE_BASELINE = 1.0


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


@dataclass(frozen=True, slots=True)
class TickSnapshot:
    """Phase 9 cp2: the TUI status panel's real state source. One is built
    and dispatched to every registered listener at the end of each tick --
    the "prefer the existing on_tick callback pattern over polling" call
    from `phase9-plan.md`, mirroring `Heartbeat`'s own `on_tick` seam rather
    than having the UI poll the database."""

    tick_id: int
    valence: float
    arousal: float
    tempo_hz: float
    budget_reserve_usd: float
    ignited: bool
    winner_source: str
    pending_input_count: int


TickListener = Callable[[TickSnapshot], Awaitable[None]]
ResponseChunkHandler = Callable[[str], Awaitable[None]]


class TeicDaemon:
    def __init__(self, settings: Settings, llm_client: OpenRouterClient | None = None) -> None:
        self._settings = settings
        # Test-injectable seam (Phase 9 cp1): pass a fake/mock client to
        # exercise the real send path without a live network call. Left
        # `None` in production until `start()` builds a real one -- gated on
        # a configured API key so every pre-Phase-9 gate test (no key set in
        # `tests/conftest.py`'s `tmp_settings`) keeps ignited ticks
        # network-call-free without needing to inject anything itself.
        self._llm_client = llm_client
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
        self._viability_budget: ViabilityBudget | None = None
        self._allostasis: AllostaticForecaster | None = None
        self._termination_gate: TerminationGate | None = None
        self._pricing: PricingCache | None = None
        self._terminated: bool = False
        self._self_model: SelfModel | None = None
        self._confidence: ConfidenceEstimate | None = None
        self._prior_ignited: bool = False
        self._prior_goal_gradient: float = 0.0
        self._pending_user_messages: asyncio.Queue[str] = asyncio.Queue()
        self._current_tick_id: int | None = None
        # Phase 9 cp2: TUI observer seams.
        self._tick_listeners: list[TickListener] = []
        self._on_response_chunk: ResponseChunkHandler | None = None

    async def submit_user_message(self, text: str) -> None:
        """The real "user can chat" input seam: queued here, drained one per
        tick by `_on_tick` into a `user_message` `WorkspaceCandidate` -- the
        first ever externally-sourced candidate, the rest all being
        internally generated (interoception/memory/viability)."""
        await self._pending_user_messages.put(text)

    def add_tick_listener(self, listener: TickListener) -> None:
        """Registers a callback invoked with a `TickSnapshot` at the end of
        every tick -- the TUI status panel's update source."""
        self._tick_listeners.append(listener)

    def remove_tick_listener(self, listener: TickListener) -> None:
        self._tick_listeners.remove(listener)

    def set_response_chunk_handler(self, handler: ResponseChunkHandler | None) -> None:
        """Wires a real per-chunk callback into `_handle_ignited_prompt`'s
        `ChatClient.stream()` loop -- the TUI chat pane's token-by-token
        streaming source, as opposed to `TickSnapshot`, which only carries
        end-of-tick summary state."""
        self._on_response_chunk = handler

    def pause(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.pause()

    def resume(self) -> None:
        if self._heartbeat is not None:
            self._heartbeat.resume()

    @property
    def paused(self) -> bool:
        return self._heartbeat.paused if self._heartbeat is not None else False

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def conn(self) -> aiosqlite.Connection:
        assert self._conn is not None, "daemon not started"
        return self._conn

    @property
    def is_running(self) -> bool:
        return self._conn is not None

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
        self._viability_budget = ViabilityBudget(self._settings.viability)
        self._allostasis = AllostaticForecaster(
            self._channels.inference, horizon_ticks=self._settings.viability.forecast_horizon_ticks
        )
        assert self._log_sink is not None
        self._termination_gate = TerminationGate(self._settings.viability, self._log_sink)
        self._pricing = PricingCache()
        self._pricing.load_from_disk()
        api_key = self._settings.openrouter_api_key.get_secret_value()
        if self._llm_client is None and api_key:
            self._llm_client = OpenRouterClient(
                api_key=api_key,
                primary_model=self._settings.llm.primary_model,
                fallback_model=self._settings.llm.fallback_model,
                base_url=self._settings.llm.base_url,
                request_timeout_s=self._settings.llm.request_timeout_s,
                max_retries=self._settings.llm.max_retries,
                backoff_base_s=self._settings.llm.backoff_base_s,
                on_failure=self._on_llm_failure,
            )
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

    async def _on_llm_failure(self, reason: str) -> None:
        """`OpenRouterClient`'s `on_failure` hook: surfaces a send failure
        as a permanent log record rather than a bare exception -- this is
        the "LLM failure must surface as interoceptive strain... never a
        crash" contract from `teic/llm/client.py`'s own module docstring."""
        assert self._log_sink is not None
        await self._log_sink.emit(
            LogEvent(
                session_id=self._session_id,
                tick_id=self._current_tick_id,
                level="WARN",
                subsystem="llm",
                event_type=f"failure:{reason}",
                payload={},
                ts=datetime.now(UTC),
            )
        )

    async def _handle_ignited_prompt(self, prompt: ChatPrompt, tick_id: int) -> float:
        """Real send-and-cost path for an ignited broadcast's rendered
        prompt. Falls back to Phase 6's prompt-tokens-only estimate (no
        network call) whenever no client is available -- production
        without a configured API key, and every pre-Phase-9 gate test,
        which injects nothing and sets no key (see `start()`)."""
        assert self._pricing is not None
        assert self._viability_budget is not None
        prompt_tokens = sum(len(m["content"]) for m in prompt.messages) // 4
        if self._llm_client is None:
            return self._pricing.estimate_cost_usd(
                self._settings.llm.primary_model, prompt_tokens, completion_tokens=0
            )
        started_at = datetime.now(UTC)
        response_text = ""
        status: CallStatus = "ok"
        error_detail: str | None = None
        try:
            async for chunk in self._llm_client.stream(prompt):
                response_text += chunk
                if self._on_response_chunk is not None:
                    await self._on_response_chunk(chunk)
        except Exception as exc:  # noqa: BLE001 - any send failure must degrade, never crash the tick
            status = "error"
            error_detail = str(exc)
            assert self._log_sink is not None
            await self._log_sink.emit(
                LogEvent(
                    session_id=self._session_id,
                    tick_id=tick_id,
                    level="ERROR",
                    subsystem="llm",
                    event_type="send_failed",
                    payload={"error": error_detail},
                    ts=datetime.now(UTC),
                )
            )
        finished_at = datetime.now(UTC)
        completion_tokens = len(response_text) // 4
        cost_usd = self._pricing.estimate_cost_usd(
            self._settings.llm.primary_model, prompt_tokens, completion_tokens
        )
        latency_ms = int((finished_at - started_at).total_seconds() * 1000)
        assert self._conn is not None
        call_log = LLMCallLog(
            call_id=str(uuid.uuid4()),
            tick_id=tick_id,
            model=self._settings.llm.primary_model,
            fallback_used=False,
            prompt=json.dumps(prompt.messages),
            response=response_text,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            estimated_cost_usd=cost_usd,
            latency_ms=latency_ms,
            status=status,
            error_detail=error_detail,
            started_at=started_at,
            finished_at=finished_at,
        )
        await self._conn.execute(
            "INSERT INTO llm_call_log (call_id, tick_id, model, fallback_used, prompt, response, "
            "prompt_tokens, completion_tokens, estimated_cost_usd, latency_ms, status, error_detail, "
            "started_at, finished_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                call_log.call_id,
                call_log.tick_id,
                call_log.model,
                int(call_log.fallback_used),
                call_log.prompt,
                call_log.response,
                call_log.prompt_tokens,
                call_log.completion_tokens,
                call_log.estimated_cost_usd,
                call_log.latency_ms,
                call_log.status,
                call_log.error_detail,
                started_at.isoformat(),
                finished_at.isoformat(),
            ),
        )
        await self._conn.commit()
        return cost_usd

    async def _on_tick(self, tick_index: int, dt_real: float) -> None:
        if self._terminated:
            # Heartbeat.run_n_ticks() has no stop-event check of its own
            # (unlike run()) -- this flag is what keeps a terminated daemon
            # inert for the remainder of a fixed-count test/dev run.
            return
        assert self._conn is not None
        assert self._channels is not None
        assert self._affect_dynamics is not None
        assert self._mood is not None
        assert self._modulation is not None
        assert self._forward_model is not None
        assert self._protention is not None
        assert self._arbiter is not None
        assert self._viability_budget is not None
        assert self._allostasis is not None
        assert self._termination_gate is not None
        assert self._pricing is not None
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
        self._current_tick_id = tick_id

        tick_ctx = TickContext(
            session_id=self._session_id,
            tick_index=tick_index,
            wall_ts=now,
            dt_real=dt_real,
            dt_subjective=dt_real,
            tempo_hz=tempo_hz,
            idle_state=False,
            pending_input_count=self._pending_user_messages.qsize(),
        )
        # Phase 6: read the ledger's own state *before* this tick's sensing
        # -- reflects the outcome of the *previous* tick's spend/replenish,
        # since this tick's own arbitration hasn't happened yet. Same
        # one-tick-lag pattern as prediction_error above.
        budget_reserve = self._viability_budget.reserve_channel()
        burn_rate = self._viability_budget.burn_rate_channel()
        register_state = self._channels.process(
            tick_ctx,
            tick_id,
            now,
            prediction_error=prediction_error,
            budget_reserve=budget_reserve,
            burn_rate=burn_rate,
            goal_gradient=self._prior_goal_gradient,
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
            confidence=self._confidence,
            prior_ignited=self._prior_ignited,
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

        # Phase 9: drain at most one queued user message per tick into a
        # real externally-sourced candidate. Fixed salience factors of 1.0
        # mirror the "viability" candidate's guaranteed-ignition pattern
        # (max ignition_threshold is exactly 1.0, condition is >=) -- a
        # user message always gets a chance to be heard the very tick it
        # arrives, never queued indefinitely behind other candidates.
        try:
            user_message_text: str | None = self._pending_user_messages.get_nowait()
        except asyncio.QueueEmpty:
            user_message_text = None
        if user_message_text is not None:
            candidates.append(
                WorkspaceCandidate(
                    source_module="user_message",
                    content={"text": user_message_text, "tick_id": tick_id},
                    novelty=1.0,
                    precision=1.0,
                    affective_weight=1.0,
                    goal_relevance=1.0,
                )
            )

        # Phase 6: anticipatory pressure bids a real candidate into the
        # workspace -- the mechanism behind "regulation is visible as agent
        # behavior, not a background cron job." Computed right after this
        # tick's own ChannelInference.update() (inside process() above), so
        # the posterior it reads is current.
        pressure = self._allostasis.anticipatory_pressure(
            "budget_reserve", threshold=VIABILITY_PRESSURE_THRESHOLD, lower_is_worse=True
        )
        if pressure > 0.0:
            candidates.append(
                WorkspaceCandidate(
                    source_module="viability",
                    content={"pressure": pressure, "channel": "budget_reserve", "tick_id": tick_id},
                    novelty=_clamp01(pressure),
                    precision=1.0,
                    affective_weight=1.0,
                    goal_relevance=VIABILITY_GOAL_RELEVANCE_BASELINE,
                )
            )

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
        # Phase 7: build this tick's real self-model + confidence estimate.
        # `history_summary` reuses the memory query results just fetched
        # above (see module docstring's Phase 7 paragraph) rather than
        # issuing a second MemoryStore.query() call.
        history_summary = "; ".join(r.record.content for r in memory_results)
        self_model = build_self_model(
            register_state=register_state,
            affect_state=affect_state,
            prediction_error=prediction_error,
            history_summary=history_summary,
            prior=self._self_model,
            tick_id=tick_id,
        )
        confidence = compute_confidence(
            self_model=self_model,
            prior_self_model=self._self_model,
            prediction_error=prediction_error,
            tick_id=tick_id,
        )
        await self._conn.execute(
            "INSERT INTO self_model (session_id, tick_id, version, body, agency, "
            "interoception_summary, history_summary, identity_traits, mental_state_estimate, "
            "temporal_self, confidence, ts) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                self._session_id,
                tick_id,
                self_model.version,
                json.dumps(self_model.body),
                self_model.agency,
                json.dumps(self_model.interoception_summary),
                self_model.history_summary,
                json.dumps(self_model.identity_traits),
                json.dumps(self_model.mental_state_estimate),
                json.dumps(self_model.temporal_self),
                confidence.confidence,
                now.isoformat(),
            ),
        )
        await self._conn.commit()
        self._self_model = self_model
        self._confidence = confidence
        self._prior_goal_gradient = self_model.identity_traits.get("goal_gradient", 0.0)

        broadcast = self._arbiter.select(candidates, affect_state, mood, tick_id)

        # Built from ticks already committed to workspace_broadcast -- i.e.
        # strictly before this tick's own row is inserted below, so the
        # monologue never echoes the current turn's own content back into
        # its own prompt (that content is already the live broadcast/user
        # message `assemble_prompt` sends separately).
        narrative_tail = (
            await build_narrative_tail(self._conn, self._session_id)
            if broadcast.ignited
            else []
        )

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
        self._prior_ignited = broadcast.ignited

        # Phase 9: the real send path through Phase 5's
        # render_prompt_if_ignited() seam. When a real (or injected test
        # fake) client is available, this actually streams a response and
        # charges the real post-response cost; otherwise it falls back to
        # Phase 6's prompt-tokens-only estimate (no network call), which
        # keeps every pre-Phase-9 gate test (no API key configured, no
        # client injected) exactly as before.
        prompt = render_prompt_if_ignited(broadcast, narrative_tail, modulation_params)
        if prompt is not None:
            cost_usd = await self._handle_ignited_prompt(prompt, tick_id)
        else:
            cost_usd = 0.0
        self._viability_budget.spend(cost_usd)

        # Termination is checked against the reserve as spend() actually
        # left it, before any same-tick replenishment can mask a real
        # depletion -- replenish() is pre-emptive self-regulation (fired
        # from anticipatory pressure crossing threshold before reserve
        # reaches zero), not a resurrection path once it's already there.
        if self._viability_budget.reserve_usd <= 0.0 and not self._terminated:
            try:
                await self._termination_gate.fire(
                    self._session_id, tick_id, reason="viability reserve depleted"
                )
            except TerminationRefused:
                pass
            else:
                self._terminated = True
                assert self._heartbeat is not None
                self._heartbeat.stop()

        # The one and only replenish() call site: an explicit,
        # workspace-arbitrated effector action, never a silent top-up.
        if broadcast.ignited and broadcast.winner.source_module == "viability":
            self._viability_budget.replenish()

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

        if self._tick_listeners:
            snapshot = TickSnapshot(
                tick_id=tick_id,
                valence=affect_state.valence,
                arousal=affect_state.arousal,
                tempo_hz=tempo_hz,
                budget_reserve_usd=self._viability_budget.reserve_usd,
                ignited=broadcast.ignited,
                winner_source=broadcast.winner.source_module,
                pending_input_count=self._pending_user_messages.qsize(),
            )
            for listener in list(self._tick_listeners):
                try:
                    await listener(snapshot)
                except Exception:  # noqa: BLE001 - a UI listener failure must never break the tick
                    pass
        self._current_tempo_hz = modulation_params.tempo_hz
