# Phase 2 Plan — Non-linguistic modulation (the real gate)

## Context

Sub-plan for **Phase 2** of `PLAN.md`'s Build Order table: "`modulation.py`,
`reportability.py`, wired into heartbeat + prompt_assembly's sampling params
(not text)"; gate: "Identical prompt text, different registers → divergent
tempo/temperature/speak-gate. **Hard stop for user check-in.**" This mirrors
`docs/PlanBuildTEIC.md`'s master Phase 2 row: "Non-linguistic modulation
pathways; no text rendering of state" / "Behavior changes with zero textual
access to state" — and its explicit callout: "**Phase 2 is the real gate.**
If behavior cannot be made to change through a non-linguistic channel, stop
and report to the user before continuing." Phase 1 (real `RegisterState` via
`ChannelPipeline`, `affect_sample` left as Phase 0's neutral placeholder) is
complete and committed (`72bccdb`).

**Scope ruling, carried forward from Phase 1's plan:** Phase 1 explicitly
deferred affect wiring to "whichever task lands immediately before Phase 2
needs it," naming `ModulationCompute.compute()`'s `AffectState`/`mood`
parameters as that trigger. Phase 2 is that task: `affect_dynamics.py` and
`mood.py` land here, not as a separate phase, because `ModulationCompute`
cannot be real without them.

**`reportability.py`'s scope this phase, stated explicitly so it isn't
mistaken for Phase 7's full reportability gate:** `docs/PlanBuildTEIC.md`
lists "reportability gate" under Phase 7 ("Self-model, metacognition,
reportability gate"), calibrated against confidence. `PLAN.md`'s own Build
Order table nonetheless names `reportability.py` in Phase 2. This plan
resolves the tension by scoping Phase 2's `reportability.py` narrowly: a
`ReportabilityGate` that decides `speak_gate_open` from `epistemic_tension`
plus a refractory cooldown — the concrete mechanism the gate test needs,
factored into its own testable module rather than inlined in `modulation.py`.
Full ignition-gated reportability (workspace arbiter input, self-model
confidence calibration) is Phase 5/7 work and is **not** built now; this is
recorded as an intentional partial wiring, not a gap.

## Global Constraints (binding on all tasks)

- No hand-authored emotion labels. `AffectState.nearest_attractor_label()`
  already enforces this at the model level (Phase 0); affect_dynamics/mood
  must only ever produce continuous `valence`/`arousal`/`mood` floats derived
  from register values, never a label field.
- `ModulationCompute.compute()` must stay the single entry point: called
  once per tick, its `ModulationParams` output threaded explicitly through
  call sites, no downstream module re-reading raw `RegisterState`/
  `AffectState` on its own. `llm/prompt_assembly.py`'s signature (no raw-state
  parameter) must not change — it already consumes `ModulationParams` only,
  since Phase 0; Phase 2's job is making the values flowing into it real, not
  changing the boundary itself.
- Every numeric constant (EWMA gains, clamp bounds, weights) must be a named
  module-level constant, not a bare literal at the call site — same
  convention `interoception/inference.py` established in Phase 1.
- Fields already declared on `ModulationParams` that no consumer exists for
  yet (`retrieval_k`, `retrieval_affect_weight`, `planning_depth`,
  `tool_risk_tolerance`, `salience_weight_overrides`) must still be computed
  from real inputs this phase (not fixed placeholders) even though nothing
  reads them until Phase 4/5/6 — comment which phase will consume each.
- `teic/temporal/heartbeat.py`'s existing DI style (`time_source`/
  `sleep_fn`) must be preserved; the new variable-tempo hook must default to
  `None` so Phase 0/1's gate tests, which construct `Heartbeat` without it,
  keep passing unmodified.
- Do **not** implement `interoception/allostasis.py`, viability/budget
  tracking, workspace arbiter/ignition, memory, or the self-model —
  Phases 4/5/6/7.
- `mypy --strict` must keep passing on `teic/models`, `teic/interoception`,
  `teic/workspace`, `teic/llm`, `teic/embodiment`, and now `teic/temporal`
  (heartbeat's new hook) and `teic/daemon.py`.
- Full `pytest -q` must pass, including Phase 0/1 gate tests unmodified in
  behavior.
- `BUILD_STATUS.md`/`ARCHITECTURE.md` updates are part of "done" for the
  task that lands daemon wiring, not a follow-up.
- Per PLAN.md, this phase ends in a **hard stop for user check-in** — do not
  proceed into Phase 3 after this phase's gate passes without the user's
  go-ahead.

---

## Task 1: Affect dynamics + mood

**Files to create:**

1. `teic/interoception/affect_dynamics.py`
   - Module constant `ALPHA = 0.3` (same fixed-gain EWMA convention as
     `inference.py`).
   - `class AffectDynamics`: per-session stateful EWMA over two raw signals
     computed each tick from `RegisterState`:
     - `_raw_valence(registers)` = `clamp(registers.budget_reserve -
       registers.burn_rate - 0.5*registers.epistemic_tension -
       0.5*registers.prediction_error, -1.0, 1.0)` — viability trend, pulled
       down by unresolved tension/error.
     - `_raw_arousal(registers)` = `clamp(0.4*registers.prediction_error +
       0.2*registers.surprise_volatility + 0.2*registers.latency_strain +
       0.2*registers.context_pressure, 0.0, 1.0)` — resource-mobilization
       magnitude, matching `AffectState`'s existing docstring formula.
     - `update(registers) -> tuple[float, float]`: EWMA-smooths both raw
       signals against previous state (lazily seeded on first call, same
       "first value is the seed" pattern as `ChannelInference.update()`),
       returns `(valence, arousal)`.
2. `teic/interoception/mood.py`
   - Module constant `MOOD_ALPHA = 0.05` — deliberately smaller than
     `AffectDynamics.ALPHA` so mood is a genuinely *slower* integrator over
     the valence trajectory, per `AffectState`'s docstring.
   - `class MoodTracker`: `update(valence: float) -> float`, single EWMA
     state variable initialized to `0.0` (neutral start, not hand-labeled).

**Tests to add:**

- `tests/test_interoception/test_affect_dynamics.py`: a register vector with
  high `budget_reserve`/low `burn_rate`/zero tension produces positive
  valence; the inverse produces negative valence; high
  `prediction_error`/`surprise_volatility` produces high arousal vs. a calm
  vector's low arousal; repeated identical input converges (smooths) rather
  than jumping straight to the raw value on the second call.
- `tests/test_interoception/test_mood.py`: mood moves toward sustained
  positive valence input but much more slowly than a single-tick
  `AffectDynamics` update would (assert mood's movement after N identical
  updates is smaller than `AffectDynamics`'s after the same N, for the same
  effective input — demonstrates the "slow integrator" property, not just
  that both are EWMAs).

**Verification:** `pytest tests/test_interoception -q` and `mypy
teic/interoception` before reporting done.

---

## Task 2: `reportability.py` — speak-gate

**Files to create:**

1. `teic/interoception/reportability.py`
   - Module constants: `SPEAK_GATE_EPISTEMIC_THRESHOLD = 0.3`,
     `REFRACTORY_TICKS = 5`.
   - `class ReportabilityGate`: holds `_ticks_since_open` (initialized to
     `REFRACTORY_TICKS`, i.e. ready immediately on session start — not an
     arbitrary "closed forever" default). `evaluate(epistemic_tension:
     float) -> bool`: gate opens iff cooldown has elapsed **and**
     `epistemic_tension >= SPEAK_GATE_EPISTEMIC_THRESHOLD`; opening resets
     the cooldown counter, not-opening increments it. Docstring must state
     explicitly that this does *not* yet incorporate workspace
     ignition (Phase 5) or self-model confidence (Phase 7) — those compose
     with this gate later, they don't replace it.

**Tests to add:**

- `tests/test_interoception/test_reportability.py`: low epistemic_tension
  never opens the gate across many calls; high epistemic_tension opens it
  once then stays closed for `REFRACTORY_TICKS` calls even with tension
  still high (cooldown enforced); after the cooldown elapses with tension
  still high, it opens again.

**Verification:** `pytest tests/test_interoception -q` and `mypy
teic/interoception`.

---

## Task 3: `modulation.py` real `compute()`, heartbeat variable tempo, daemon wiring

Depends on Tasks 1 and 2.

**Changes:**

1. `teic/interoception/modulation.py`:
   - Replace the `NotImplementedError` stub. `ModulationCompute.__init__`
     takes `idle_tempo_hz`, `max_tempo_hz`, `base_temperature: float = 0.7`
     (named constant `BASE_TEMPERATURE`), and an injectable
     `ReportabilityGate` (default-constructed if not passed — same DI
     posture as `Heartbeat`'s clock).
   - `compute(registers, affect, mood)` implements every field from
     PLAN.md's "Non-Linguistic Modulation Pathway" section concretely:
     - `tempo_hz = clamp(idle_tempo_hz + affect.arousal *
       (max_tempo_hz - idle_tempo_hz), idle_tempo_hz, max_tempo_hz)`.
     - `temperature = clamp(base_temperature + registers.epistemic_tension *
       0.5 - max(0.0, -mood) * 0.3, 0.1, 1.5)`.
     - `top_p = clamp(0.9 + registers.epistemic_tension * 0.05, 0.5, 1.0)`.
     - `retrieval_k = round(clamp(10 - registers.context_pressure * 5 +
       registers.memory_fragmentation * 5, 1, 20))` — comment: unused until
       Phase 4's retrieval.
     - `retrieval_affect_weight = clamp(affect.valence, -1.0, 1.0)` —
       comment: unused until Phase 4.
     - `planning_depth = round(clamp(5 - (1 - registers.budget_reserve) * 3
       - registers.burn_rate * 2 - registers.goal_gradient * 2, 1, 5))` —
       comment: unused until Phase 5/6.
     - `tool_risk_tolerance = clamp(registers.effector_integrity +
       affect.valence * 0.2, 0.0, 1.0)` — comment: unused until an effector
       exists.
     - `salience_weight_overrides = {"embodiment": 1.0 +
       registers.latency_strain}` — comment: unused until Phase 5's arbiter;
       named single example from PLAN.md's own text ("latency_strain
       up-weights embodiment candidates"), not a full source table yet.
     - `speak_gate_open = self._reportability.evaluate(registers.epistemic_tension)`.
   - A private module-level `_clamp(x, lo, hi) -> float` helper shared by
     every field above.
2. `teic/temporal/heartbeat.py`:
   - Add optional constructor param `tempo_hz_provider: Callable[[], float]
     | None = None`. After each `on_tick` call in both `run()` and
     `run_n_ticks()`, if the provider is set, reassign `self._tempo_hz =
     self._tempo_hz_provider()` — the *next* interval uses the new value,
     matching PLAN.md's "fed straight into the heartbeat's next sleep
     interval." Default `None` preserves Phase 0/1 fixed-tempo behavior
     exactly (those tests construct `Heartbeat` without this param).
3. `teic/daemon.py`:
   - Construct `self._affect_dynamics = AffectDynamics()`, `self._mood =
     MoodTracker()`, `self._modulation = ModulationCompute(idle_tempo_hz=...,
     max_tempo_hz=...)` (from `self._settings.daemon`), and
     `self._current_tempo_hz: float = self._settings.daemon.base_tempo_hz`
     in `start()`. Pass `tempo_hz_provider=lambda: self._current_tempo_hz`
     to the `Heartbeat` constructed there.
   - In `_on_tick`: capture `tempo_hz_used = self._current_tempo_hz` at the
     top (the cadence actually in effect for *this* tick) and use it both
     for the `tick` row's `tempo_hz` column and for `TickContext.tempo_hz`
     (replacing the current hard read of
     `self._settings.daemon.base_tempo_hz` in both places). After computing
     `register_state`, call `self._affect_dynamics.update(register_state)`
     → `(valence, arousal)`, then `self._mood.update(valence)` → `mood`,
     build a real `AffectState(valence=valence, arousal=arousal, mood=mood,
     tick_id=tick_id, ts=now)`, call `self._modulation.compute(register_state,
     affect_state, mood)` → `modulation_params`. Write `affect_sample` from
     `affect_state`'s real fields plus `affect_state.nearest_attractor_label()`
     (replacing Phase 1's hard-coded `0.0, 0.0, 0.0, "neutral"` insert).
     Finally set `self._current_tempo_hz = modulation_params.tempo_hz` so the
     *next* tick's interval reflects this tick's computed arousal.

**Tests to add:**

- `tests/test_interoception/test_modulation.py`: two `RegisterState`/
  `AffectState`/`mood` inputs — one "calm" (low arousal/epistemic_tension),
  one "strained" (high arousal/epistemic_tension) — fed through the *same*
  `assemble_prompt(broadcast, narrative_tail, modulation)` call with
  byte-identical `broadcast`/`narrative_tail` arguments: assert the two
  resulting `ChatPrompt.messages` are equal (byte-identical text) while
  `ChatPrompt.temperature`/`top_p` and the source `ModulationParams.tempo_hz`/
  `speak_gate_open` differ. This is the literal gate wording, exercised as a
  unit test rather than only at the daemon-integration level.
- `tests/test_temporal/test_heartbeat.py` (new): a `tempo_hz_provider` that
  returns a different value after each tick causes successive `dt_real`
  intervals (via a fake `sleep_fn` recording its argument) to actually
  change — proves the feedback loop, independent of any daemon/register
  logic.

**Verification:** `pytest tests/test_interoception tests/test_temporal
tests/test_llm -q` and `mypy teic/interoception teic/temporal teic/daemon.py`.

---

## Task 4: Phase 2 gate test, docs

Depends on Task 3.

1. `tests/test_gates/test_phase2.py`:
   - Daemon-level synthetic run, same DI pattern as
     `test_phase1.py` (fake `time_source`/`sleep_fn` driving `daemon._on_tick`
     directly via a separately constructed `Heartbeat`), driven long enough
     (jittered `dt_real`, reusing Phase 1's alternating-interval sequence or
     a variant that also pushes `latency_strain`/`surprise_volatility` into
     a wide range) that arousal visibly varies tick to tick.
   - Assert: `tick.tempo_hz` takes more than one distinct value across the
     session's rows (Phase 0/1 never did — this is the concrete "fixed
     tempo becomes variable" behavior change); `affect_sample.valence`/
     `arousal` are not pinned at Phase 1's flat `0.0` placeholder across
     every tick; and — reusing Task 3's unit-level check inline or by
     import — that feeding two of this run's own captured
     `(RegisterState, AffectState, mood)` snapshots (one early/calm-ish tick,
     one from a strained tick) through `assemble_prompt` with identical
     `broadcast`/`narrative_tail` produces identical prompt text with
     divergent `temperature`/`tempo_hz`/`speak_gate_open` — tying the
     daemon-level register movement directly to the literal gate wording,
     not just to two hand-picked synthetic vectors.
   - No assertion on actual LLM calls (still no wiring into a real workspace
     broadcast loop — that's Phase 5) — explicitly out of scope, same
     posture as Phase 0/1's gate tests.
2. `BUILD_STATUS.md`: mark Phase 2 "**Complete**", add a "## Phase 2 —
   complete" section in Phase 0/1's style, including the **hard-stop
   check-in** notice per PLAN.md and a "How to verify this phase yourself"
   block.
3. `ARCHITECTURE.md`: append "### Phase 2 — Non-linguistic modulation
   (complete)" to the Phase log, stating explicitly: the `reportability.py`
   scope ruling (Phase 2's narrow gate vs. Phase 7's full one), that
   `salience_weight_overrides`/`retrieval_k`/`planning_depth`/
   `tool_risk_tolerance` are computed but not yet consumed by anything
   (naming the phases that will consume them), and that no real LLM call
   happens yet — this phase proves the modulation *pathway*, not an
   end-to-end chat turn.

**Verification:** full `pytest -q` and project-wide `mypy` before reporting
done; include exact commands and output in the report. Then **stop and
check in with the user** per PLAN.md's Phase 2 hard-stop — do not begin
Phase 3 in the same turn.
