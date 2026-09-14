# Phase 3 Plan — Forward model, protention buffer, prediction error

## Context

Sub-plan for **Phase 3** of `PLAN.md`'s Build Order table: "Forward model,
protention buffer, prediction error" / gate: "Contingency-change test: 3x
latency injection → error spike → adaptation." This mirrors
`docs/PlanBuildTEIC.md`'s Layer 0 ("Protention buffer — explicit timestamped
predictions ... next interoceptive vector") and Layer 1 ("Forward model of
own effectors (predict observation and latency from action + body state);
errors update the model") sections, and its "Contingency-change test" under
Additional Experiments: "silently inflate a tool's latency 3×; measure
transient error spike and adaptation."

Phase 2 (`b301dca`) is complete and was the spec's explicit hard-stop; the
user has given the go-ahead to continue into Phase 3.

**Scope ruling, stated explicitly:** there is no real effector/tool call
wired into the daemon yet (`llm/client.py` exists but nothing in
`daemon.py` calls it — that's Phase 5+, once the workspace arbiter can win a
broadcast worth turning into an LLM call). The only genuinely observable
"action → latency" loop that exists this early is the daemon's own tick
timing: each tick *is* an action (sleep for the commanded interval) with an
observable outcome (`dt_real`), exactly the mechanism `embodiment/sensors.py`
already uses for `latency_strain` (a **fixed**-expectation deviation from
`1/tempo_hz`, no learning). Phase 3's forward model targets this same
signal but adds the piece `latency_strain` deliberately does not have:
learned, adaptive expectation. This is what makes the contingency-change
test meaningful without inventing a real tool call: a sustained step-change
in `dt_real` (standing in for "a tool's latency 3x-ed") produces a
transient spike in the forward model's `prediction_error` output that
**decays back down over subsequent ticks as the model re-learns the new
regime** — the literal "error spike → adaptation" gate — while
`latency_strain` (unchanged this phase) stays elevated forever, since it has
no memory. Real per-effector forward models (once effectors exist) are
Phase 5+ work; this phase builds the mechanism generically enough to extend
then, not a placeholder.

Per `PLAN.md`'s module layout, `forward_model.py` lives in `teic/embodiment/`
(Layer 1); the protention buffer lives in `teic/temporal/` (Layer 0) since
`PlanBuildTEIC.md` places it there explicitly, alongside the retention
buffer and specious present (both still unbuilt — out of scope this phase,
per the Build Order table's row-3 scope: forward model + protention buffer
+ prediction error only, not retention/specious-present/prospective-memory).

**Protention persistence, stated explicitly so it isn't mistaken for a
missed migration:** `PLAN.md`'s Data Model section fixes the migration list
at `0001`-`0004`, none of which include a protention/prediction table.
Phase 3's `ProtentionBuffer` is therefore **in-memory only**, one session's
worth of state on the daemon instance, exactly like `SensorArray`'s latency
ring buffer or `ChannelInference`'s per-channel EWMA state — not a gap to
fix, an intentional scope match to the locked-in schema.

## Global Constraints (binding on all tasks)

- No hand-authored emotion labels or magic thresholds without a named
  module-level constant — same convention as `inference.py`/`modulation.py`.
- `prediction_error` becomes a real, non-zero `RawSensorSample` field this
  phase (currently hardcoded `0.0` in `embodiment/sensors.py` with the
  comment "wired in Phase 3"). No other placeholder channel
  (`epistemic_tension`, `goal_gradient`, `memory_fragmentation`,
  `social_contact`, `burn_rate`, `budget_reserve`, `effector_integrity`)
  changes this phase — those remain whatever phase already owns them.
- `ChannelPipeline`/`SensorArray`'s existing call shape must stay
  additive-only: new parameters get defaults so any code that already calls
  `.process(tick_ctx, tick_id, ts)` / `.sample(tick_ctx)` without them
  keeps compiling and behaving as before (mirrors `Heartbeat`'s
  `tempo_hz_provider` precedent from Phase 2).
- `ForwardModel`/`ProtentionBuffer` must not read `Settings` or touch the
  DB directly — same "pure computation object, daemon does I/O" posture as
  `AffectDynamics`/`MoodTracker`/`ModulationCompute`.
- Do **not** implement retention buffer, specious present, prospective
  memory, body schema, affordance map, viability/agency, or any real
  effector call — those are later phases (4, 5, 6, 9 as applicable).
- `mypy --strict` (or bare project-wide `mypy`, matching how it's actually
  invoked in this repo) must keep passing on `teic/models`,
  `teic/interoception`, `teic/embodiment`, `teic/temporal`, `teic/workspace`,
  `teic/llm`, and `teic/daemon.py`.
- Full `pytest -q` must pass, including every prior phase's gate test
  unmodified in behavior.
- `BUILD_STATUS.md`/`ARCHITECTURE.md` updates are part of "done" for the
  task that lands daemon wiring, not a follow-up.
- Phase 3's gate is **not** a named hard-stop in `PLAN.md` (only Phase 2
  was) — proceeding straight into reporting completion and awaiting the
  user's next instruction is correct, but do not silently start Phase 4
  in the same turn without saying so.

---

## Task 1: `ForwardModel` + `ProtentionBuffer`

**Files to create:**

1. `teic/embodiment/forward_model.py`
   - Module constants: `ALPHA = 0.3` (same fixed-gain EWMA convention as
     `inference.py`/`affect_dynamics.py`), `INITIAL_MULTIPLIER = 1.0`
     (unbiased prior: predicted latency equals nominal latency until
     evidence says otherwise), `ERROR_CLAMP_MAX = 5.0` (same clamp ceiling
     `sensors.py` uses for `latency_strain`, so the two channels are
     comparable in magnitude).
   - `class ForwardModel`: one instance per session, holds `_multiplier:
     float = INITIAL_MULTIPLIER` — its running estimate of "actual dt_real
     ÷ nominal dt" (nominal dt = `1/tempo_hz` for whichever tick is in
     effect).
     - `predict_dt_real(self, nominal_dt: float) -> float`: returns
       `nominal_dt * self._multiplier` — the model's forecast for the next
       tick's `dt_real`, using the *current* (not-yet-updated) multiplier.
     - `observe(self, actual_dt_real: float, nominal_dt: float,
       predicted_dt_real: float) -> float`: computes
       `error = min(abs(actual_dt_real - predicted_dt_real) /
       predicted_dt_real, ERROR_CLAMP_MAX)`, then updates
       `self._multiplier += ALPHA * (actual_dt_real / nominal_dt -
       self._multiplier)`, then returns `error`. Order matters: the error
       is computed against the prediction made *before* this call updates
       the model — that's what makes a step-change produce a spike (old
       multiplier, wrong) followed by decay (multiplier adapts) rather than
       an instantly-perfect prediction.
     - Docstring must state the "why no real effector yet" scope ruling
       above verbatim in substance (tick timing stands in for effector
       latency until Phase 5+ effectors exist).
2. `teic/temporal/protention.py`
   - `class ProtentionEntry(BaseModel)`: `made_at_tick_id: int`,
     `predicted_at: datetime`, `predicted_dt_real: float`,
     `predicted_registers: dict[str, float]` — the "explicit timestamped
     predictions" `PlanBuildTEIC.md` names (latency stands in for "what the
     next tool call returns"; `predicted_registers` is the literal "next
     interoceptive vector" prediction, computed as a naive one-step
     carry-forward of the current tick's inferred `RegisterState` — the
     EWMA filter's current mean already *is* its best forecast for the next
     observation absent new evidence, so no separate per-channel forecaster
     is needed this phase).
   - `class ProtentionBuffer`: holds `_pending: ProtentionEntry | None =
     None`. `push(self, entry: ProtentionEntry) -> None` replaces any
     pending entry; `pop(self) -> ProtentionEntry | None` returns and
     clears it. Docstring must state explicitly this is a **single-slot,
     one-tick-ahead** buffer (not a ring buffer) — Phase 3's protention
     horizon is exactly one tick; a multi-step horizon is a future
     extension, not a gap.

**Tests to add:**

- `tests/test_embodiment/test_forward_model.py` (new directory: no
  `tests/test_embodiment/` exists yet — add `__init__.py` too):
  - A model repeatedly observing `actual_dt_real == nominal_dt` (perfect
    predictions) converges its multiplier near `1.0` and reports `error`
    near `0.0` every time.
  - A model that has adapted to a stable regime, then observes a single
    tick where `actual_dt_real` is 3x `nominal_dt` (holding `nominal_dt`
    fixed across the call), reports a large `error` on that call — the
    spike.
  - The same model, after several more `observe()` calls at the new 3x
    ratio, reports `error` on the later calls that is meaningfully smaller
    than the error on the first post-change call — the adaptation —
    even though `actual_dt_real` never returns to the old regime.
- `tests/test_temporal/test_protention.py` (new file in the existing
  `tests/test_temporal/` directory): `push` then `pop` returns the same
  entry; a second `pop` with nothing pushed since returns `None`; pushing
  twice without popping keeps only the most recent entry (single-slot
  behavior, not a queue).

**Verification:** `pytest tests/test_embodiment tests/test_temporal -q` and
`mypy teic/embodiment teic/temporal`.

---

## Task 2: Daemon wiring — `prediction_error` becomes real

Depends on Task 1.

**Changes:**

1. `teic/embodiment/sensors.py`:
   - `SensorArray.sample(self, tick_ctx: TickContext, prediction_error:
     float = 0.0) -> RawSensorSample`: replace the hardcoded
     `prediction_error=0.0,  # wired in Phase 3` line with
     `prediction_error=prediction_error,` (the parameter, now threaded
     through) and update the module docstring's channel-ownership list to
     drop `prediction_error -> 3` from the "still placeholder" set.
2. `teic/interoception/channels.py`:
   - `ChannelPipeline.process(self, tick_ctx: TickContext, tick_id: int, ts:
     datetime, prediction_error: float = 0.0) -> RegisterState`: forward the
     new parameter straight into `self.sensors.sample(tick_ctx,
     prediction_error)`.
3. `teic/daemon.py`:
   - `start()`: construct `self._forward_model = ForwardModel()` and
     `self._protention = ProtentionBuffer()`; add matching `| None`
     attributes in `__init__` (same pattern as `self._modulation` etc.).
   - `_on_tick`, restructured (exact new body, replacing the current
     tick-row-insert-through-`register_state` section):

     ```python
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
     ```
   - Update the module docstring's phase-log comment block, adding a
     "Phase 3:" paragraph describing `prediction_error` now flowing from a
     real `ForwardModel`/`ProtentionBuffer` pair instead of the flat `0.0`
     placeholder, and stating explicitly this still isn't a real
     effector-latency forward model (tick timing stands in) — that's
     Phase 5+.

**Tests to add:**

- `tests/test_daemon.py` (create if it doesn't exist, else extend): a
  short synthetic run (reusing the fake `time_source`/`sleep_fn` DI pattern
  from `test_phase1.py`/`test_phase2.py`, driven directly rather than via
  the gate test file) where the first several ticks use `dt_real` equal to
  each tick's nominal `1/tempo_hz` and asserts `register_sample` rows for
  the `prediction_error` channel are near-`0.0` on ticks after the first
  (tick 0 has no prior prediction, so it alone may be `0.0` trivially —
  assert on tick ≥ 2 instead).

**Verification:** `pytest tests/test_daemon.py tests/test_embodiment
tests/test_interoception -q` and `mypy teic/embodiment
teic/interoception teic/daemon.py`.

---

## Task 3: Phase 3 gate test, docs

Depends on Task 2.

1. `tests/test_gates/test_phase3.py`:
   - Same DI pattern as `test_phase1.py`/`test_phase2.py`: construct
     `TeicDaemon`, `await daemon.start()`, then drive `daemon._on_tick`
     directly via a separately constructed `Heartbeat` with a scripted fake
     `sleep_fn` — but this time the script is a **deliberate two-phase
     step function**, not jitter: the first `N_BASELINE = 15` ticks use
     `dt_real = 1.0` (matching `base_tempo_hz = 1.0`'s nominal interval, so
     the forward model converges near a `1.0` multiplier with near-zero
     `prediction_error`), then the next `N_INJECTED = 20` ticks use
     `dt_real = 3.0` (the sustained "3x latency injection", standing in for
     `PlanBuildTEIC.md`'s "silently inflate a tool's latency 3×" per this
     plan's scope ruling).
   - Pull every tick's `prediction_error` from `register_sample` for this
     session, ordered by `tick_index`.
   - Assert **spike**: the `prediction_error` on the first injected tick
     (`tick_index == N_BASELINE`) is substantially larger than the mean
     `prediction_error` over the last few baseline ticks (e.g. indices
     `N_BASELINE - 5` through `N_BASELINE - 1`) — concretely, at least 3x
     that baseline mean (accounting for `ERROR_CLAMP_MAX` — pick a baseline
     window late enough that the mean is small and non-zero-safe, or assert
     against a small floor constant if the baseline mean rounds to exactly
     `0.0`).
   - Assert **adaptation**: the mean `prediction_error` over the *last*
     few injected ticks (e.g. the final 5 of the run) is substantially
     smaller than the first-injected-tick spike value — the model has
     re-learned the new regime even though `dt_real` never returns to
     baseline.
   - Assert, for contrast and to prove this is a *new* capability rather
     than a restatement of existing behavior: `register_sample`'s
     `latency_strain` channel (the fixed-expectation, non-adaptive sibling
     signal) stays elevated across the *entire* injected window without
     decaying — i.e. it does **not** show the same spike-then-adapt shape
     `prediction_error` does. This is the concrete evidence that Phase 3
     added a genuinely new (learned) signal rather than just relabeling
     `latency_strain`.
2. `BUILD_STATUS.md`: mark Phase 3 "**Complete**", add a "## Phase 3 —
   complete" section in the existing phases' style (bullet list of what was
   built, referencing this plan's scope rulings — no real effector yet,
   in-memory-only protention buffer — verbatim in substance), plus a "How
   to verify this phase yourself" block matching Phase 0-2's format
   (`source .venv/bin/activate`, `pytest -q`, `mypy`).
3. `ARCHITECTURE.md`: append "### Phase 3 — Forward model, protention
   buffer, prediction error (complete)" to the Phase log, stating: the
   tick-timing-stands-in-for-effector-latency scope ruling and that a real
   per-effector forward model is Phase 5+ work; that the protention buffer
   is in-memory/single-slot/one-tick-ahead (not persisted, not a ring
   buffer) and why (no protention table in the locked migration list);
   that `predicted_registers` is captured each tick but has no consumer yet
   (name Phase 4+ as the eventual consumer, e.g. retrieval/consolidation
   wanting to compare predicted vs. actual interoceptive trajectories).

**Verification:** full `pytest -q` and project-wide `mypy` before reporting
done; include exact commands and output in the report. Phase 3 is not a
named hard-stop in `PLAN.md`, but still report completion and wait rather
than starting Phase 4 unannounced in the same turn.
