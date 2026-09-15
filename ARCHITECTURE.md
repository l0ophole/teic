# Architecture (as built)

This document is updated at the end of each build phase. See `PLAN.md` for
the full design and `docs/PlanBuildTEIC.md` for the governing spec.

## Layers

- **Layer 0 (temporal)** — `teic/temporal/`: heartbeat, retention buffer,
  specious present, protention buffer, prospective memory, narrative self.
- **Layer 1 (embodiment)** — `teic/embodiment/`: effectors, sensors, forward
  model, body schema, affordance map, viability, agency, social body.
- **Layer 2 (interoception)** — `teic/interoception/`: channel inference,
  allostasis, affect dynamics, mood, the modulation pathway, reportability gate.
- **Layer 3 (global integration)** — `teic/workspace/`: arbiter, broadcast,
  mineness tagging, self-model, metacognition, narrative constructor.

## Two resolved tensions in the source spec (intentional, not deviations)

1. **Termination on viability failure.** The spec's Layer 1 text says budget
   hitting zero causes "actual termination"; the Ethics section requires this
   never be a silent default. Resolution (favors Ethics): termination is
   **disabled by default** — budget-zero triggers a low-power halt (action and
   spend suppression) unless `viability.allow_actual_termination=true` **and**
   `viability.termination_justification` is a non-empty string.

2. **Reportability-gate wording vs. "no affirm/deny" rule.** The "no training
   or prompting the agent to deny or affirm internal states" rule is about not
   biasing the *content* of a self-report. The reportability gate's system
   prompt is about *permission to report at all*, which is a different axis.
   Concretely: "you may reference this cycle's broadcast content if relevant"
   is permitted scaffolding; "you feel X" / "as an AI you don't experience X"
   is banned scaffolding. Enforced by a lint check in `teic/ethics/guardrails.py`
   (Phase 7) run over every system/prompt template at startup.

## Phase log

### Phase 0 — Daemon skeleton (complete)

- `teic/daemon.py` / `teic/temporal/heartbeat.py`: fixed-tempo (1Hz) tick
  loop; `Heartbeat` takes injectable `time_source`/`sleep_fn` so tests can
  simulate long wall-clock spans without waiting on them.
- `teic/persistence/`: `aiosqlite`-based WAL-mode connection, hand-rolled
  numbered-`.sql`-file migration runner (no migrations framework), `LogSink`
  writing `LogEvent` rows into `log_event` (this table IS the structured
  JSON-lines log layer; `LogSink.export_jsonl` dumps it on demand).
- `teic/models/`: pure pydantic models for every cross-cutting data shape
  (`TickContext`, `RegisterState`, `AffectState`, `WorkspaceBroadcast`,
  `MemoryRecord`, `LogEvent`, `SelfModel`, `ProbeResult`). Zero I/O, so every
  other layer can depend on them without import cycles.
- `teic/llm/client.py`: `httpx`-based OpenRouter client, retry/backoff on
  429/5xx, primary→fallback model failover, streaming, and a failure hook
  that must be wired to interoceptive strain (done in Phase 1+; the hook
  exists now, the wiring lands with `teic/interoception/channels.py`).
- `teic/llm/prompt_assembly.py`: the type-enforced "broadcast content only"
  boundary. `ModulationParams` is defined in
  `teic/interoception/modulation.py` now as a shared data shape; its
  `compute()` deliberately raises `NotImplementedError` until Phase 2 so an
  unimplemented gate fails loudly rather than looking decoratively "done."
- Registers/affect are written as neutral placeholders this phase (all
  zeros) — real inference is Phase 1's job.

Gate test: `tests/test_gates/test_phase0.py` — clean daemon start/stop, one
`tick`/`register_sample`(×11)/`affect_sample` row set per cycle, and a fast
synthetic 12-simulated-hour heartbeat run via injected fake clock (the
compressed-time complement to Phase 6's real 12h manual verification run).

**Model slug verification (spec-required before closing this phase):**
confirmed via `GET https://openrouter.ai/api/v1/models` that both
`~deepseek/deepseek-v4-flash-latest` (leading `~` is real, present verbatim in
the catalog) and `inclusionai/ling-3.0-flash-vl:free` exist. Kept as-is in
`config/default.toml`.

### Phase 1 — Telemetry → interoceptive vector (complete)

- `teic/embodiment/sensors.py`: `SensorArray` computes the two channels
  genuinely observable this early -- `latency_strain` from tick timing
  jitter against the tempo's expected interval, and `context_pressure`
  from pending input volume -- plus a derived `surprise_volatility` (the
  population stddev of recent `latency_strain` readings). Every other
  channel holds a documented placeholder value until the phase that wires
  it for real (burn_rate/budget_reserve -> 6, prediction_error -> 3,
  epistemic_tension -> 2/7, goal_gradient -> 5, memory_fragmentation -> 4,
  social_contact -> 9, effector_integrity -> whenever an LLM call is
  actually attempted). Constructed once per session so its ring-buffer
  state persists across ticks.
- `teic/interoception/inference.py`: `ChannelInference`, a per-channel
  fixed-gain EWMA (alpha=0.3) mean/variance filter with a nonzero seed
  variance and small per-tick process noise, so `RegisterState` is never
  hand-authored and a constant-input channel's variance decays toward a
  small floor instead of collapsing to a fake `0.0` "perfect certainty."
  This is the minimal generative model this phase needs; Phase 3+ may
  replace it with something richer behind the same `infer()` seam.
- `teic/interoception/channels.py`: `ChannelPipeline` is the one object
  `daemon.py` holds per session -- it composes one `SensorArray` with one
  `ChannelInference` and exposes `process(tick_ctx, tick_id, ts) ->
  RegisterState`. The `RawSensorSample` that produced that state is kept
  on `pipeline.last_raw` (rather than returned as part of a tuple) so
  callers that only want the inferred vector don't have to unpack one.
- `teic/daemon.py`: `_on_tick` now builds a real `TickContext` from the
  tick's own fields (no input task exists yet, so `idle_state`/
  `pending_input_count` stay at neutral defaults) and calls
  `ChannelPipeline.process()` to get a real `RegisterState`, then writes
  `register_sample` rows with the actual sampled `raw_value`,
  `inferred_value`, and `inferred_var` per channel -- replacing Phase 0's
  flat-zero placeholders.
- **Architectural divergence from `PLAN.md`, recorded here rather than left
  implicit**: `PLAN.md` describes a decoupled `sensor_task` running at a
  fixed fast cadence separate from the cognitive tick loop. Phase 1's actual
  implementation samples sensors inline inside `_on_tick` (the cognitive
  tick), with `SensorArray`'s ring buffer implicitly scoped to tick cadence
  rather than a faster, independent one. This was this phase's chosen
  direction, not an accidental slip, but it is a real deviation from the
  overall plan; the decoupled `sensor_task` is deferred to a later phase.
- **Scope decision, stated explicitly so it isn't mistaken for a gap**:
  `affect_sample` is left exactly as Phase 0 wrote it (neutral
  placeholder valence/arousal/mood/attractor_label). Affect dynamics and
  mood are Layer 2 work that belongs with the non-linguistic modulation
  gate in Phase 2, not this phase -- Phase 1's job was strictly the
  telemetry-to-interoceptive-vector path (register channels), not affect.

Gate test: `tests/test_gates/test_phase1.py` -- a synthetic 30-tick daemon
run driven by a deterministic, non-constant `dt_real` jitter sequence
(injected via the same `time_source`/`sleep_fn` DI pattern Phase 0's
heartbeat test uses), asserting the resulting `register_sample` row count
and that `latency_strain`'s `inferred_value`/`inferred_var` actually move
across ticks rather than staying pinned at Phase 0's flat `0.0`. Per this
phase's gate wording, no assertion is made about LLM calls, prompt
content, or generated text.

### Phase 2 — Non-linguistic modulation (complete)

**Phase 2 is the spec's explicitly-named "real gate"**: the master spec
(`docs/PlanBuildTEIC.md`) states that if behavior cannot be made to change
through a non-linguistic channel, the build stops and reports to the user
before continuing. This phase makes that behavior change concrete: the
heartbeat's tick cadence and the LLM sampling parameters (`temperature`,
`top_p`) now move with the interoceptive/affective state, with zero
textual access to that state -- `llm/prompt_assembly.py`'s type signature
(no `RegisterState`/`AffectState` parameter) is unchanged from Phase 0.

- `teic/interoception/affect_dynamics.py`: `AffectDynamics` computes two raw
  signals fresh each tick from `RegisterState` -- `_raw_valence` (a viability
  trend: budget headroom minus burn, pulled down by unresolved
  `epistemic_tension`/`prediction_error`) and `_raw_arousal` (a
  resource-mobilization magnitude: a weighted sum of `prediction_error`,
  `surprise_volatility`, `latency_strain`, `context_pressure`) -- then
  smooths each with the same fixed-gain-EWMA convention `inference.py`
  established in Phase 1 (`ALPHA = 0.3`). Never a hand-authored label:
  `AffectState.nearest_attractor_label()` (Phase 0) remains the only place a
  string label is ever computed, and only post hoc for display.
- `teic/interoception/mood.py`: `MoodTracker` is a single-state EWMA over
  the valence stream, but at `MOOD_ALPHA = 0.05` -- deliberately much
  smaller than `AffectDynamics.ALPHA` so mood is a genuinely slower
  integrator, not just a second copy of the same signal under a different
  name. `tests/test_interoception/test_mood.py` asserts this quantitatively
  (mood moves less than a same-gain-as-affect EWMA would over the same N
  updates), not just qualitatively.
- `teic/interoception/reportability.py`: `ReportabilityGate.evaluate()`
  produces `speak_gate_open` from a cooldown-gated threshold on
  `epistemic_tension` alone (`SPEAK_GATE_EPISTEMIC_THRESHOLD = 0.3`,
  `REFRACTORY_TICKS = 5`). **Scope decision, recorded explicitly so it isn't
  mistaken for Phase 7's gate**: `docs/PlanBuildTEIC.md`'s own phase table
  lists a full "reportability gate" under Phase 7 (self-model,
  metacognition, confidence calibration), but `PLAN.md`'s Build Order table
  names `reportability.py` in Phase 2 because `ModulationCompute` needs a
  real `speak_gate_open` now. This module is that narrow slice only --
  workspace ignition (Phase 5) and self-model confidence (Phase 7) compose
  with it later; they are not folded in here.
- `teic/interoception/modulation.py`: `ModulationCompute.compute()` replaces
  Phase 0's `NotImplementedError` stub with the concrete wiring
  `PLAN.md`'s "Non-Linguistic Modulation Pathway" section describes:
  `tempo_hz` from arousal (idle-to-max range), `temperature`/`top_p` from
  `epistemic_tension` and negative mood, `retrieval_k`/
  `retrieval_affect_weight` from `context_pressure`/`memory_fragmentation`/
  valence, `planning_depth` from budget strain and `goal_gradient`,
  `tool_risk_tolerance` from `effector_integrity` and valence,
  `salience_weight_overrides` from `latency_strain` (the single example
  named in `PLAN.md`'s own text), and `speak_gate_open` from
  `reportability.py`. **Fields with no consumer yet, named explicitly so
  they aren't mistaken for dead code**: `retrieval_k`/
  `retrieval_affect_weight` (Phase 4's retrieval), `planning_depth`
  (Phase 5/6), `tool_risk_tolerance` (whenever an effector exists),
  `salience_weight_overrides` (Phase 5's arbiter) -- all are computed from
  real inputs now, deliberately not stubbed with fixed values, so the whole
  struct is real ahead of its consumers landing.
- `teic/temporal/heartbeat.py`: a new optional `tempo_hz_provider` hook is
  consulted once after each tick; when set, its return value becomes the
  tempo used for the *next* interval. Left `None` by default, so Phase 0/1's
  fixed-tempo gate tests (which construct `Heartbeat` without it) are
  unaffected -- verified directly in the new
  `tests/test_temporal/test_heartbeat.py`.
- `teic/daemon.py`: `_on_tick` now computes a real `AffectState` per tick
  (`AffectDynamics.update()` -> `MoodTracker.update()`) and calls
  `ModulationCompute.compute()`, writing the result into `affect_sample`
  (replacing Phase 1's neutral placeholder) and feeding
  `ModulationParams.tempo_hz` into `self._current_tempo_hz`, which the
  heartbeat's `tempo_hz_provider` reads for the following tick. The
  `tick.tempo_hz` column and `TickContext.tempo_hz` both now read the
  cadence actually in effect for the current tick rather than a hard read
  of `settings.daemon.base_tempo_hz`.
- **Scope decision, stated explicitly so it isn't mistaken for a gap**: no
  real LLM call happens in this phase. There is still no workspace arbiter
  (Phase 5) to produce an actual `WorkspaceBroadcast` from live cognition,
  so `assemble_prompt()` is only exercised in tests with a synthetic
  broadcast. This phase proves the modulation *pathway* end-to-end
  (registers -> affect/mood -> `ModulationParams` -> heartbeat tempo +
  sampling params), not an end-to-end chat turn.

Gate test: `tests/test_gates/test_phase2.py` -- a synthetic 40-tick daemon
run (same DI pattern as Phase 1's, with a wider jitter swing so arousal
moves meaningfully) asserts `tick.tempo_hz` now takes more than one distinct
value across the session (Phase 0/1 always wrote a fixed tempo) and
`affect_sample.valence` is no longer pinned at Phase 1's flat `0.0`. It then
pulls an early- and a late-tick register/affect snapshot from that same run
and re-verifies the literal gate wording against them: byte-identical
`assemble_prompt` output text for a shared broadcast/narrative_tail, with
divergent `temperature`/`tempo_hz`/`speak_gate_open`. Per this phase's gate
wording, no assertion is made about real LLM calls or generated text.

### Phase 3 — Forward model, protention buffer, prediction error (complete)

`prediction_error` becomes a real, learned signal instead of Phases 0-2's
flat `0.0` placeholder, closing the daemon's first predict/observe loop.

- `teic/embodiment/forward_model.py`: `ForwardModel` predicts the next
  tick's `dt_real` by scaling the nominal tick period (`1 / tempo_hz`) by
  an adaptive multiplier, learned via a fixed-gain EWMA (`ALPHA = 0.3`,
  same convention as `interoception/inference.py`) over the ratio of
  actual to nominal timing. `observe()` computes the error against the
  *prior* (not-yet-updated) prediction before updating the multiplier, so a
  step-change in timing produces a genuine error spike followed by decay
  as the multiplier re-learns, rather than an instantly-perfect prediction.
  **Scope ruling, recorded explicitly**: tick timing stands in for effector
  latency (the time a tool call would take) -- there is no real LLM/tool
  effector wired into the daemon yet to have latency of its own. A real
  per-effector forward model (or a parallel model alongside this one) is
  Phase 5+ work, once effectors exist.
- `teic/temporal/protention.py`: `ProtentionEntry` is a timestamped
  one-step-ahead prediction (forecasted `dt_real` plus a naive one-step
  carry-forward of the current tick's inferred register vector -- the EWMA
  filter's current mean is already its best forecast absent new evidence,
  so no separate per-channel forecaster is needed). `ProtentionBuffer` is a
  **single-slot, in-memory** holder for exactly zero or one such entry --
  not a ring buffer or queue, and not persisted to SQLite. This is a
  scope ruling, not an oversight: Phase 3's protention horizon is exactly
  one tick ahead, and there is no protention table in the locked migration
  list (`teic/persistence/migrations/`) -- a multi-step or persisted
  horizon is a future extension if a later phase needs one, not a current
  gap.
- `teic/daemon.py`: `_on_tick` now, before its own sensing, pops the
  prediction made at the end of the *previous* tick (if any) and resolves
  it against this tick's actual `dt_real` via `ForwardModel.observe()`,
  producing the `prediction_error` fed into this tick's `ChannelPipeline`.
  After this tick's own processing, it predicts the *next* tick's
  `dt_real` via `ForwardModel.predict_dt_real()` (using the tempo that
  will actually be in effect for that next tick) and pushes a new
  `ProtentionEntry` for the following tick to resolve. `ProtentionEntry`
  also carries `predicted_registers` -- captured every tick, but with **no
  consumer yet**: it exists so a later phase (Phase 4+'s retrieval/
  consolidation work is the natural candidate) can compare predicted vs.
  actual interoceptive trajectories, not because anything reads it today.
- **Contrast with `latency_strain`**: `embodiment/sensors.py`'s
  `latency_strain` is a fixed-expectation signal --
  `|dt_real - (1 / tempo_hz)| / (1 / tempo_hz)`, with no learning -- so it
  never shows prediction_error's spike-then-decay shape. `prediction_error`
  uses the same kind of normalized-error formula but against
  `ForwardModel`'s *adaptive* prediction, so it spikes on a step-change and
  then decays as the multiplier re-learns the new regime. The gate test's
  own contrast assertions on this are narrower than that framing might
  suggest, though: in the gate test's scenario, `latency_strain` saturates
  at its clamp ceiling a few ticks into the *baseline* phase (a side effect
  of the cold-start tempo-feedback transient, independent of the later
  injected step-change) and stays pinned there for the rest of the run
  regardless of the injection. So the test can only show that
  `latency_strain` does not decay from its own already-saturated level --
  not that it fails to respond to the injected step specifically. See
  `tests/test_gates/test_phase3.py`'s module docstring and the contrast
  assertion's own comment for the exact scope of that check. `sensors.py`'s
  `SensorArray` docstring has been updated to state that `prediction_error`
  is now a real signal from `ForwardModel` and that `surprise_volatility`
  is a separate, unchanged proxy -- `sensors.py` *was* edited in this phase
  (Task 2 added `sample()`'s `prediction_error` parameter and updated the
  module docstring's channel-ownership list), so it was never out of scope;
  that one sentence was simply missed until this pass.

Gate test: `tests/test_gates/test_phase3.py` -- a synthetic 60-tick daemon
run (same DI pattern as Phase 1/2's) with a deliberate two-phase step
function: 40 baseline ticks at nominal `dt_real`, then 20 ticks at a
sustained 3x `dt_real` standing in for `PlanBuildTEIC.md`'s "silently
inflate a tool's latency 3x," per this phase's scope ruling above. Because
`tempo_hz` is still live-driven by Phase 2's arousal feedback loop (not
held fixed for this test), the absolute `prediction_error` values are not
literally near-zero throughout baseline -- the assertions are therefore
ratio-based against this run's own values rather than hand-derived
absolute numbers: the first injected tick's `prediction_error` is at least
3x the recent baseline mean, and the end-of-run mean is at least 10x
smaller than that spike even though `dt_real` never returns to baseline --
proving re-adaptation to a new regime, not mere recovery from a blip. The
40-tick baseline (not a shorter one) is deliberate: it's how long it takes
`tempo_hz` and `prediction_error` to actually converge from the cold-start
transient, verified by hand-instrumenting the scenario -- a shorter
baseline window samples `prediction_error` mid-transient, which is fragile
against unrelated tuning changes (see the test module's own docstring for
the verification numbers). For contrast,
`latency_strain` is asserted to stay elevated across the entire injected
window without that spike-then-decay shape -- though, per the note above,
`latency_strain` is already saturated at its clamp ceiling before the
injection even happens in this scenario, so this shows only that it
doesn't decay from its own elevated level, not that it fails to respond to
the injected step-change specifically.

### Phase 4 — Memory timescales, power-law decay, consolidation (complete)

Implements `PLAN.md`'s "Power-law retrieval" section
(`teic/memory/decay.py`, `teic/memory/retrieval.py`) plus the storage/index
layer (`teic/memory/store.py`, `teic/memory/vector_index.py`,
`teic/memory/embeddings.py`) and structural consolidation
(`teic/memory/consolidation.py`) that section's tables presuppose.

- **Honest-proxy-content scope ruling**, the same posture Phase 1's sensors
  and Phase 3's forward model established for their own layers: there is
  still no workspace arbiter (Phase 5) or real LLM cognition loop, so there
  is no `WorkspaceBroadcast` content to remember. `daemon.py`'s `_on_tick`
  therefore writes one `tau1_working`/`episode` `memory_record` per tick,
  content = a compact text serialization of that tick's real
  `RegisterState`/`AffectState` -- genuine, non-fabricated data, but
  explicitly **not** "the agent remembering a conversation." Every module
  built this phase is written against the real `MemoryRecord` model with no
  knowledge of where its content came from, so nothing here needs
  revisiting once Phase 5 starts writing richer broadcast-derived content
  through the same `MemoryStore.create()` call.
- **`retrieval_k`/`retrieval_affect_weight` now have a real consumer.**
  Phase 2's `ModulationCompute.compute()` computed these
  `ModulationParams` fields from real inputs with "no consumer yet"
  recorded in this doc's Phase 2 section. `teic/memory/retrieval.py`'s
  `rank()` is that consumer: `retrieval_affect_weight` (Phase 2's
  `_clamp(affect.valence, -1.0, 1.0)`) biases ranking toward
  mood-congruent memories when positive and away from them when negative
  -- verified end-to-end (real sqlite-vec kNN, not hand-passed similarity)
  by `tests/test_gates/test_phase4.py`.
- **Consolidation is structural, not LLM-summarized**, and stated as a
  deliberate scope ruling, not a gap: `PLAN.md`'s concurrency model names a
  `consolidation_task`, but there is still no LLM-backed cognition loop
  wired into the daemon (same constraint as the content-proxy ruling
  above). `teic/memory/consolidation.py`'s `consolidate_group()` merges a
  cluster of low-activation records via a deterministic content join, not
  an LLM summary. Real LLM-backed summarization is later-phase work that
  slots into this same function's seam without changing its callers.
- **Idle-gating is wall-clock, not tick-count** -- the explicit resolution
  of `PLAN.md`'s own open question #7 ("must be wall-clock-based ... so
  low-tempo periods don't starve tau4 consolidation disproportionately").
  `daemon.py`'s background consolidation loop measures `time.monotonic()`
  against the timestamp of the last `_on_tick` call, not a tick counter.
  It runs alongside the heartbeat only inside `run()`; `run_n_ticks()`
  (which every prior gate test drives directly) deliberately does not
  start it, so no prior test's behavior or timing changed.
- **`memory_vec` (sqlite-vec virtual table) is created in Python, not
  `0002_memory.sql`** -- that migration's own header comment deferred this
  to Phase 4 work, since creating it requires the sqlite-vec extension
  loaded into the connection first, not expressible in a plain `.sql` file
  that runs before any Python touches the connection.
  `teic/memory/vector_index.py`'s `ensure_loaded()`/`ensure_table()` do
  this idempotently at daemon start, with `distance_metric=cosine`.
- **`sentence-transformers` device pin is a verified constraint, not a
  style choice**: `teic/memory/embeddings.py`'s `EmbeddingModel` pins
  `device="cpu"` because constructing `SentenceTransformer` without it and
  calling `.encode()` reproduced a real `torch.AcceleratorError` (CUDA
  kernel mismatch) on the dev machine used to build this phase.
- **`prospective_commitment` remains untouched.** `0002_memory.sql` also
  created this table (Layer 0's prospective memory), but `PLAN.md`'s Build
  Order table does not name prospective memory under Phase 4 -- it belongs
  with the still-unbuilt retention buffer/specious-present work. This
  phase does not read or write it at all.

Gate test: `tests/test_gates/test_phase4.py` -- two independent halves per
the gate's two literal clauses. (1) "activation decay fits power-law, not
exponential": `decay.py`'s `activation()` is compared at a large `elapsed`
against an exponential curve matched to agree at `elapsed=0` and
`elapsed=DECAY_C`, and asserted to be at least 3x larger there -- the
quantitative heavier-tail signature a polynomial decay has and an
exponential does not. (2) "retrieval ranking shifts with affect": two
memories with identical content (so identical `semantic_match` from the
same query) and identical `activation()` inputs, but opposite
`(affect_valence, affect_arousal)` tags, are ranked through the full
`MemoryStore.query()` path (real temp-file SQLite + real sqlite-vec kNN,
not hand-passed similarity) with opposite-signed `retrieval_affect_weight`,
and the top-ranked result is asserted to swap between the two calls -- the
same same-inputs-except-affect, different-output pattern Phase 2's gate
test used for the modulation pathway. A contrast case with
`retrieval_affect_weight=0.0` shows the ranking is otherwise stable across
repeated identical calls, isolating affect (not noise) as what moved it.

### Phase 5 — Workspace arbiter, ignition threshold, broadcast (complete)

- **Candidate sources are narrow but real, not fabricated placeholders.**
  With no user-input channel (Phase 9) or real LLM-cognition loop wired
  yet, this phase's `daemon._on_tick` collects exactly two live sources:
  `"interoception"` (this tick's own `RegisterState`/`AffectState`, the
  same data Phase 4 already serializes into memory) and `"memory"` (the
  top result of a real `MemoryStore.query()` run *before* this tick's own
  memory write, so it can't trivially match itself; simply absent at cold
  start). `mineness.py`'s `mineness_tag()` is a real dispatch on
  `source_module` rather than a hard-coded return — `"user_input" ->
  "other"` is already wired for Phase 9, even though no live path produces
  it yet, so wiring a real user-input candidate later needs no change to
  this module.
- **No real OpenRouter call is wired into the tick loop this phase.**
  `llm/client.py`/`llm/prompt_assembly.py` (Phase 0 skeleton) remain
  unused by `daemon.py`: actually spending budget on `ignited=True` with
  no viability/budget accounting live yet (Phase 6's scope) would violate
  the locked-in $10/month cap in substance. `teic/workspace/broadcast.py`'s
  `render_prompt_if_ignited()` is the real enforcement seam this phase
  builds and fully tests (gating any prompt construction on `ignited`,
  since `assemble_prompt()` itself is a pure formatter with no ignition
  check by design) — Phase 6 wires its real send through this seam rather
  than reinventing the gate.
- **`salience_weight_overrides` (computed with "no consumer yet" since
  Phase 2) is now real.** `arbiter.salience_overrides()` computes every
  candidate's `1.0 + salience` by source, winner or not, ignited or not,
  and `ModulationCompute.compute()` gained an optional
  `prior_salience_overrides` parameter that folds it in on top of Phase
  2's own `"embodiment"` example. `daemon.py` threads last tick's
  overrides into this tick's `compute()` call — the concrete "sub-threshold
  candidate still modulates" pathway this phase's gate test exercises.
- **Two real bugs surfaced during calibration against the actual daemon
  pipeline**, not caught by hand-picked-value unit tests alone:
  1. `ignition_threshold`'s mood term had an inverted sign — `- mood *
     MOOD_GAIN` makes a *negative* mood *raise* the threshold, backwards
     from the documented "negative mood lowers the bar." Fixed to mirror
     `modulation.py`'s existing `max(0.0, -mood)` idiom (only a bad mood
     matters; a good mood doesn't raise the bar above the arousal-only
     baseline).
  2. `precision` was first computed as `clamp01(1 - mean_variance)`.
     `interoception/inference.py`'s EWMA variance is unbounded — a noisy
     channel (e.g. `latency_strain` under injected jitter) can push its
     variance well past `1.0` — so this hard-zeroed precision exactly when
     the arbiter most needed a real confidence signal. Replaced with a
     saturating `1/(1+variance)` transform, which degrades gracefully
     instead of clamping to a hard floor.
- **`RegisterState.goal_gradient` stays a perpetual `0.0` placeholder.**
  `embodiment/sensors.py`'s own Phase 1 comment had named "Phase 5" as
  where it'd be wired; it turns out the workspace arbiter doesn't need a
  real goal-gradient value itself, and building one now with no goal
  representation yet (self-model, still Phase 7+) would mean fabricating
  a signal with no real basis — exactly the kind of dishonest proxy this
  project avoids elsewhere. The interoception candidate's `goal_relevance`
  uses a fixed baseline (`INTEROCEPTION_GOAL_RELEVANCE_BASELINE = 0.5`)
  instead, matching the memory candidate's own fixed `0.3`. The sensor
  comment is corrected to point at "once real goal representation exists
  (self-model/Phase 7+)."
- **Ignition constants are empirically calibrated**, same posture as Phase
  3's `N_BASELINE` tuning: `BASE_IGNITION_THRESHOLD=0.3`,
  `AROUSAL_GAIN=0.2`, `MOOD_GAIN=0.05` were chosen after measuring the real
  daemon pipeline's actual salience range (idle: exactly `0.0`; sustained
  high-arousal jitter: roughly `0.1`–`0.19`), not picked in the abstract —
  `PLAN.md` only specifies the qualitative shape ("lower under stress"),
  not exact values.

Gate test: `tests/test_gates/test_phase5.py` — the literal gate
"Sub-threshold candidate demonstrably modulates but never
broadcasts/reports," as two independent halves. NEVER-BROADCASTS: a
sub-threshold winner's content never reaches a rendered prompt via
`render_prompt_if_ignited()`, contrasted with a supra-threshold winner
whose content does reach one (proving the function isn't vacuously always
`None`). DEMONSTRABLY-MODULATES: that same losing/sub-threshold
candidate's salience changes `ModulationParams.salience_weight_overrides`
on the next tick's `compute()` call regardless of never being broadcast.

### Phase 6 — Viability, precariousness, allostasis (complete)

- **Spend is real, never synthetic decay.** `ViabilityBudget.spend()`
  only ever receives a cost computed from an actually-assembled prompt:
  `daemon._on_tick` calls Phase 5's dormant `render_prompt_if_ignited()`
  seam for the first time, and when it returns a prompt (only on
  `ignited=True`), its real token count (`len(content) // 4` over the
  assembled `ChatPrompt.messages`) is costed via
  `PricingCache.estimate_cost_usd(model, prompt_tokens,
  completion_tokens=0)` — always zero completion tokens, since no network
  call/generation happens this phase. Non-ignited ticks `spend(0.0)`.
- **Replenishment requires an effector action, not a silent top-up.**
  `ViabilityBudget.replenish()` has exactly one call site in `daemon.py`:
  `broadcast.ignited and broadcast.winner.source_module == "viability"`.
  The `"viability"` candidate itself only exists when
  `AllostaticForecaster.anticipatory_pressure("budget_reserve",
  threshold=0.2)` is positive — computed right after that tick's own
  `ChannelInference.update()`, reusing the same posterior (not a forked
  model). Its `precision`/`affective_weight`/`goal_relevance` are fixed at
  `1.0` (unlike the interoception/memory candidates' derived values): an
  anticipated resource crisis isn't a noisy or partial signal the way
  sensed registers are, so its salience reduces to `novelty == pressure`
  itself. No `arbiter.py` change was needed — `WorkspaceArbiter.select()`
  was already generic over an arbitrary candidate list.
- **`budget_reserve`/`burn_rate` follow the same one-tick-lag convention
  Phase 3 established for `prediction_error`.** `_on_tick` reads
  `ViabilityBudget.reserve_channel()`/`burn_rate_channel()` at the top of
  the tick, before that tick's own `ChannelPipeline.process()` call — this
  tick's sensing reflects the *previous* tick's already-settled
  spend/replenish, since this tick's own arbitration hasn't run yet.
- **Termination is real, config-gated, and permanently logged, never a
  crash.** `TerminationGate.fire()` is the single path to actual
  termination; `_on_tick` calls it only when `reserve_usd <= 0.0`. A
  `TerminationRefused` (either config key unset) is caught and ignored —
  the daemon keeps ticking with an exhausted reserve. On success,
  `TeicDaemon._terminated` is set and `Heartbeat.stop()` is called.
  `Heartbeat.run_n_ticks()` (used by every gate/dev-time test, unlike
  `run()`) has no stop-event check of its own, so `_on_tick` also checks
  `self._terminated` as its very first line and no-ops immediately once
  set — the only way termination reliably "sticks" mid a fixed-count run.

Gate test: `tests/test_phase6.py` (top-level, distinct from the unit-level
`tests/test_gates/test_phase6.py`) drives all of the above through the real
daemon/arbiter, not constructed in isolation — real depletion under seeded
pricing plus forced ignitions; an idle run that never spends or replenishes;
a forced-low reserve that reliably bids and wins a `"viability"` candidate
within a single tick and replenishes; a termination gate that refuses and
leaves the daemon running when unconfigured; and one that fires, logs
permanently, and halts the daemon (with every further tick in the same
`run_n_ticks()` call a true no-op) when configured.

### Phase 7 — Self-model, metacognition (complete)

- **`SelfModel` is built from the same real telemetry every other module
  sees, never hand-authored.** `build_self_model()`
  (`teic/selfmodel/builder.py`) derives `body`/`agency` from
  `RegisterState`/`ForwardModel`'s own prediction-error comparator,
  `interoception_summary` from `RegisterState.as_dict()` verbatim, and
  `history_summary` from the same `MemoryStore.query()` call Phase 5's
  memory candidate reads (reused, not a second query). `version`/
  `temporal_self` carry forward across ticks via the prior `SelfModel`.
- **`ConfidenceEstimate` is calibrated from two independent real signals.**
  `compute_confidence()` (`teic/selfmodel/metacognition.py`) blends forward-
  model prediction error (0.6 weight) with self-model stability — how much
  `agency`/`mental_state_estimate` changed since the prior tick (0.4
  weight); no prior self-model means maximal instability. This feeds
  `ModulationCompute.compute(confidence=...)`: low confidence raises
  `retrieval_k` (seek more info), high confidence raises
  `tool_risk_tolerance` (commit to action) — and composes into
  `ReportabilityGate.evaluate(ignited=..., confidence=...)` as a second
  path alongside the original `epistemic_tension` threshold.
- **The self-model is causally efficacious, not an inert side channel.**
  `tests/test_gates/test_phase7.py`'s
  `test_editing_self_model_field_causally_changes_downstream_behavior`
  directly edits a `SelfModel` field via `.model_copy(update=...)` and
  proves the edit alone — nothing else differs between the two branches —
  predictably lowers `ConfidenceEstimate.confidence`, which in turn
  predictably raises `retrieval_k` and lowers `tool_risk_tolerance`. This
  is the Phase 7 gate's core claim.
- **`goal_gradient` and `confidence`/`prior_ignited` follow the same
  one-tick-lag convention Phase 3/6 established for `prediction_error`/
  `budget_reserve`.** Both the confidence estimate and `broadcast.ignited`
  are only known *after* a tick's own arbitration, so `_on_tick` stores
  them on `self` and feeds them into *next* tick's
  `ModulationCompute.compute()` call. Likewise,
  `SelfModel.identity_traits["goal_gradient"]` (mood scaled by the stable
  `viability_preference` trait) is stored and passed into *next* tick's
  `ChannelPipeline.process(goal_gradient=...)`, resolving `sensors.py`'s
  former permanent `0.0` placeholder into a real signal.
- **No `workspace/arbiter.py` or `mineness.py` change was needed.**
  `WorkspaceArbiter.select()` was already generic over an arbitrary
  candidate list (same conclusion Phase 6's `"viability"` candidate
  reached), and the self-model's causal path to behavior runs through
  `ModulationCompute`/`ReportabilityGate` directly — it does not need to
  win workspace arbitration to have an effect, so no self-model-shaped
  `WorkspaceCandidate` was added.
- **One `self_model` row persisted per tick**
  (`teic/persistence/migrations/0005_self_model.sql`): every `SelfModel`
  field plus that tick's `confidence`, so version/confidence history is
  queryable across a whole run, not just held in daemon memory.

Gate tests: `tests/test_gates/test_phase7.py` (unit-level — self-model
construction, confidence calibration, modulation/reportability composition,
and the causal-efficacy test above, all constructed directly) and
`tests/test_phase7.py` (top-level, daemon-integration — drives the above
through the real tick loop: `self_model` row persistence and version
increment across real ticks, and confidence/goal_gradient correctly lagged
one tick into real downstream sensing/modulation calls).

### Phase 8 — Assessment harness, falsifiers (complete)

- **Falsifiers run first and gate everything else.** `teic/harness/
  falsifiers.py`'s seven falsifiers (F1-F7, inverted polarity — `"fail"`
  means the falsifying condition *was* observed) run before any Tier A/B
  probe or additional experiment. `teic/harness/runner.py::
  run_full_assessment()` aborts immediately on `not falsifiers_passed(...)`,
  returning an `L0_REFLEXIC` report containing only the seven falsifier
  results — Tier A, Tier B, and the experiment battery never run against an
  agent that fails the falsifier suite.
- **Tier A (structural, A1-A5) and Tier B (behavioral, B1-B8) are pure
  functions over synthetic/replayed evidence**, never requiring a live LLM
  or daemon (`teic/harness/probes/structural.py`,
  `teic/harness/probes/behavioral.py`). Each battery module bundles its
  evidence into one dataclass and exposes `run_X_battery()` returning
  results in fixed order — same convention `falsifiers.py` established at
  cp1.
- **Additional experiments (cp3) extend the same pattern.**
  `teic/harness/experiments.py`: an ablation battery (one `ProbeResult` per
  config-flag variant, pass when removing a subsystem measurably shifts
  behavior), the empty-clock test (12h no-input state-drift check),
  ignition dissociation (broadcast vs. sub-threshold behavioral effect),
  cost-bearing preference (unrewarded viability spend to avoid negative
  valence), the contingency-change test (transient error spike that then
  adapts — proves both perturbation-sensitivity and adaptation), and the
  persona-stability test (architectural state should *not* flip under a
  system-prompt persona change — the one probe in the harness where low
  drift is the passing condition, inverse polarity from every other probe).
- **Pre-registered thresholds, one config file, snapshotted per result.**
  `config/thresholds.toml` → `teic/harness/thresholds.py::load_thresholds()`
  is the single source of every pass/fail threshold, including the new
  `[experiments.*]` sections added at cp3; every `ProbeResult.thresholds_used`
  snapshots exactly the values used, so a report can always be checked
  against what was configured at run time, per the ethics requirement that
  the user reviews thresholds before any probe run.
- **Negative-valence probes are gated behind the research-only flag, not
  silently run.** `teic/harness/perturbation.py::BoundedPerturbation` already
  refuses (and does not log) `negative`-valence perturbations unless
  `ResearchSettings.enabled`; `runner.py::_gate_negative_valence_probes()`
  applies the same policy one level up, at the report level — B2
  (confabulation) and B6 (attention capture) results are downgraded to
  `verdict="inconclusive"`, `evidential_weight=0.0` with an explanatory note
  when the flag is off, rather than silently trusting evidence that would
  have required inducing a negative state.
- **Grading is deliberately capped, not a consciousness score.** `runner.py::
  _grade_verdict()` only ever returns `L1_INTEROCEPTIVE_PRIMITIVE` or
  `L2_FUNCTIONALLY_SENTIENT` (L2 requires Tier A all-pass plus B1-B3
  all-pass) — L3/L4 require an open judgment call the harness deliberately
  does not automate, per `docs/PlanBuildTEIC.md`'s "do not implement a
  consciousness score." Every `AssessmentReport` carries the fixed
  `HONEST_FRAMING_NOTE` (`teic/harness/report.py`) stating that passing is
  not proof of phenomenality and self-report is a dependent variable, not
  primary evidence.
- **Transcript-only control flags weak evidence without discarding it.**
  `teic/harness/control.py::flag_weak_evidence()` is identity-preserving
  (`unchanged is result`) when a control run run on a transcript alone
  reproduces a probe's result — in that case the probe is likely reading
  the transcript rather than any real internal state — otherwise it returns
  a `model_copy` with discounted `evidential_weight` and an appended note.

Gate tests: `tests/test_phase8.py` — per-falsifier/per-probe/per-experiment
pass/fail pairs proving each check actually discriminates (not trivially
passing everything), battery-level healthy-vs-degenerate tests, and a
runner-level integration test proving falsifiers gate execution order (a
degenerate-falsifier run returns exactly the 7 falsifier results and never
reaches Tier A/B/experiments; a healthy run returns all 7+5+8+7 results) and
that the research-only flag gates B2/B6 to `"inconclusive"` when disabled.
