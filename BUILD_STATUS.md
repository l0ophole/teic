# Build Status

| Phase | Status |
|---|---|
| 0 — Daemon skeleton | **Complete** |
| 1 — Telemetry → interoceptive vector | **Complete** |
| 2 — Non-linguistic modulation (real gate) | **Complete** |
| 3 — Forward models, prediction error | **Complete** |
| 4 — Memory timescales, decay, consolidation | **Complete** |
| 5 — Workspace arbiter, ignition | **Complete** |
| 6 — Viability, allostasis | Not started |
| 7 — Self-model, metacognition | Not started |
| 8 — Assessment harness + falsifiers | Not started |
| 9 — UI (terminal + web) | Not started |

## Phase 0 — complete

- [x] git repo initialized
- [x] `pyproject.toml`, package skeleton, migrations, settings
- [x] Verify OpenRouter model slugs against `/models` (done — see ARCHITECTURE.md)
- [x] `pip install -e ".[dev]"` completes cleanly
- [x] `pytest` passes (3 tests: phase-0 gate x2, prompt_assembly regression guard)
- [x] `mypy` passes on `teic/models`, `teic/interoception`, `teic/workspace`, `teic/llm`
- [x] Manual smoke test: `python -m teic` — clean start, ticks persisted, clean SIGTERM shutdown
- [x] Fixed a real bug found during manual verification: `run_migrations` used
      `executescript`, which implicitly commits before running, so a
      process killed mid-migration left partially-applied DDL with no
      `schema_migrations` record and could not recover on restart. Fixed by
      opening the connection with `isolation_level=None` and applying each
      migration's statements individually inside one explicit
      `BEGIN`/`COMMIT` (rolled back on any exception).
- [x] First commit

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
python -m teic   # Ctrl+C after a few seconds; check data/teic.db has tick rows
```

## Phase 1 — complete

- [x] `teic/embodiment/sensors.py`: `SensorArray`/`RawSensorSample` -- real
      `latency_strain` (tick timing jitter) and `context_pressure` (pending
      input volume), derived `surprise_volatility`, every other channel a
      documented placeholder until the phase that wires it
- [x] `teic/interoception/inference.py`: `ChannelInference`, a per-channel
      fixed-gain EWMA mean/variance filter turning raw samples into a
      calibrated `RegisterState` (never hand-authored)
- [x] `teic/interoception/channels.py`: `ChannelPipeline` composing one
      `SensorArray` + one `ChannelInference` per session, exposing
      `process(tick_ctx, tick_id, ts) -> RegisterState` plus `last_raw` for
      the raw sample that produced it
- [x] `teic/daemon.py`: `_on_tick` builds a real `TickContext` per cycle and
      writes real `raw_value`/`inferred_value`/`inferred_var` into
      `register_sample` via `ChannelPipeline`; `affect_sample` stays the
      neutral Phase 0 placeholder on purpose (affect dynamics/mood are
      Phase 2's job)
- [x] `pytest` passes (14 tests: Phase 0 gate x2, Phase 1 gate, prompt_assembly
      regression guard, plus Task 1's sensor/inference unit tests)
- [x] `mypy` passes project-wide (bare `mypy`, no args)
- [x] Gate test: `tests/test_gates/test_phase1.py` -- synthetic 30-tick run
      with a deterministic non-constant `dt_real` jitter sequence, asserting
      `register_sample` row count, and that `latency_strain`'s
      `inferred_value`/`inferred_var` actually move across ticks (not
      Phase 0's flat `0.0`). No assertion on LLM calls or generated text --
      out of scope per this phase's gate wording.

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
```

## Phase 2 — complete

**Hard stop for user check-in per `PLAN.md`** -- do not begin Phase 3 without
the user's go-ahead; this phase is the spec's explicitly-named "real gate."

- [x] `teic/interoception/affect_dynamics.py`: `AffectDynamics`, a per-session
      fixed-gain EWMA (alpha=0.3) over two raw signals computed fresh each
      tick from `RegisterState` -- `_raw_valence` (viability trend, pulled
      down by unresolved tension/error) and `_raw_arousal` (resource-
      mobilization magnitude) -- never a hand-authored label.
- [x] `teic/interoception/mood.py`: `MoodTracker`, a single-state EWMA over
      valence at a deliberately much smaller gain (`MOOD_ALPHA = 0.05`) than
      `AffectDynamics`, so mood genuinely lags rather than tracking valence
      tick-for-tick.
- [x] `teic/interoception/reportability.py`: `ReportabilityGate`, a
      cooldown-gated threshold on `epistemic_tension` (`REFRACTORY_TICKS =
      5`, `SPEAK_GATE_EPISTEMIC_THRESHOLD = 0.3`) producing `speak_gate_open`.
      **Scoped narrowly to Phase 2** -- see `docs/plans/phase2-plan.md`'s
      scope ruling on the Phase 2 vs. Phase 7 reportability tension; workspace
      ignition (Phase 5) and self-model confidence (Phase 7) are not
      incorporated yet.
- [x] `teic/interoception/modulation.py`: `ModulationCompute.compute()` is no
      longer a `NotImplementedError` stub -- every `ModulationParams` field
      is now derived concretely from `(registers, affect, mood)` per
      `PLAN.md`'s "Non-Linguistic Modulation Pathway" section. Several fields
      (`retrieval_k`, `retrieval_affect_weight`, `planning_depth`,
      `tool_risk_tolerance`, `salience_weight_overrides`) are computed for
      real but have no consumer until Phases 4/5/6.
- [x] `teic/temporal/heartbeat.py`: new optional `tempo_hz_provider` hook,
      consulted after each tick so its return value becomes the *next*
      interval -- default `None` leaves Phase 0/1's fixed-tempo behavior
      unchanged.
- [x] `teic/daemon.py`: `_on_tick` now computes a real `AffectState` via
      `AffectDynamics`/`MoodTracker` and real `ModulationParams` via
      `ModulationCompute`, writes them into `affect_sample` (replacing Phase
      1's neutral placeholder), and feeds `ModulationParams.tempo_hz` back
      into the heartbeat via `tempo_hz_provider` for the next tick.
- [x] `pytest` passes (28 tests: prior phases' gates + Phase 2 gate, plus new
      unit tests for `affect_dynamics`/`mood`/`reportability`/`modulation`/
      `heartbeat`'s tempo feedback)
- [x] `mypy` passes project-wide (bare `mypy`, no args)
- [x] Gate test: `tests/test_gates/test_phase2.py` -- a synthetic 40-tick
      daemon run with a wider jittered `dt_real` sequence than Phase 1's
      asserts `tick.tempo_hz` now takes more than one value (Phase 0/1 always
      wrote a fixed tempo) and `affect_sample.valence` is no longer pinned at
      Phase 1's flat `0.0`; it then pulls an early- and a late-tick
      register/affect snapshot from that same run and re-verifies the
      literal gate wording -- identical `assemble_prompt` output text with a
      byte-identical broadcast/narrative_tail, divergent
      temperature/tempo_hz/speak-gate. No assertion on real LLM calls or
      generated text -- there is still no workspace/arbiter wiring an actual
      chat turn (Phase 5+); this phase proves the modulation *pathway*.

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
```

## Phase 3 — complete

- [x] `teic/embodiment/forward_model.py`: `ForwardModel`, an adaptive
      fixed-gain EWMA (`ALPHA = 0.3`) predictor of tick-timing latency --
      learns the ratio of actual `dt_real` to nominal tick period
      (`1 / tempo_hz`) so a sustained step-change in tick timing produces a
      transient `prediction_error` spike that decays as the model
      re-learns the new regime. **Scope ruling**: tick timing stands in for
      effector latency -- there is no real LLM/tool call yet to have
      latency of its own; a real per-effector forward model is Phase 5+
      work.
- [x] `teic/temporal/protention.py`: `ProtentionEntry`/`ProtentionBuffer`, a
      **single-slot, in-memory, one-tick-ahead** prediction buffer holding
      the forecasted next-tick `dt_real` plus a naive one-step
      carry-forward of the current register vector. Not persisted and not
      a ring buffer -- there is no protention table in the locked migration
      list, and Phase 3's protention horizon is exactly one tick; a
      multi-step/persisted horizon is a future extension, not a current
      gap.
- [x] `teic/daemon.py`: `_on_tick` now resolves last tick's pending
      prediction (if any) against this tick's real `dt_real` via
      `ForwardModel.observe()`, producing a genuinely learned
      `prediction_error` fed into `ChannelPipeline` -- replacing Phases
      0-2's flat `0.0` placeholder -- then predicts the *next* tick's
      `dt_real` and pushes a new `ProtentionEntry` (including
      `predicted_registers`, captured each tick but with **no consumer
      yet** -- Phase 4+'s retrieval/consolidation is the eventual consumer,
      wanting to compare predicted vs. actual interoceptive trajectories).
- [x] `pytest` passes (38 tests: prior phases' gates + Phase 3 gate, plus
      `tests/test_daemon.py` (Task 2's smaller-scope unit-style check of
      the same wiring) and new unit tests for `forward_model`/`protention`)
- [x] `mypy` passes project-wide (bare `mypy`, no args)
- [x] Gate test: `tests/test_gates/test_phase3.py` -- a synthetic
      60-tick daemon run with a deliberate two-phase step function (40
      baseline ticks at nominal `dt_real`, then 20 ticks at a sustained 3x
      `dt_real`, standing in for `PlanBuildTEIC.md`'s "silently inflate a
      tool's latency 3x" per this phase's scope ruling) asserts
      `prediction_error` spikes at least 3x above its recent baseline mean
      on the first injected tick, then decays back down well below that
      spike by the end of the run even though `dt_real` never returns to
      baseline -- proving the model re-adapts to the new regime rather than
      just recovering from a blip. The 40-tick baseline is sized so
      `tempo_hz`/`prediction_error` have actually converged from the
      cold-start transient by the time the baseline window is sampled
      (verified by hand-instrumenting the scenario; a shorter baseline
      samples mid-transient and is fragile against unrelated tuning
      changes). For contrast, `latency_strain` (the fixed-expectation,
      non-adaptive sibling signal) is asserted to stay elevated across the
      entire injected window without that spike-then-decay shape -- though
      in this scenario `latency_strain` is already pinned at its clamp
      ceiling from the cold-start transient several ticks before the
      injection even happens, so this shows only that it doesn't decay
      from its own elevated level, not a response to the injected step
      specifically. See the test module's own docstring for the full
      caveat and the verification numbers.

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
```

## Phase 4 — complete

- [x] `teic/memory/decay.py`: `activation()` implements `PLAN.md`'s
      power-law formula verbatim (`base_activation * (1 + elapsed/DECAY_C)
      ** (-decay_alpha)`, tick-id-based elapsed) -- verified quantitatively
      against a matched exponential to have a heavier tail, not just
      "decreasing." `touch()` resets the decay clock on read without
      touching `base_activation`, per `PLAN.md`'s "lossy by design"
      requirement even for reinforced memories.
- [x] `teic/memory/retrieval.py`: `rank()` implements `score = activation *
      semantic_match * affective_tag_weight(current_affect)`. **This is the
      consumer Phase 2's `retrieval_k`/`retrieval_affect_weight`
      (`ModulationParams`) were computed for with "no consumer yet"** --
      they now actually bias ranking toward (positive valence) or away
      from (negative valence) mood-congruent memories.
- [x] `teic/memory/embeddings.py`: `EmbeddingModel` wraps
      `sentence-transformers/all-MiniLM-L6-v2`, pinned to `device="cpu"` --
      a **verified** constraint (reproduced `torch.AcceleratorError`
      without the pin on this machine), not a style choice. Lazy
      construction so importing the module stays offline-safe.
- [x] `teic/memory/vector_index.py`: creates the `memory_vec` sqlite-vec
      virtual table `0002_memory.sql`'s header comment deferred to this
      phase (needs the extension loaded into the connection first), with
      `distance_metric=cosine`.
- [x] `teic/memory/store.py`: `MemoryStore` composes the above with real
      SQL -- `create()` persists a record + embedding, `query()` runs a
      real kNN then re-ranks via `retrieval.rank()`, reinforcing
      (`touch()`-ing) every returned result.
- [x] `teic/memory/consolidation.py`: **structural, not LLM-summarized**
      consolidation (no cognition loop exists yet -- see scope ruling 2 in
      `docs/plans/phase4-plan.md`) -- `consolidate_group()` deterministically
      joins low-activation records' content into one `tau4_consolidated`
      record and marks sources `superseded_by` it. Idle-gating is
      **wall-clock**, per `PLAN.md`'s own open question #7, not tick-count.
- [x] `teic/daemon.py`: `_on_tick` writes one real `tau1_working` memory
      record per tick from that tick's `RegisterState`/`AffectState` (the
      honest-proxy-content pattern Phase 1/3 established for their layers
      -- not real cognition, that's Phase 5+ once the workspace arbiter
      exists). `run()` (not `run_n_ticks()`, which every gate test drives
      directly and stays unmodified) also runs a background wall-clock-
      idle-gated consolidation loop alongside the heartbeat.
- [x] `prospective_commitment` (also created by `0002_memory.sql`) is
      untouched this phase -- it belongs with Layer 0's still-unbuilt
      retention buffer/specious present/prospective memory work, not
      Phase 4's Build Order scope.
- [x] `pytest` passes (59 tests: prior phases' gates + Phase 4 gate, plus
      new `teic/memory` unit/integration tests and two extended
      `tests/test_daemon.py` cases)
- [x] `mypy` passes project-wide (bare `mypy`, no args; added
      `teic/memory` to `pyproject.toml`'s mypy `files` list and a
      `sqlite_vec` `ignore_missing_imports` override -- no published stubs)
- [x] Gate test: `tests/test_gates/test_phase4.py` -- two independent
      halves per the gate's two clauses. (1) `activation()`'s value at a
      large `elapsed` is asserted at least 3x a matched exponential's value
      there -- the quantitative heavier-tail signature of a power law.
      (2) two memories with identical content/activation but opposite
      affect tags are ranked through the full `MemoryStore.query()` path
      (real sqlite-vec kNN, not hand-passed similarity) with opposite-signed
      `retrieval_affect_weight`, and the top result is asserted to swap --
      proving affect state, not noise, drives the ranking (a contrast case
      with `retrieval_affect_weight=0.0` shows the ranking is otherwise
      stable). Manually verified via `python -m teic`: real `tau1_working`
      rows land in `memory_record` with the documented content format.

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
python -m teic   # Ctrl+C after a few seconds; check memory_record has tau1_working rows
```

## Phase 5 — complete

- [x] `teic/workspace/arbiter.py`: `WorkspaceArbiter.select()` implements
      `PLAN.md`'s `salience = novelty * precision * affective_weight *
      goal_relevance` (already a `WorkspaceCandidate` property since Phase
      0) with `max()` over the tick's candidates as the one winner, and
      `ignited = winner.salience >= ignition_threshold(affect, mood)`.
      `ignition_threshold()` lowers under arousal and negative mood only
      (mirrors `modulation.py`'s existing `max(0.0, -mood)` idiom — a good
      mood never raises the bar above the arousal-only baseline).
      `salience_overrides()` folds every candidate's salience — winner or
      not, ignited or not — forward for the daemon to feed into next
      tick's `ModulationParams`.
- [x] `teic/workspace/mineness.py`: `mineness_tag()` is a real dispatch on
      `source_module`, not a hard-coded constant — only `"self"` is
      reachable this phase (both live sources are agent-internal), but
      `"user_input" -> "other"` is already wired so Phase 9's real
      user-input candidate needs no change here. No live source produces
      `"ambiguous"` yet — an honest gap, not a stub.
- [x] `teic/workspace/broadcast.py`: `render_prompt_if_ignited()` is the
      actual "never broadcasts/reports below threshold" enforcement
      point — `assemble_prompt()` (Phase 0) is a pure formatter with no
      `ignited` check of its own by design, so this seam is where ignition
      really gates content reaching a renderable prompt. `daemon.py`
      doesn't call it yet (see next bullet) but it's fully tested now, so
      Phase 6 has a real, already-verified seam to wire its send through.
- [x] `daemon._on_tick` now collects two real candidate sources each tick
      — **not fabricated placeholders**: `"interoception"` (this tick's
      own `RegisterState`/`AffectState`, the same data Phase 4 serializes
      into memory) and `"memory"` (the top `MemoryStore.query()` result,
      queried *before* this tick's own memory write so it can't trivially
      match itself; absent at cold start when no memories exist yet) —
      arbitrates them, and persists one `workspace_broadcast` row per tick
      regardless of ignition. **No real OpenRouter call is wired in** —
      spending budget needs Phase 6's viability accounting to gate it
      first; this phase proves the arbiter mechanism and produces real,
      persisted broadcasts without an unaccounted spend path.
- [x] Two real bugs found and fixed during calibration against the actual
      daemon pipeline (not caught by unit tests alone, since those used
      hand-picked candidate salience values): `ignition_threshold`'s mood
      term had an inverted sign (a bad mood was *raising* the threshold);
      and `precision` computed as `clamp01(1 - mean_variance)` hard-zeroed
      under a noisy channel's unbounded EWMA variance (can exceed 1.0),
      exactly when the arbiter most needed a real confidence signal —
      replaced with a saturating `1/(1+variance)` transform. Both are
      documented in `teic/workspace/arbiter.py` and `daemon.py`'s Phase 5
      docstring paragraph, not silently patched.
- [x] `RegisterState.goal_gradient` is a perpetual `0.0` placeholder (no
      goal representation exists until self-model/Phase 7+) — the
      interoception candidate's `goal_relevance` uses a fixed baseline
      (`INTEROCEPTION_GOAL_RELEVANCE_BASELINE = 0.5`) instead of that dead
      channel, same honest-baseline pattern as the memory candidate's own
      fixed `goal_relevance = 0.3`. `embodiment/sensors.py`'s own comment
      is corrected to point at Phase 7+ instead of Phase 5.
- [x] Ignition constants (`BASE_IGNITION_THRESHOLD=0.3`, `AROUSAL_GAIN=0.2`,
      `MOOD_GAIN=0.05`) are empirically calibrated against the real daemon
      pipeline's actual salience range (idle: exactly `0.0`; sustained
      high-arousal jitter: roughly `0.1`–`0.19`) — same posture as Phase
      3's `N_BASELINE` tuning — so idle runs never ignite while sustained
      real stress reliably does.
- [x] `pytest` passes (70 tests: prior phases' gates + Phase 5 gate, plus
      new `teic/workspace` unit tests and two extended `tests/test_daemon.py`
      cases)
- [x] `mypy` passes project-wide (bare `mypy`, no args)
- [x] Gate test: `tests/test_gates/test_phase5.py` — the literal gate
      "Sub-threshold candidate demonstrably modulates but never
      broadcasts/reports," as two independent halves. (1) NEVER-BROADCASTS:
      a sub-threshold winner's content is asserted to never reach a
      rendered prompt via `render_prompt_if_ignited()` (contrasted with a
      supra-threshold winner, whose content *does* reach one — proving the
      function isn't vacuously always `None`). (2) DEMONSTRABLY-MODULATES:
      that same losing/sub-threshold candidate's salience is asserted to
      change `ModulationParams.salience_weight_overrides` on the next
      tick's `compute()` call regardless of it never being broadcast.

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
python -m teic   # Ctrl+C after a few seconds; check workspace_broadcast has rows
```
