# Phase 1 Plan — Telemetry → interoceptive vector

## Context

Sub-plan for **Phase 1** of `PLAN.md`'s Build Order table: "Sensors,
interoception channels (logging only)"; gate: "Channels move under synthetic
load; no behavior-change assertion yet" (mirrors `docs/PlanBuildTEIC.md`
line 187). Phase 0 (daemon skeleton, fixed-tempo heartbeat, persistence,
neutral-placeholder registers/affect) is complete and committed
(`cc8f153`). This plan is the authority for Phase 1's two tasks; `PLAN.md`
and `docs/PlanBuildTEIC.md` remain the binding spec above it.

**Scope ruling (made by the controller, recorded here so it isn't mistaken
for an oversight):** Phase 1 wires `RegisterState` (the "interoceptive
vector") only. `AffectState`/`affect_sample` stays the Phase 0 neutral
placeholder — `affect_dynamics.py`/`mood.py` are not in this phase's table
row and depend on register deltas this phase is only just introducing.
Wiring affect is deferred to whichever task lands immediately before
Phase 2 needs it (Phase 2's `ModulationCompute.compute()` takes
`AffectState` as a parameter).

## Global Constraints (binding on both tasks)

- No hand-authored constants presented as *the* value for a channel that
  actually has no upstream signal yet: express those as principled
  ratios/defaults (e.g. "no spend recorded" → `budget_reserve = 1.0`, "no
  call attempted" → `effector_integrity = 1.0`, "no subsystem yet" → `0.0`)
  and say in a comment which later phase wires the real signal. Every
  channel's raw value must still flow through real inference — no
  channel may have `inferred_var == 0.0` on every single tick forever;
  the constant-input channels prove this by having their variance
  collapse toward (but not necessarily hit) zero as inference sees the
  same raw value repeatedly — a live inference process, not a bypass.
- Do **not** touch `teic/models/affect.py`, `affect_sample` inserts, or
  build `affect_dynamics.py`/`mood.py` — out of scope this phase (see
  Scope ruling above).
- Do **not** implement `interoception/allostasis.py`,
  `interoception/modulation.py`'s `compute()`, `interoception/reportability.py`,
  viability/budget tracking, or memory — later phases (2, 4, 6, 7).
- Follow `teic/temporal/heartbeat.py`'s existing dependency-injection style
  (injectable `time_source`) for anything reading wall-clock time, so tests
  drive synthetic timing without real sleeps — same pattern
  `tests/test_gates/test_phase0.py` already uses.
- `mypy --strict` must keep passing on `teic/models`, `teic/interoception`,
  `teic/workspace`, `teic/llm`, and must now also pass on `teic/embodiment`
  (new real code lands there this phase).
- Full `pytest -q` must pass, including the existing Phase 0 gate tests
  unmodified in behavior (row-count assertions may need the new real
  values but must still hold).
- Documentation updates (`BUILD_STATUS.md`, `ARCHITECTURE.md`) are part of
  "done" for the task that lands the daemon wiring — not a follow-up.

---

## Task 1: Sensors + interoceptive inference pipeline

Build the three cooperating modules that turn raw per-tick measurements
into a real `RegisterState`, with no daemon wiring yet (that's Task 2).

**Files to create:**

1. `teic/embodiment/sensors.py`
   - A `RawSensorSample` pydantic model with one `float` field per name in
     `teic.models.registers.REGISTER_CHANNELS`.
   - A `SensorArray` class (constructed once per session, not per tick —
     it holds a small ring buffer, so it must be an object with instance
     state, not a free function) with a method
     `sample(tick_ctx: teic.models.tick.TickContext) -> RawSensorSample`
     computing:
     - `latency_strain` = `abs(tick_ctx.dt_real - expected) / expected` where
       `expected = 1.0 / tick_ctx.tempo_hz`, clamped to `[0.0, 5.0]`.
     - `surprise_volatility` = population stddev of the last 10
       `latency_strain` values this instance has seen (ring buffer of
       length 10; fewer than 10 seen so far → stddev over what exists,
       0.0 for the very first sample).
     - `context_pressure` = `min(tick_ctx.pending_input_count / 5.0, 1.0)`.
     - `budget_reserve` = `1.0` — comment: no spend tracking until Phase 6.
     - `effector_integrity` = `1.0` — comment: no LLM call attempted yet.
     - `burn_rate`, `prediction_error`, `epistemic_tension`,
       `goal_gradient`, `memory_fragmentation`, `social_contact` = `0.0`
       each — comment naming the phase that wires each one (burn_rate/
       budget → 6, prediction_error → 3, epistemic_tension → 2/7,
       goal_gradient → 5, memory_fragmentation → 4, social_contact → 9).

2. `teic/interoception/inference.py`
   - `class ChannelInference`: per-channel fixed-gain EWMA mean/variance
     filter, gain `alpha = 0.3` (module constant, named, not a bare
     literal at the call site). Internal state: `dict[str, tuple[float,
     float]]` mapping channel → `(inferred_value, variance)`, lazily
     initialized on first `update()` call for that channel using that
     first raw value as the seed inferred value and variance `0.0`.
   - `update(channel: str, raw: float) -> tuple[float, float]`:
     ```
     if channel unseen: state[channel] = (raw, 0.0); return (raw, 0.0)
     prior_mean, prior_var = state[channel]
     new_mean = prior_mean + alpha * (raw - prior_mean)
     new_var = (1 - alpha) * (prior_var + alpha * (raw - prior_mean) ** 2)
     state[channel] = (new_mean, new_var)
     return (new_mean, new_var)
     ```
   - `infer(raw: RawSensorSample, tick_id: int, ts: datetime) -> RegisterState`:
     calls `update()` once per channel in `REGISTER_CHANNELS`, assembles
     the full `RegisterState` (point estimates + `variances` dict +
     `tick_id` + `ts`).

3. `teic/interoception/channels.py`
   - `class ChannelPipeline`: owns one `SensorArray` and one
     `ChannelInference` instance; `process(tick_ctx, tick_id, ts) ->
     RegisterState` calls `sensors.sample(tick_ctx)` then
     `inference.infer(raw, tick_id, ts)` and returns the result. This is
     the single object `daemon.py` will hold in Task 2.

**Tests to add:**

- `tests/test_embodiment/test_sensors.py`: constant `dt_real` ==
  `expected` gives `latency_strain == 0.0`; a jittered sequence of
  `dt_real` values produces nonzero, varying `latency_strain` and a
  `surprise_volatility` that responds to the jitter (goes from 0.0 on the
  first sample to nonzero once enough jittered samples have accumulated).
- `tests/test_interoception/test_inference.py`: repeated identical raw
  input drives variance toward 0.0 across calls (monotonically
  non-increasing after the first couple of updates); a raw input that
  jumps between two values keeps variance bounded away from 0.0; `infer()`
  returns a `RegisterState` with all 11 channels populated and
  `variances` keyed by every channel name.

**Verification:** run `pytest tests/test_embodiment tests/test_interoception -q`
and `mypy teic/embodiment teic/interoception` before reporting done; include
the exact commands and output in the report file.

---

## Task 2: Wire pipeline into daemon, Phase 1 gate test, docs

Depends on Task 1's `ChannelPipeline` interface.

**Changes:**

1. `teic/daemon.py`:
   - Import `ChannelPipeline` from `teic.interoception.channels`.
   - Construct one `ChannelPipeline()` instance in `start()` (same place
     `Heartbeat` is constructed) and store it as `self._channels`.
   - In `_on_tick`, after inserting the `tick` row, build a
     `teic.models.tick.TickContext` from the tick's fields (session_id,
     tick_index, wall_ts=now, dt_real, dt_subjective=dt_real, tempo_hz,
     idle_state=False, pending_input_count=0 — no input task exists yet),
     call `self._channels.process(tick_ctx, tick_id, now)` to get a real
     `RegisterState`, and replace the placeholder `register_sample` insert
     loop: for each channel, insert `raw_value` = the actual sampled raw
     float for that channel (thread it through — `ChannelPipeline.process`
     needs to expose the `RawSensorSample` too, e.g. return
     `tuple[RawSensorSample, RegisterState]` or store the last raw sample
     as an attribute; pick one and keep it consistent with Task 1's
     interface, adjusting Task 1's code if needed), `inferred_value` from
     `RegisterState`, `inferred_var` from `RegisterState.variances[channel]`.
   - Leave the `affect_sample` insert exactly as it is today (neutral
     placeholder) — do not touch it, per Global Constraints.

2. `tests/test_gates/test_phase1.py`:
   - Synthetic-load gate test using the same injected `time_source`/
     `sleep_fn` DI pattern as `test_phase0.py`. Drive a sequence of
     simulated `dt_real` values across ~30 ticks that is *not* constant
     (e.g. alternate between two intervals, or a small seeded sequence —
     deterministic, not `random` without a fixed seed).
   - After running, query `register_sample` for the session and assert:
     - row count matches `30 * len(REGISTER_CHANNELS)`.
     - the set of distinct `inferred_value` for `channel = 'latency_strain'`
       across the session's ticks has more than one distinct value (real
       movement, not the old flat `0.0`).
     - the set of distinct `inferred_var` for `channel = 'latency_strain'`
       is not `{0.0}` (inference is actually running).
   - No assertion on LLM calls, prompt content, or generated text —
     explicitly out of scope per this phase's gate wording.

3. `BUILD_STATUS.md`: mark the Phase 1 row "**Complete**"; add a
   "## Phase 1 — complete" section mirroring Phase 0's checklist/style,
   including a "How to verify this phase yourself" block with the
   commands actually used.

4. `ARCHITECTURE.md`: append "### Phase 1 — Telemetry → interoceptive
   vector (complete)" under "## Phase log", in the same prose style as
   the Phase 0 entry, explicitly stating the affect-stays-placeholder
   scope decision so a future reader doesn't mistake it for a gap.

**Verification:** run the **full** `pytest -q` and `mypy` (project-wide,
matching Phase 0's verification commands) before reporting done; include
exact commands and output in the report file.
