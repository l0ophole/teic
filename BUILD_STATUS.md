# Build Status

| Phase | Status | Detail |
|---|---|---|
| 0 — Daemon skeleton | **Complete** | `docs/plans/phase0-notes.md` |
| 1 — Telemetry → interoceptive vector | **Complete** | `docs/plans/phase1-notes.md` |
| 2 — Non-linguistic modulation (real gate) | **Complete** | `docs/plans/phase2-notes.md` |
| 3 — Forward models, prediction error | **Complete** | `docs/plans/phase3-notes.md` |
| 4 — Memory timescales, decay, consolidation | **Complete** | `docs/plans/phase4-notes.md` |
| 5 — Workspace arbiter, ignition | **Complete** | `docs/plans/phase5-notes.md` |
| 6 — Viability, allostasis | **Complete** | `docs/plans/phase6-notes.md` |
| 7 — Self-model, metacognition | Not started | |
| 8 — Assessment harness + falsifiers | Not started | |
| 9 — UI (terminal + web) | Not started | |

## Current state / next step

Phase 6 cp3 done: viability budget + allostatic forecast wired into
`daemon.py`'s tick loop end-to-end (real spend via `render_prompt_if_ignited`
+ `PricingCache`, viability candidate bidding, `replenish()`/
`TerminationGate` reached only through real arbitration). See
`docs/plans/phase6-notes.md`.

Next: begin Phase 7 (self-model, metacognition) per `PLAN.md`'s build order.

## How to verify the build so far

```
.venv/bin/pytest -q   # all phases' gates included
.venv/bin/mypy
python -m teic         # Ctrl+C; check data/teic.db: tick, register_sample,
                        # affect_sample, memory_record (tau1), workspace_broadcast rows
```

## Completed-phase one-liners

- Phase 0: repo skeleton, migrations (fixed executescript/implicit-commit
  bug), settings, smoke-tested daemon loop.
- Phase 1: `SensorArray` + `ChannelInference` (EWMA calibration) +
  `ChannelPipeline`; real register_sample rows; affect still neutral.
- Phase 2: `AffectDynamics` + `MoodTracker` (slow-gain lag) +
  `ReportabilityGate` (Phase-2-scoped) + full `ModulationCompute`; tempo
  feedback via `tempo_hz_provider`; gate proves byte-identical prompt text
  with divergent non-linguistic params.
- Phase 3: `ForwardModel` (adaptive latency prediction) + one-tick
  `ProtentionBuffer`; real `prediction_error` feeds `ChannelPipeline`;
  step-change gate proves spike-then-decay re-adaptation.
- Phase 4: power-law `decay`, affect-biased `retrieval` (consumes Phase 2's
  retrieval modulation), sqlite-vec `memory_vec`, `MemoryStore`, structural
  wall-clock-idle-gated consolidation; real tau1_working writes.
- Phase 5: `WorkspaceArbiter` (salience formula + affect-sensitive ignition
  threshold, 2 bugs found during calibration and documented),
  `mineness_tag`, `render_prompt_if_ignited` seam; two real candidate
  sources; ignition constants calibrated to the real pipeline.
- Phase 6: `ViabilityBudget` (real spend/replenish ledger) +
  `AllostaticForecaster` (shared-posterior trend forecast) +
  `TerminationGate` (config-gated, permanently logged); daemon wires real
  spend through `render_prompt_if_ignited`/`PricingCache`, bids a
  `"viability"` candidate on anticipatory pressure, replenishes only on
  that candidate winning + igniting, terminates only through the gate.
