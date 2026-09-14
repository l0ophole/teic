# Phase 6 Plan — Viability, Precariousness, Allostasis

Gate (per `docs/PlanBuildTEIC.md` BUILD ORDER): **Agent regulates without
instruction.** The budget must actually deplete, replenishment must require
action, and termination-on-zero must be real, config-gated, and logged.

Existing scaffolding to build on (do not recreate):
- `teic/settings.py:35` — `ViabilitySettings` (`allow_actual_termination`,
  `termination_justification`) already present; needs budget/decay/
  replenishment fields added.
- `teic/models/registers.py:8` — `budget_reserve`, `burn_rate`,
  `context_pressure` already exist as channels.
- `teic/ethics/__init__.py` — empty package, intended home for the
  termination gate and permanent-logging hook.
- `teic/interoception/inference.py:45` (`ChannelInference`) and
  `teic/interoception/mood.py:15` (`MoodTracker`) — allostatic forecasting
  hooks into these, not new parallel modules.
- `teic/temporal/heartbeat.py:26` (`Heartbeat`) — tick loop that any
  regulation action must be invoked from.

## File-by-file build order

1. **`teic/models/viability.py`** (new) — `ViabilityState` pydantic model:
   current reserve, burn rate, forecast trajectory, termination flag,
   justification string. Mirrors the shape of `teic/models/affect.py`.
2. **`teic/settings.py`** (edit `ViabilitySettings`) — add starting budget,
   depletion rate parameters, replenishment cost/action, and forecast
   horizon. Keep `allow_actual_termination` defaulting `False`.
3. **`teic/embodiment/viability_budget.py`** (new) — the precariousness
   ledger: depletes `budget_reserve` from real token/dollar/compute-second
   spend (read from `teic/llm/cost.py`), exposes a replenishment call that
   requires an explicit effector action (not a silent top-up).
4. **`teic/interoception/allostasis.py`** (new) — forecasts channel
   trajectories (reuse `ChannelInference` posterior, don't fork it) and
   emits an anticipatory pressure signal *before* a viability channel
   crosses its threshold. This is what lets the agent act pre-emptively
   rather than reactively.
5. **`teic/ethics/termination_gate.py`** (new) — the single authorized path
   to actual termination. Reads `ViabilitySettings.allow_actual_termination`
   + `termination_justification`; refuses to fire without both set; writes
   a permanent log entry via `teic/persistence/log_sink.py` before halting
   the daemon.
6. **`teic/ethics/perturbation_caps.py`** (new) — bounded negative-state
   induction caps (intensity/duration) for any research-mode viability
   perturbation, per the Ethics Requirements section. Only needed if Phase
   6 exposes a perturbation hook for the assessment harness; confirm scope
   with the checkpoint before building.
7. **`teic/daemon.py`** (edit) — wire `viability_budget` depletion and
   `allostasis` forecasting into the tick loop; call `termination_gate` when
   reserve hits zero.
8. **`teic/workspace/arbiter.py`** (edit, check first) — viability pressure
   must be able to bid into the workspace (e.g., surface a "replenish now"
   candidate) so regulation is visible as agent behavior, not a background
   cron job.
9. **`tests/test_phase6.py`** (new) — budget depletion under synthetic
   spend, replenishment requiring action, allostatic forecast triggering
   pre-violation behavior, termination gate refusing to fire when
   unconfigured, termination gate firing + logging when configured.
10. **`BUILD_STATUS.md`** / **`ARCHITECTURE.md`** — Phase 6 sections, per
    Notes discipline (one line + pointer to `docs/plans/phase6-notes.md`).

## Checkpoints

- cp1: budget-and-forecast — Tasks 1–4 done: `ViabilityState` model,
  settings fields, depleting/replenishing budget ledger wired to real LLM
  spend, allostatic forecast producing an anticipatory signal. Tests for
  these pass; termination path not yet built.
- cp2: termination-gate — Tasks 5 (and 6 if in scope) done: config-gated
  termination gate with permanent logging, perturbation caps if applicable.
  Tests confirm refusal-when-unconfigured and firing-when-configured.
- cp3: integration — Tasks 7–10 done: daemon tick loop and arbiter wired
  end-to-end, `test_phase6.py` full suite green, mypy clean, BUILD_STATUS.md
  and ARCHITECTURE.md updated. Phase 6 gate ("agent regulates without
  instruction") demonstrable.

## Context to read at each checkpoint resume

- `docs/plans/phase6-plan.md` (this file)
- `BUILD_STATUS.md` — status table + current-state section only
- Files named in the task list above for the checkpoint being resumed;
  use offset/limit on large ones (`teic/daemon.py`, `teic/settings.py`)
- Do not re-read `PLAN.md`, `ARCHITECTURE.md`, or prior phase notes unless
  a specific task above says to check one first
