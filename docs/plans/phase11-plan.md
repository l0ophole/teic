# Phase 11 plan: wire `epistemic_tension` and `social_contact`

## Goal

Both channels are currently hardcoded to `0.0` in `teic/embodiment/sensors.py`
(`epistemic_tension` at line 113, `social_contact` at line 119) despite
`RegisterState` carrying them as real fields and `AffectDynamics._raw_valence`
already weighting `epistemic_tension` at `-0.5`. This phase wires both to
real, already-computed signals, following the codebase's existing
one-tick-lag threading convention (same pattern as `budget_reserve`,
`burn_rate`, `goal_gradient`): a value computed *this* tick (too late to
affect this tick's own `RegisterState`, since `SensorArray.sample()` runs
before it) is threaded into *next* tick's `sample()` call.

- **`epistemic_tension`** <- `1.0 - self._confidence.confidence` (prior
  tick's `ConfidenceEstimate`, already computed by
  `teic/selfmodel/metacognition.py::compute_confidence` and stored on
  `daemon._confidence`). Defaults to `1.0` (maximal tension) when no prior
  confidence exists yet, mirroring `_self_model_instability`'s "no prior
  self-model -> instability maximal" convention.
- **`social_contact`** <- a per-session decaying signal inside
  `SensorArray`, reset toward `1.0` on any tick where a user message was
  drained the *previous* tick, and decaying otherwise (same "ring
  buffer / persistent per-session state" convention `SensorArray` already
  uses for `latency_strain`/`surprise_volatility`). Fed by a new boolean
  daemon threads through `sample()`, set from the existing
  `_pending_user_messages.get_nowait()` drain step.

Nothing about `RegisterState`, `REGISTER_CHANNELS`, or the affect formulas
changes shape — this is purely filling in two already-declared channels.

## Context to read

- `teic/embodiment/sensors.py` — full file; this is where both placeholders
  live and where the new decay state for `social_contact` goes.
- `teic/interoception/channels.py` — full file; `ChannelPipeline.process()`
  is the one seam between `daemon.py` and `SensorArray`/`ChannelInference`.
- `teic/daemon.py` lines ~230-260 (constructor state:
  `_prior_goal_gradient`, `_confidence`, `_pending_user_messages`), ~520-660
  (the `_on_tick` register-build + user-message-drain block), ~700-740 (where
  `compute_confidence` runs and `self._confidence`/`_prior_goal_gradient` get
  set for next tick) — read with offset/limit, not the whole file.
- `teic/selfmodel/metacognition.py` — full file; defines `ConfidenceEstimate`
  semantics `epistemic_tension` will invert.
- `teic/interoception/affect_dynamics.py` — full file; confirms exactly how
  `epistemic_tension` (valence, weight -0.5) and `social_contact` (not
  currently in either formula — verify whether this phase should add it to
  `_raw_valence`/`_raw_arousal`, or leave affect formulas untouched and only
  populate the channel; default to leaving formulas untouched unless the
  phase plan review says otherwise, since that's a separate design decision
  from "stop hardcoding zero").
- `teic/models/registers.py` — full file; channel list/docstring, no logic
  changes expected but confirm field semantics.
- `tests/test_embodiment/test_sensors.py` — existing `SensorArray` test
  shape/conventions to match.
- `tests/test_daemon.py` — existing daemon-level test conventions; note the
  known pre-existing hang in
  `test_high_arousal_run_ignites_more_than_idle_run` (documented in
  `BUILD_STATUS.md`, unrelated to this phase, stays deselected).
- `docs/plans/phase10-plan.md` and `phase10-notes.md` — most recent phase's
  plan/notes, for this repo's current checkpoint-notes format.

## File-by-file build order

1. **`teic/embodiment/sensors.py`**
   - Add `_SOCIAL_CONTACT_DECAY` constant (named, like `_LATENCY_HISTORY_LEN`).
   - Add `self._social_contact: float = 0.0` to `SensorArray.__init__`.
   - Add `epistemic_tension: float = 1.0` and `user_message_last_tick: bool
     = False` parameters to `SensorArray.sample()`.
   - Replace `epistemic_tension=0.0,  # wired in Phase 2/7` with
     `epistemic_tension=epistemic_tension,` and update the module docstring's
     "placeholder until the phase that wires it" list to drop
     `epistemic_tension -> 2/7` and `social_contact -> 9`.
   - Compute `social_contact` from `self._social_contact`: reset toward
     `1.0` when `user_message_last_tick`, else decay
     (`self._social_contact *= _SOCIAL_CONTACT_DECAY`); clamp `[0, 1]`;
     replace the `social_contact=0.0,  # wired in Phase 9` line.

2. **`teic/interoception/channels.py`**
   - Add `epistemic_tension: float = 1.0` and `user_message_last_tick: bool
     = False` parameters to `ChannelPipeline.process()`, threaded straight
     into `self.sensors.sample(...)`.

3. **`teic/daemon.py`**
   - Add `self._prior_user_message_present: bool = False` next to
     `self._prior_goal_gradient` in `__init__`.
   - In the `_on_tick` register-build call (~line 552-560), pass
     `epistemic_tension=(1.0 - self._confidence.confidence) if
     self._confidence is not None else 1.0` and
     `user_message_last_tick=self._prior_user_message_present`.
   - After the existing user-message-drain block (~line 638-646), set
     `self._prior_user_message_present = user_message_text is not None`
     for the *next* tick to consume.
   - No change needed where `self._confidence` itself gets set
     (~line 735) — already correct for the one-tick lag.

4. **`tests/test_embodiment/test_sensors.py`**
   - Test `epistemic_tension` passthrough (raw sample reflects the
     parameter, default `1.0` when omitted).
   - Test `social_contact` decay: a tick with `user_message_last_tick=True`
     pushes it toward `1.0`; subsequent ticks without a message decay it;
     value stays clamped to `[0, 1]`.

5. **`tests/test_daemon.py`**
   - Test that sending a user message causes a *later* tick's
     `register_sample` row for `social_contact` to be elevated relative to
     an idle run (same style as the existing arousal-comparison test, but
     wary of that test's known hang — prefer a narrower, non-hanging
     assertion if the existing test's pattern is what hangs).
   - Test that `epistemic_tension` reflects `1.0 - prior confidence` across
     a tick boundary (e.g. force a low-confidence tick and assert the next
     tick's `epistemic_tension` register rose).

6. **`ARCHITECTURE.md`**
   - Update the two placeholder-list lines (~82-83) that currently read
     `epistemic_tension -> 2/7 ... social_contact -> 9` to describe the
     real Phase 11 wiring, matching this repo's existing style of
     documenting each channel's provenance inline.

7. **`docs/plans/phase11-notes.md`** (created at first checkpoint, not now)
   - Per this project's notes discipline: one line in `BUILD_STATUS.md`
     per completed phase, detail lives here.

## Checkpoints

- cp1: sensors + channels wired - `SensorArray`/`ChannelPipeline` accept and
  compute real `epistemic_tension`/`social_contact` (files 1-2 above),
  `tests/test_embodiment/test_sensors.py` new cases green, mypy clean.
- cp2: daemon threads the one-tick-lag values - `daemon.py` passes real
  `epistemic_tension`/`user_message_last_tick` into `channels.process()`
  each tick (file 3), targeted `tests/test_daemon.py` cases green, mypy
  clean.
- cp3: docs + full verification - `ARCHITECTURE.md` updated, gate/regression
  tests added, batched `pytest -q && mypy` run (minus the pre-existing
  known-hanging test), `BUILD_STATUS.md` + `phase11-notes.md` updated,
  committed.
