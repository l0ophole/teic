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
