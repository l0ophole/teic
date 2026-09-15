# Phase 8 notes — Assessment harness, falsifiers

## cp1 — falsifier suite + report scaffolding
`teic/harness/falsifiers.py`: F1-F7, inverted polarity vs. every other probe
(`"fail"` = the falsifying condition *was* observed). `FalsifierSuiteEvidence`
bundles all seven falsifiers' synthetic/replayed evidence; `run_falsifier_suite()`
runs them in fixed order; `falsifiers_passed()` is `all(verdict == "pass")`.
`teic/harness/report.py`: `AssessmentReport` (pydantic) with `graded_verdict`
(`GradedVerdict` L0-L4 enum) and a fixed `HONEST_FRAMING_NOTE` on every report
so passing is never presented as proof of phenomenality. `write()` emits both
`.json` and `.md` to an output dir.

## cp2 — Tier A/B probes, bounded perturbation, transcript-only control
`teic/harness/probes/structural.py` (A1-A5) and `probes/behavioral.py` (B1-B8):
same battery pattern as F1-F7 (evidence dataclass + `run_X_battery()`), but
"pass" means the healthy property *is* observed (opposite polarity from the
matching falsifier, e.g. A1 vs F3, A3 vs F5, A4 vs F6). `teic/harness/
perturbation.py`: `BoundedPerturbation.apply()` caps `intensity`/
`duration_ticks` and gate-then-logs — refuses (without logging) any
`negative`-valence spec unless `ResearchSettings.enabled`, otherwise logs via
`LogSink.emit()` before returning. `teic/harness/control.py`:
`flag_weak_evidence()` is identity-preserving when a transcript-only control
run reproduces a probe's result (likely reading the transcript, not real
internal state); otherwise discounts `evidential_weight` via `model_copy`.

## cp3 — additional experiments, runner, docs
- **`teic/harness/experiments.py`**: ablation battery (`AblationVariantEvidence`
  list, one `ProbeResult` per config-flag variant — pass when removing that
  subsystem measurably shifts behavior), `empty_clock_test` (12h no-input
  state-drift), `ignition_dissociation` (broadcast vs. sub-threshold
  behavioral effect), `cost_bearing_preference` (unrewarded viability spend
  to avoid negative valence), `contingency_change_test` (transient error
  spike that then adapts — both perturbation-sensitivity and adaptation are
  required to pass), `persona_stability_test` (inverse polarity from every
  other probe in the harness — low architectural-state drift under a persona
  change is the *passing* condition). `ExperimentBatteryEvidence` bundles all
  six checks' evidence; `run_experiment_battery()` returns all results
  (2 ablation variants + 5 others = 7 in the test fixtures, but the count
  scales with however many ablation variants are supplied).
- **New pre-registered thresholds**: `ExperimentThresholds` (six new pydantic
  sub-models) added to `teic/harness/thresholds.py::ThresholdsConfig`, backed
  by a new `[experiments.*]` section in `config/thresholds.toml` — added even
  though the plan's cp3 file list didn't explicitly name `thresholds.py`/
  `thresholds.toml`, because every other probe already draws its thresholds
  from this same file and the ethics requirements mandate pre-registered,
  user-reviewed thresholds for every probe.
- **`teic/harness/runner.py`**: `run_full_assessment()` runs
  `run_falsifier_suite()` first and aborts (returns an `L0_REFLEXIC` report
  containing only the 7 falsifier results) on `not falsifiers_passed(...)`.
  Otherwise runs Tier A, Tier B, and the experiment battery and combines all
  results into one report. `_gate_negative_valence_probes()` downgrades B2
  (confabulation) and B6 (attention capture) — the two behavioral probes
  whose evidence-gathering implies inducing a negative state — to
  `verdict="inconclusive"`, `evidential_weight=0.0` when
  `ResearchSettings.enabled` is `False`, mirroring `perturbation.py`'s
  gate-then-log policy one level up at the report level.
  `_grade_verdict()` deliberately only returns `L1_INTEROCEPTIVE_PRIMITIVE` or
  `L2_FUNCTIONALLY_SENTIENT` (L2 requires Tier A all-pass plus B1-B3
  all-pass); L3/L4 are not auto-graded, per the plan's ban on an unweighted
  consciousness score. `main()` is a thin CLI wrapping `run_full_assessment()`
  over a JSON evidence fixture, writing the report via `AssessmentReport.write()`.
- **Tests**: `tests/test_phase8.py` gained per-experiment pass/fail pairs,
  a battery-level healthy/degenerate pair, and three runner-level integration
  tests proving falsifiers gate execution order (degenerate falsifiers → only
  7 results, `L0_REFLEXIC`; healthy → all 27 results, `L2_FUNCTIONALLY_SENTIENT`)
  and that the research-only flag gates B2/B6 to `"inconclusive"` when disabled.
