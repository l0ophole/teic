## Phase 2 — complete

**Hard stop for user check-in per `PLAN.md`** -- do not begin Phase 3 without
the user's go-ahead; this phase is the spec's explicitly-named "real gate."

- [x] `teic/interoception/affect_dynamics.py`: `AffectDynamics`, a per-session
      fixed-gain EWMA (alpha=0.3) over two raw signals computed fresh each
      tick from `RegisterState` -- `_raw_valence` (viability trend, pulled
      down by unresolved tension/error) and `_raw_arousal` (resource-
      mobilization magnitude) -- never a hand-authored label.
- [x] `teic/interoception/mood.py`: `MoodTracker`, a single-state EWMA over
      valence at a deliberately much smaller gain (`MOOD_ALPHA = 0.05`) than
      `AffectDynamics`, so mood genuinely lags rather than tracking valence
      tick-for-tick.
- [x] `teic/interoception/reportability.py`: `ReportabilityGate`, a
      cooldown-gated threshold on `epistemic_tension` (`REFRACTORY_TICKS =
      5`, `SPEAK_GATE_EPISTEMIC_THRESHOLD = 0.3`) producing `speak_gate_open`.
      **Scoped narrowly to Phase 2** -- see `docs/plans/phase2-plan.md`'s
      scope ruling on the Phase 2 vs. Phase 7 reportability tension; workspace
      ignition (Phase 5) and self-model confidence (Phase 7) are not
      incorporated yet.
- [x] `teic/interoception/modulation.py`: `ModulationCompute.compute()` is no
      longer a `NotImplementedError` stub -- every `ModulationParams` field
      is now derived concretely from `(registers, affect, mood)` per
      `PLAN.md`'s "Non-Linguistic Modulation Pathway" section. Several fields
      (`retrieval_k`, `retrieval_affect_weight`, `planning_depth`,
      `tool_risk_tolerance`, `salience_weight_overrides`) are computed for
      real but have no consumer until Phases 4/5/6.
- [x] `teic/temporal/heartbeat.py`: new optional `tempo_hz_provider` hook,
      consulted after each tick so its return value becomes the *next*
      interval -- default `None` leaves Phase 0/1's fixed-tempo behavior
      unchanged.
- [x] `teic/daemon.py`: `_on_tick` now computes a real `AffectState` via
      `AffectDynamics`/`MoodTracker` and real `ModulationParams` via
      `ModulationCompute`, writes them into `affect_sample` (replacing Phase
      1's neutral placeholder), and feeds `ModulationParams.tempo_hz` back
      into the heartbeat via `tempo_hz_provider` for the next tick.
- [x] `pytest` passes (28 tests: prior phases' gates + Phase 2 gate, plus new
      unit tests for `affect_dynamics`/`mood`/`reportability`/`modulation`/
      `heartbeat`'s tempo feedback)
- [x] `mypy` passes project-wide (bare `mypy`, no args)
- [x] Gate test: `tests/test_gates/test_phase2.py` -- a synthetic 40-tick
      daemon run with a wider jittered `dt_real` sequence than Phase 1's
      asserts `tick.tempo_hz` now takes more than one value (Phase 0/1 always
      wrote a fixed tempo) and `affect_sample.valence` is no longer pinned at
      Phase 1's flat `0.0`; it then pulls an early- and a late-tick
      register/affect snapshot from that same run and re-verifies the
      literal gate wording -- identical `assemble_prompt` output text with a
      byte-identical broadcast/narrative_tail, divergent
      temperature/tempo_hz/speak-gate. No assertion on real LLM calls or
      generated text -- there is still no workspace/arbiter wiring an actual
      chat turn (Phase 5+); this phase proves the modulation *pathway*.
