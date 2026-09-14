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
