# Build Status

| Phase | Status |
|---|---|
| 0 — Daemon skeleton | **Complete** |
| 1 — Telemetry → interoceptive vector | **Complete** |
| 2 — Non-linguistic modulation (real gate) | **Complete** |
| 3 — Forward models, prediction error | **Complete** |
| 4 — Memory timescales, decay, consolidation | Not started |
| 5 — Workspace arbiter, ignition | Not started |
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
      35-tick daemon run with a deliberate two-phase step function (15
      baseline ticks at nominal `dt_real`, then 20 ticks at a sustained 3x
      `dt_real`, standing in for `PlanBuildTEIC.md`'s "silently inflate a
      tool's latency 3x" per this phase's scope ruling) asserts
      `prediction_error` spikes at least 3x above its recent baseline mean
      on the first injected tick, then decays back down well below that
      spike by the end of the run even though `dt_real` never returns to
      baseline -- proving the model re-adapts to the new regime rather than
      just recovering from a blip. For contrast, `latency_strain` (the
      fixed-expectation, non-adaptive sibling signal) is asserted to stay
      elevated across the entire injected window without that
      spike-then-decay shape -- concrete evidence Phase 3 added a genuinely
      new, learned signal rather than just relabeling `latency_strain`.

### How to verify this phase yourself

```
source .venv/bin/activate
pytest -q
mypy
```
