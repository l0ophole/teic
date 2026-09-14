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
