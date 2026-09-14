# Build Status

| Phase | Status |
|---|---|
| 0 — Daemon skeleton | **Complete** |
| 1 — Telemetry → interoceptive vector | **Complete** |
| 2 — Non-linguistic modulation (real gate) | Not started |
| 3 — Forward models, prediction error | Not started |
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
