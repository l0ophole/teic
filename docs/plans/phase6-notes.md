# Phase 6 notes — Viability, precariousness, allostasis

Gate: agent regulates without instruction. Budget actually depletes,
replenishment requires an explicit effector action, termination-on-zero is
real, config-gated, and logged.

## cp1 — budget + forecast

- `teic/models/viability.py`: `ViabilityState` (reserve, burn rate,
  forecast trajectory, termination flag/justification).
- `teic/settings.py`: `ViabilitySettings` gained `monthly_budget_usd`,
  `harness_monthly_budget_usd`, `max_burn_rate_usd_per_tick`,
  `replenishment_amount_usd`, `forecast_horizon_ticks`.
- `teic/embodiment/viability_budget.py`: `ViabilityBudget` — `spend()` (real
  cost only), `replenish()` (explicit effector action, never called
  automatically), `reserve_channel()`/`burn_rate_channel()` normalized 0..1.
- `teic/interoception/allostasis.py`: `AllostaticForecaster` reuses the
  session's own `ChannelInference` posterior (not a forked model);
  `anticipatory_pressure()` returns nonzero before an actual threshold
  violation.

## cp2 — termination gate

- `teic/ethics/termination_gate.py`: `TerminationGate.fire()` refuses
  (`TerminationRefused`, writes nothing) unless both
  `allow_actual_termination` and `termination_justification` are set; on
  success writes a permanent `log_event` row before signalling halt.
- `perturbation_caps.py` skipped — no perturbation hook exposed yet (Phase
  8 not started); revisit if the assessment harness needs it.

## cp3 — daemon/arbiter integration

- `teic/embodiment/sensors.py` / `teic/interoception/channels.py`:
  `budget_reserve`/`burn_rate` threaded through `SensorArray.sample()` /
  `ChannelPipeline.process()` as two new optional params, same one-tick-lag
  pattern as `prediction_error` (Phase 3) — this tick's sensing reads the
  *previous* tick's already-settled ledger state.
- `teic/daemon.py` `_on_tick`: reads `ViabilityBudget.reserve_channel()`/
  `burn_rate_channel()` before this tick's own `ChannelPipeline.process()`;
  after that tick's `ChannelInference.update()`, calls
  `AllostaticForecaster.anticipatory_pressure("budget_reserve", threshold=
  0.2)` and appends a `"viability"` `WorkspaceCandidate` when positive
  (`novelty = pressure`, `precision`/`affective_weight`/`goal_relevance`
  fixed at `1.0` — an anticipated crisis isn't a noisy signal the way
  sensed registers are). No arbiter.py change needed: `select()` was
  already generic over `list[WorkspaceCandidate]`.
- Real spend, finally: `render_prompt_if_ignited()` (Phase 5's seam) is now
  called every tick; when it returns a prompt, its real token count (chars
  // 4) is costed via `PricingCache.estimate_cost_usd()` (0.0 completion
  tokens, since no generation ever happens this phase) and charged via
  `spend()`. The only `replenish()` call site: `broadcast.ignited and
  broadcast.winner.source_module == "viability"`.
- Termination wiring: when `reserve_usd <= 0.0`, `_on_tick` calls
  `TerminationGate.fire()`; `TerminationRefused` is caught and ignored
  (daemon keeps running with an exhausted reserve); success sets
  `TeicDaemon._terminated = True` and calls `Heartbeat.stop()`.
  `Heartbeat.run_n_ticks()` (used by every gate/dev test) has no
  stop-event check of its own, unlike `run()` — so `_on_tick` also checks
  `self._terminated` as its first line and no-ops immediately once set,
  making termination stick even mid fixed-count test run.
- `tests/test_phase6.py` (new, top-level — distinct from the unit-level
  `tests/test_gates/test_phase6.py`): real depletion under seeded pricing +
  forced ignitions; idle run never spends/replenishes; a forced-low reserve
  reliably bids and wins a `"viability"` candidate within one tick
  (pressure hits exactly `1.0` on a channel's first-ever observation, since
  `AllostaticForecaster`'s flat first-call trajectory already sits below
  threshold) and replenishes; termination gate refusal leaves the daemon
  running; termination gate success halts it after exactly one further
  tick, with a permanent log row.
