# Phase 7 Plan — Self-Model, Metacognition, Reportability Gate

Gate (per `docs/PlanBuildTEIC.md` BUILD ORDER): **Self-model is causally
efficacious; confidence is calibrated.** Editing a self-model field must
predictably change behavior, and a metacognitive confidence estimate must
alter behavior (low confidence → seek info, high confidence → act).

Existing scaffolding to build on (do not recreate):
- `teic/models/self_model.py` — `SelfModel` pydantic model already has all
  seven fields (body/agency/interoception/history/identity/mental_state/
  temporal_self) plus `version`/`last_edited_tick_id`. No module actually
  constructs, persists, or reads one yet.
- `teic/interoception/reportability.py` — Phase 2's narrow
  `ReportabilityGate` (cooldown + `epistemic_tension` threshold only, by
  design — see its module docstring). Phase 7 must *compose* self-model
  confidence and workspace ignition into this, not replace it.
- `teic/workspace/mineness.py` — self/other/ambiguous tagging already keyed
  off `WorkspaceCandidate.source_module`; the self-model is the thing
  broadcast content gets tagged as belonging to (PLAN.md Layer 3).
- `teic/models/registers.py` (`goal_gradient`) and `teic/daemon.py`'s
  `INTEROCEPTION_GOAL_RELEVANCE_BASELINE` comment — both explicitly say
  `goal_gradient`'s perpetual `0.0` placeholder waits on real self-model/goal
  representation; Phase 7 is where that gets resolved (or explicitly
  deferred again with a comment update).
- `teic/models/probe.py` (`ProbeResult`) — Tier B8 (counterfactual
  self-simulation) and B7 (self-model updating) probes are Phase 8's job,
  but Phase 7's self-model/confidence APIs must be shaped so those probes
  can call them without new plumbing.
- `teic/embodiment/sensors.py`, `teic/embodiment/forward_model.py` — body
  schema / agency comparator inputs the self-model's `body`/`agency` fields
  should be built from ("models the system from the same telemetry", not
  authored by hand).
- `teic/daemon.py` `_on_tick` — tick loop order established by prior phases
  (prediction-error resolve → sense → affect → modulation → workspace
  candidates/arbitration → memory write); self-model update and
  metacognitive confidence slot into this sequence, not around it.

## File-by-file build order

1. **`teic/models/metacognition.py`** (new) — `ConfidenceEstimate` pydantic
   model: scalar calibrated confidence (0..1), the signal(s) it was derived
   from, tick_id. Mirrors the shape of `teic/models/affect.py`.
2. **`teic/selfmodel/__init__.py`** (new package) — home for self-model
   construction/update logic, parallel to `teic/workspace/`,
   `teic/interoception/`.
3. **`teic/selfmodel/builder.py`** (new) — builds/updates a `SelfModel`
   instance each tick (or on a slower cadence — confirm at cp1) from the
   same telemetry every other module sees: `RegisterState`/`AffectState`
   (interoception_summary), `ForwardModel`/effector state
   (body/agency — reuse `ForwardModel`'s comparator, don't fork it),
   memory (history_summary via `MemoryStore.query()`, same pattern as
   Phase 5's memory candidate), and prior `SelfModel` (temporal_self,
   version increment). Resolves `RegisterState.goal_gradient`'s Phase
   5/6 `0.0` placeholder against `identity_traits`, or documents why it
   still can't and stays deferred.
4. **`teic/selfmodel/metacognition.py`** (new) — the metacognitive monitor:
   computes calibrated second-order confidence from forward-model
   prediction error + self-model stability (e.g. how much the self-model
   changed this tick). Must expose a value `ModulationCompute` or the
   arbiter can consume to alter behavior (low confidence → raise
   retrieval/exploration, high confidence → act/commit).
5. **`teic/interoception/modulation.py`** (edit) — thread confidence into
   `ModulationCompute.compute()` (e.g. retrieval count/weighting, planning
   depth, tool risk tolerance per PLAN.md Layer 2) so low/high confidence
   has a real non-linguistic behavioral effect, following Phase 2's
   established pathway.
6. **`teic/interoception/reportability.py`** (edit) — compose self-model
   confidence and workspace ignition (Phase 5) with the existing
   `epistemic_tension` cooldown gate, per the module's own docstring
   ("those compose with this gate later; they don't replace it").
7. **`teic/workspace/arbiter.py`** / **`teic/workspace/mineness.py`**
   (edit, check first) — a self-model-update candidate may need to bid
   into the workspace (self-model changes are themselves broadcastable
   content); mineness tagging should reference the self-model rather than
   a hardcoded self/other source list if this changes.
8. **`teic/daemon.py`** (edit) — wire self-model construction/update and
   metacognitive confidence into `_on_tick`, in the established tick
   sequence; persist self-model versions (new table/columns — check
   `teic/persistence/db.py` migrations first) so editing a field and
   observing downstream behavior change is possible at the gate check.
9. **`teic/persistence/db.py`** (edit, migration) — add a `self_model`
   table (version, tick_id, serialized fields) if Phase 7 needs durable
   self-model history rather than in-memory-only state; confirm scope at
   cp1 before adding.
10. **`tests/test_phase7.py`** (new) — self-model construction from real
    telemetry; self-model persists/versions across ticks; **causal
    efficacy test**: directly edit a self-model field and assert a
    predictable downstream behavior change (the gate's core claim);
    confidence estimate correlates with forward-model prediction error;
    low confidence measurably alters modulation (e.g. retrieval
    count/exploration) vs. high confidence; reportability gate composition
    (self-model confidence + ignition + epistemic_tension all contribute).
11. **`BUILD_STATUS.md`** / **`ARCHITECTURE.md`** — Phase 7 sections, per
    Notes discipline (one line + pointer to `docs/plans/phase7-notes.md`).

## Checkpoints

- cp1: self-model-construction — Tasks 1–3 done: `ConfidenceEstimate`
  model, `teic/selfmodel/` package, `SelfModel` built/updated each tick from
  real telemetry (not hand-authored), with a resolution (or documented
  deferral) of the `goal_gradient` placeholder. No metacognition or
  behavioral wiring yet.
- cp2: metacognition-and-modulation — Tasks 4–6 done: calibrated confidence
  computed from real signals, threaded into `ModulationCompute` so it has a
  non-linguistic behavioral effect, and composed into the reportability
  gate alongside the existing epistemic-tension/ignition signals. Tests for
  these pass.
- cp3: integration — Tasks 7–11 done: workspace/arbiter wiring (if needed),
  `teic/daemon.py` tick-loop integration, persistence migration (if
  needed), `test_phase7.py` full suite green including the causal-efficacy
  test, mypy clean, BUILD_STATUS.md and ARCHITECTURE.md updated. Phase 7
  gate ("self-model is causally efficacious; confidence is calibrated")
  demonstrable.

## Context to read at each checkpoint resume

- `docs/plans/phase7-plan.md` (this file)
- `BUILD_STATUS.md` — status table + current-state section only
- Files named in the task list above for the checkpoint being resumed;
  use offset/limit on large ones (`teic/daemon.py`, `teic/settings.py`)
- Do not re-read `PLAN.md`, `ARCHITECTURE.md`, or prior phase notes unless
  a specific task above says to check one first
