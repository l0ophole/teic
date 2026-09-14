# Phase 7 notes — Self-model, metacognition

## cp1 — self-model construction (teic/selfmodel/builder.py)
`build_self_model()` derives every field from real telemetry already
computed elsewhere: `body`/`agency` reuse `ForwardModel`'s prediction-error
comparator, `interoception_summary` is `RegisterState.as_dict()` verbatim,
`history_summary` is passed in (caller-resolved via `MemoryStore.query()`).
`goal_gradient` resolves into `identity_traits["goal_gradient"]` (mood *
stable `viability_preference` trait) but the daemon-side wiring back into
`SensorArray.sample()` was explicitly deferred to cp3 task 8, since
`RegisterState` for a tick is built *before* that tick's self-model runs —
the dependency only closes across a tick boundary.

## cp2 — metacognitive confidence (teic/selfmodel/metacognition.py)
`compute_confidence()` blends prediction-error component (0.6) and
self-model-stability component (0.4; agency delta + mental-state-estimate
delta since prior tick, 1.0 instability when no prior exists).
`ModulationCompute.compute()` gained optional `confidence`/`prior_ignited`
params (default to neutral/no-op so pre-cp3 callers see unchanged
behavior) feeding `retrieval_k`/`tool_risk_tolerance`.
`ReportabilityGate.evaluate()` gained a second `ignited AND confidence >=
IGNITION_CONFIDENCE_THRESHOLD` path alongside the original
`epistemic_tension` threshold.

## cp3 — daemon integration
- **Task 7 (arbiter/mineness) — no change needed.** `WorkspaceArbiter.select()`
  is already generic over an arbitrary candidate list; the self-model's
  causal path to behavior runs through `ModulationCompute`/
  `ReportabilityGate` directly, not through winning workspace arbitration.
  No self-model-shaped `WorkspaceCandidate` was added. Documented here as a
  scope decision, not left implicit.
- **Task 8 (teic/daemon.py):** new instance attrs `_self_model`,
  `_confidence`, `_prior_ignited`, `_prior_goal_gradient`. `_on_tick` now:
  passes `goal_gradient=self._prior_goal_gradient` into
  `self._channels.process()`; passes `confidence=self._confidence,
  prior_ignited=self._prior_ignited` into `self._modulation.compute()`;
  after the memory query (reusing its results for `history_summary`),
  builds this tick's `SelfModel`/`ConfidenceEstimate` and persists one
  `self_model` row; updates `self._self_model`/`_confidence`/
  `_prior_goal_gradient` for next tick; sets `self._prior_ignited =
  broadcast.ignited` right after arbitration, alongside the existing
  `salience_overrides()` line.
- **Task 9 (migration):** `teic/persistence/migrations/0005_self_model.sql`
  — one `self_model` row per tick, every `SelfModel` field plus that tick's
  `confidence`.
- **Task 10 (tests):** added
  `test_editing_self_model_field_causally_changes_downstream_behavior` to
  `tests/test_gates/test_phase7.py` — the Phase 7 gate's core claim:
  directly editing a `SelfModel` field via `.model_copy(update=...)`
  predictably changes `compute_confidence()`'s output, which predictably
  changes `ModulationCompute.compute()`'s `retrieval_k`/
  `tool_risk_tolerance`. New top-level `tests/test_phase7.py` (mirrors
  `tests/test_phase6.py`'s `_fake_heartbeat` pattern) covers: `self_model`
  row persistence + version increment across real ticks; confidence/
  goal_gradient correctly lagged one tick into real sensing/modulation.
- **Task 11:** `BUILD_STATUS.md`/`ARCHITECTURE.md` updated with a Phase 7
  section; this notes file.
