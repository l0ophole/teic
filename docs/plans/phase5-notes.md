## Phase 5 — complete

- [x] `teic/workspace/arbiter.py`: `WorkspaceArbiter.select()` implements
      `PLAN.md`'s `salience = novelty * precision * affective_weight *
      goal_relevance` (already a `WorkspaceCandidate` property since Phase
      0) with `max()` over the tick's candidates as the one winner, and
      `ignited = winner.salience >= ignition_threshold(affect, mood)`.
      `ignition_threshold()` lowers under arousal and negative mood only
      (mirrors `modulation.py`'s existing `max(0.0, -mood)` idiom — a good
      mood never raises the bar above the arousal-only baseline).
      `salience_overrides()` folds every candidate's salience — winner or
      not, ignited or not — forward for the daemon to feed into next
      tick's `ModulationParams`.
- [x] `teic/workspace/mineness.py`: `mineness_tag()` is a real dispatch on
      `source_module`, not a hard-coded constant — only `"self"` is
      reachable this phase (both live sources are agent-internal), but
      `"user_input" -> "other"` is already wired so Phase 9's real
      user-input candidate needs no change here. No live source produces
      `"ambiguous"` yet — an honest gap, not a stub.
- [x] `teic/workspace/broadcast.py`: `render_prompt_if_ignited()` is the
      actual "never broadcasts/reports below threshold" enforcement
      point — `assemble_prompt()` (Phase 0) is a pure formatter with no
      `ignited` check of its own by design, so this seam is where ignition
      really gates content reaching a renderable prompt. `daemon.py`
      doesn't call it yet (see next bullet) but it's fully tested now, so
      Phase 6 has a real, already-verified seam to wire its send through.
- [x] `daemon._on_tick` now collects two real candidate sources each tick
      — **not fabricated placeholders**: `"interoception"` (this tick's
      own `RegisterState`/`AffectState`, the same data Phase 4 serializes
      into memory) and `"memory"` (the top `MemoryStore.query()` result,
      queried *before* this tick's own memory write so it can't trivially
      match itself; absent at cold start when no memories exist yet) —
      arbitrates them, and persists one `workspace_broadcast` row per tick
      regardless of ignition. **No real OpenRouter call is wired in** —
      spending budget needs Phase 6's viability accounting to gate it
      first; this phase proves the arbiter mechanism and produces real,
      persisted broadcasts without an unaccounted spend path.
- [x] Two real bugs found and fixed during calibration against the actual
      daemon pipeline (not caught by unit tests alone, since those used
      hand-picked candidate salience values): `ignition_threshold`'s mood
      term had an inverted sign (a bad mood was *raising* the threshold);
      and `precision` computed as `clamp01(1 - mean_variance)` hard-zeroed
      under a noisy channel's unbounded EWMA variance (can exceed 1.0),
      exactly when the arbiter most needed a real confidence signal —
      replaced with a saturating `1/(1+variance)` transform. Both are
      documented in `teic/workspace/arbiter.py` and `daemon.py`'s Phase 5
      docstring paragraph, not silently patched.
- [x] `RegisterState.goal_gradient` is a perpetual `0.0` placeholder (no
      goal representation exists until self-model/Phase 7+) — the
      interoception candidate's `goal_relevance` uses a fixed baseline
      (`INTEROCEPTION_GOAL_RELEVANCE_BASELINE = 0.5`) instead of that dead
      channel, same honest-baseline pattern as the memory candidate's own
      fixed `goal_relevance = 0.3`. `embodiment/sensors.py`'s own comment
      is corrected to point at Phase 7+ instead of Phase 5.
- [x] Ignition constants (`BASE_IGNITION_THRESHOLD=0.3`, `AROUSAL_GAIN=0.2`,
      `MOOD_GAIN=0.05`) are empirically calibrated against the real daemon
      pipeline's actual salience range (idle: exactly `0.0`; sustained
      high-arousal jitter: roughly `0.1`–`0.19`) — same posture as Phase
      3's `N_BASELINE` tuning — so idle runs never ignite while sustained
      real stress reliably does.
- [x] `pytest` passes (70 tests: prior phases' gates + Phase 5 gate, plus
      new `teic/workspace` unit tests and two extended `tests/test_daemon.py`
      cases)
- [x] `mypy` passes project-wide (bare `mypy`, no args)
- [x] Gate test: `tests/test_gates/test_phase5.py` — the literal gate
      "Sub-threshold candidate demonstrably modulates but never
      broadcasts/reports," as two independent halves. (1) NEVER-BROADCASTS:
      a sub-threshold winner's content is asserted to never reach a
      rendered prompt via `render_prompt_if_ignited()` (contrasted with a
      supra-threshold winner, whose content *does* reach one — proving the
      function isn't vacuously always `None`). (2) DEMONSTRABLY-MODULATES:
      that same losing/sub-threshold candidate's salience is asserted to
      change `ModulationParams.salience_weight_overrides` on the next
      tick's `compute()` call regardless of it never being broadcast.
