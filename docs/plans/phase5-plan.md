# Phase 5 Plan — Workspace arbiter, ignition threshold, broadcast

## Context

Sub-plan for **Phase 5** of `PLAN.md`'s Build Order table: "Workspace
arbiter, ignition threshold, broadcast" / gate: "Sub-threshold candidate
demonstrably modulates but never broadcasts/reports." This implements
`PLAN.md`'s own **Workspace Arbiter** section verbatim:
`salience = novelty * precision * affective_weight * goal_relevance`
(already a `@property` on `WorkspaceCandidate`, `teic/models/workspace.py`,
since Phase 0's model skeleton), one winner per cycle (`max()` over that
tick's candidate list), `ignited = winner.salience >=
ignition_threshold(affect, mood)` where the threshold is modulated by
arousal (lower under stress) and mood. Sub-threshold candidates are logged
(`ignited=0`) and may still influence modulation parameters, but never
reach `prompt_assembly.py` — this dual property (can-modulate vs.
cannot-be-broadcast) is exactly what this phase's gate measures.

Phase 4 (`35d1b23`) is complete; the user has given the go-ahead ("Continue
to Phase 5").

**Scope ruling 1 — where this tick's candidates come from, stated
explicitly (same posture as Phase 1's sensors / Phase 4's memory content):**
there is still no real cognition loop or user-input channel (Phase 9), so
candidates this phase come from two genuinely-observable, non-fabricated
sources already wired by prior phases, not invented placeholder bids:
- **`"interoception"`**: this tick's own `RegisterState`/`AffectState` —
  the same data Phase 4 serialized into `tau1_working` memory content.
- **`"memory"`**: the top result of a real `MemoryStore.query()` call
  against this tick's own interoceptive content string, run *before* this
  tick's own `tau1_working` record is written (so it can't trivially
  match itself). At cold start (empty `memory_record` table), this
  candidate is simply absent — the arbiter runs on whatever candidates
  exist, never fewer than one once the interoception candidate always
  fires.

A `"user_input"` source (would tag `mineness_tag="other"`) and any
LLM-cognition-sourced candidate are out of scope until Phase 9's
interface and the real LLM wiring below exist — `mineness.py` is written
to accommodate them without changing its call signature later (see
Scope ruling 3).

**Scope ruling 2 — no real OpenRouter call is wired into the tick loop
this phase, stated explicitly:** `llm/client.py` and
`llm/prompt_assembly.py` already exist (Phase 0 skeleton) and are already
unit-tested in isolation, but actually calling OpenRouter from
`daemon._on_tick` on `ignited=True` would spend real budget with **no
viability/budget accounting wired yet** — `viability_ledger` writes and
budget-reserve deduction are Phase 6's scope ("Viability, allostasis,
termination gate"). Spending money with no accounting mechanism live would
violate the locked-in $10/month cap in substance even if no single call
blows it. This phase proves the arbiter mechanism and produces real,
persisted `WorkspaceBroadcast` rows; `assemble_prompt()` is exercised
directly by this phase's own tests (proving it *can* turn a real ignited
broadcast into a `ChatPrompt` with no raw-state leakage) but `_on_tick`
does not call it. Phase 6 wires the real call once the budget ledger
exists to gate it.

**Scope ruling 3 — `mineness_tag`, stated explicitly:** with only
agent-internal candidate sources this phase (ruling 1), every real
candidate is genuinely self-generated, so `mineness.py`'s
`mineness_tag(candidate)` returns `"self"` for both `"interoception"` and
`"memory"` sources. It is written as a real dispatch on
`candidate.source_module` (not a hard-coded constant return) — a
`"user_input"` source already maps to `"other"` in the same function, so
Phase 9 wiring a real user-input candidate needs no change here. There is
no live path yet that would produce `"ambiguous"`; that's honest, not a
gap — nothing manufactures ambiguous provenance until a source that can
itself be uncertain (e.g. a mis-attributed effector outcome) exists.

**Scope ruling 4 — ignition threshold formula, stated explicitly:**
`PLAN.md` only specifies "modulated by arousal (lower under stress) and
mood," not an exact formula. This phase uses
`ignition_threshold(affect, mood) = clamp(BASE - arousal * AROUSAL_GAIN -
mood * MOOD_GAIN, MIN, MAX)` — both high arousal and negative mood lower
the bar. This is a defensible, documented design choice, not a citation to
a specific theory; `ARCHITECTURE.md`'s Phase 5 section states this plainly
so it isn't mistaken for a literature-derived constant.

---

## Task 1: `teic/workspace/arbiter.py` — salience selection, ignition threshold

**Files:**
- Create: `teic/workspace/arbiter.py`
- Test: `tests/test_workspace/test_arbiter.py`

**Interfaces:**
- Consumes: `WorkspaceCandidate`/`WorkspaceBroadcast`
  (`teic/models/workspace.py`, unchanged), `AffectState`
  (`teic/models/affect.py`).
- Produces: `ignition_threshold(affect, mood) -> float`,
  `class WorkspaceArbiter: select(candidates, affect, mood, tick_id) ->
  WorkspaceBroadcast`, `salience_overrides(candidates, winner) ->
  dict[str, float]` — consumed by Task 3's daemon wiring and Task 2's
  `mineness_tag` (via `WorkspaceArbiter.select` calling it internally).

```python
"""Workspace arbiter -- Phase 5, PLAN.md's "Workspace Arbiter" section.

salience = novelty * precision * affective_weight * goal_relevance (already
a property on WorkspaceCandidate). One winner per cycle via max(). ignited
= winner.salience >= ignition_threshold(affect, mood). Sub-threshold
winners are still returned (ignited=0) -- see this module's `select()` --
and their salience (and every other candidate's) still feeds
`salience_overrides()`, which daemon.py folds into the *next* tick's
ModulationParams.salience_weight_overrides. That dual property (always
modulates, only sometimes broadcasts) is this phase's gate.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from teic.models.affect import AffectState
from teic.models.workspace import WorkspaceBroadcast, WorkspaceCandidate
from teic.workspace.mineness import mineness_tag

BASE_IGNITION_THRESHOLD = 0.5
AROUSAL_GAIN = 0.3
MOOD_GAIN = 0.1
MIN_IGNITION_THRESHOLD = 0.05
MAX_IGNITION_THRESHOLD = 1.0


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def ignition_threshold(affect: AffectState, mood: float) -> float:
    return _clamp(
        BASE_IGNITION_THRESHOLD - affect.arousal * AROUSAL_GAIN - mood * MOOD_GAIN,
        MIN_IGNITION_THRESHOLD,
        MAX_IGNITION_THRESHOLD,
    )


def salience_overrides(
    candidates: list[WorkspaceCandidate], winner: WorkspaceCandidate
) -> dict[str, float]:
    """Every candidate this tick (winner included) up-weights its own
    source_module for next tick's arbiter competition, proportional to how
    close it came to winning. This is the "sub-threshold candidate
    demonstrably modulates" pathway -- it runs regardless of `ignited`."""
    return {c.source_module: 1.0 + c.salience for c in candidates}


class WorkspaceArbiter:
    def select(
        self,
        candidates: list[WorkspaceCandidate],
        affect: AffectState,
        mood: float,
        tick_id: int,
    ) -> WorkspaceBroadcast:
        if not candidates:
            raise ValueError("WorkspaceArbiter.select() requires at least one candidate")
        winner = max(candidates, key=lambda c: c.salience)
        ignited = winner.salience >= ignition_threshold(affect, mood)
        return WorkspaceBroadcast(
            broadcast_id=str(uuid.uuid4()),
            tick_id=tick_id,
            winner=winner,
            ignited=ignited,
            mineness_tag=mineness_tag(winner),
            ts=datetime.now(UTC),
        )
```

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workspace/test_arbiter.py
from datetime import UTC, datetime

import pytest

from teic.models.affect import AffectState
from teic.models.workspace import WorkspaceCandidate
from teic.workspace.arbiter import (
    WorkspaceArbiter,
    ignition_threshold,
    salience_overrides,
)


def _affect(valence: float = 0.0, arousal: float = 0.0) -> AffectState:
    return AffectState(valence=valence, arousal=arousal, mood=0.0, tick_id=1, ts=datetime.now(UTC))


def _candidate(source: str, salience_parts: tuple[float, float, float, float]) -> WorkspaceCandidate:
    novelty, precision, affective_weight, goal_relevance = salience_parts
    return WorkspaceCandidate(
        source_module=source,
        content={"marker": source},
        novelty=novelty,
        precision=precision,
        affective_weight=affective_weight,
        goal_relevance=goal_relevance,
    )


def test_ignition_threshold_lowers_under_arousal_and_negative_mood():
    calm = ignition_threshold(_affect(arousal=0.0), mood=0.0)
    stressed = ignition_threshold(_affect(arousal=1.0), mood=-1.0)
    assert stressed < calm


def test_select_picks_max_salience_winner():
    low = _candidate("a", (0.2, 0.2, 0.2, 0.2))
    high = _candidate("b", (0.9, 0.9, 0.9, 0.9))
    broadcast = WorkspaceArbiter().select([low, high], _affect(), mood=0.0, tick_id=1)
    assert broadcast.winner.source_module == "b"


def test_subthreshold_winner_is_not_ignited_but_still_scored():
    weak = _candidate("weak", (0.1, 0.1, 0.1, 0.1))  # salience = 0.0001
    broadcast = WorkspaceArbiter().select([weak], _affect(arousal=0.0), mood=0.0, tick_id=1)
    assert broadcast.ignited is False
    assert broadcast.winner.source_module == "weak"  # still selected, just not broadcast-eligible


def test_suprathreshold_winner_is_ignited():
    strong = _candidate("strong", (0.95, 0.95, 0.95, 0.95))
    broadcast = WorkspaceArbiter().select([strong], _affect(arousal=0.0), mood=0.0, tick_id=1)
    assert broadcast.ignited is True


def test_select_requires_at_least_one_candidate():
    with pytest.raises(ValueError):
        WorkspaceArbiter().select([], _affect(), mood=0.0, tick_id=1)


def test_salience_overrides_covers_every_candidate_by_source():
    a = _candidate("a", (0.5, 0.5, 0.5, 0.5))
    b = _candidate("b", (0.1, 0.1, 0.1, 0.1))
    overrides = salience_overrides([a, b], winner=a)
    assert set(overrides) == {"a", "b"}
    assert overrides["a"] == pytest.approx(1.0 + a.salience)
    assert overrides["b"] == pytest.approx(1.0 + b.salience)
```

- [ ] **Step 2: Run to verify failure** (`ModuleNotFoundError` /
  `ImportError` for `teic.workspace.arbiter`, `teic.workspace.mineness`)

Run: `pytest tests/test_workspace/test_arbiter.py -v`

- [ ] **Step 3: Implement `arbiter.py`** as above (depends on Task 2's
  `mineness.py` existing — do Task 2 first, or stub `mineness_tag` inline
  and swap the import once Task 2 lands; recommended order is Task 2 then
  Task 1's implementation step, tests can be written in either order)

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_workspace/test_arbiter.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add teic/workspace/arbiter.py teic/workspace/mineness.py tests/test_workspace/test_arbiter.py tests/test_workspace/test_mineness.py
git commit -m "Phase 5 Task 1+2: workspace arbiter + mineness tagging"
```

---

## Task 2: `teic/workspace/mineness.py` — self/other/ambiguous tagging

**Files:**
- Create: `teic/workspace/mineness.py`
- Test: `tests/test_workspace/test_mineness.py`

**Interfaces:**
- Consumes: `WorkspaceCandidate`.
- Produces: `mineness_tag(candidate: WorkspaceCandidate) -> Literal["self",
  "other", "ambiguous"]` — consumed by `arbiter.py` (Task 1).

```python
"""Self/other/ambiguous provenance tagging for the winning candidate.

Phase 5 scope ruling: the only live candidate sources are agent-internal
("interoception", "memory" -- see phase5-plan.md's scope ruling 1), so
every real call this phase returns "self". "user_input" is dispatched to
"other" now, ahead of Phase 9 actually producing that source, so wiring a
real user-input candidate later needs no change here. No live source
produces "ambiguous" yet -- that's an honest gap, not a placeholder; it
waits for a source that can itself be uncertain about its own provenance
(e.g. a mis-attributed effector outcome), not built yet.
"""

from __future__ import annotations

from typing import Literal

from teic.models.workspace import WorkspaceCandidate

MineessTag = Literal["self", "other", "ambiguous"]

_OTHER_SOURCES = {"user_input"}


def mineness_tag(candidate: WorkspaceCandidate) -> MineessTag:
    if candidate.source_module in _OTHER_SOURCES:
        return "other"
    return "self"
```

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workspace/test_mineness.py
from teic.models.workspace import WorkspaceCandidate
from teic.workspace.mineness import mineness_tag


def _candidate(source: str) -> WorkspaceCandidate:
    return WorkspaceCandidate(
        source_module=source, content={}, novelty=0.5, precision=0.5,
        affective_weight=0.5, goal_relevance=0.5,
    )


def test_interoception_and_memory_are_self():
    assert mineness_tag(_candidate("interoception")) == "self"
    assert mineness_tag(_candidate("memory")) == "self"


def test_user_input_is_other():
    assert mineness_tag(_candidate("user_input")) == "other"
```

- [ ] **Step 2: Run to verify failure**

Run: `pytest tests/test_workspace/test_mineness.py -v`

- [ ] **Step 3: Implement** as above

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_workspace/test_mineness.py -v`
Expected: PASS

- [ ] **Step 5: Commit** — bundled with Task 1's commit above (both land
  together since `arbiter.py` imports `mineness.py`).

---

## Task 3: `teic/workspace/broadcast.py` gate function; wire arbiter into `daemon._on_tick`, persist `workspace_broadcast`

**Files:**
- Create: `teic/workspace/broadcast.py`
- Test: `tests/test_workspace/test_broadcast.py`
- Modify: `teic/daemon.py`
- Modify: `teic/interoception/modulation.py`
  (`ModulationCompute.compute()` gains an optional parameter)
- Test: `tests/test_daemon.py` (extend)

**3.0 `teic/workspace/broadcast.py`** — the actual enforcement point for
"never broadcasts/reports." `assemble_prompt()` (Phase 0) is a pure
formatter with no `ignited` check of its own — by design, per its own
docstring, its job is only to guarantee no raw-state parameter exists, not
to gate on ignition. This module is the seam that does gate on ignition,
and it's the only seam Phase 6 should call once it wires a real OpenRouter
send:

```python
"""The ignition gate for turning a WorkspaceBroadcast into an LLM prompt.

assemble_prompt() (teic/llm/prompt_assembly.py) is a pure formatter -- it
has no ignited check of its own, by design (its job is only the no-raw-state
type boundary). This module is the actual "never broadcasts/reports below
threshold" enforcement point: render_prompt_if_ignited() returns None for
any non-ignited broadcast, full stop, before assemble_prompt ever sees it.
daemon.py does not call this yet (Phase 5 scope ruling 2 -- no real
OpenRouter send exists until Phase 6's viability accounting can gate spend),
but this is the seam Phase 6 wires its real send through, so the enforcement
point is real and tested now, not deferred alongside the send itself.
"""

from __future__ import annotations

from teic.interoception.modulation import ModulationParams
from teic.llm.client import ChatPrompt
from teic.llm.prompt_assembly import assemble_prompt
from teic.models.workspace import WorkspaceBroadcast


def render_prompt_if_ignited(
    broadcast: WorkspaceBroadcast,
    narrative_tail: list[str],
    modulation: ModulationParams,
) -> ChatPrompt | None:
    if not broadcast.ignited:
        return None
    return assemble_prompt(broadcast, narrative_tail, modulation)
```

- [ ] Write `tests/test_workspace/test_broadcast.py` (a sub-threshold
  broadcast → `render_prompt_if_ignited` returns `None`; a supra-threshold
  broadcast → returns a `ChatPrompt` whose rendered message content
  contains the winner's content), run to confirm failure, implement, run
  to confirm pass, commit alongside Task 1/2's commit or its own — either
  is fine since nothing else depends on ordering here.

**Interfaces:**
- Consumes: `WorkspaceArbiter.select`, `salience_overrides`
  (Task 1), `MemoryStore.query`/`create` (Phase 4, unchanged signatures).
- Produces: `daemon._on_tick` now writes one `workspace_broadcast` row per
  tick and carries `self._prior_salience_overrides: dict[str, float]`
  forward tick-to-tick.

**3a. `teic/interoception/modulation.py`** — extend `compute()`:

```python
    def compute(
        self,
        registers: RegisterState,
        affect: AffectState,
        mood: float,
        prior_salience_overrides: dict[str, float] | None = None,
    ) -> ModulationParams:
        ...
        # salience_weight_overrides <- per-source multipliers. "embodiment"
        # is Phase 2's own named example (latency_strain up-weights
        # embodiment candidates); Phase 5 folds in last tick's real
        # per-candidate salience (arbiter.salience_overrides) on top -- this
        # is the "sub-threshold candidate still modulates" pathway, and it
        # runs whether or not last tick's winner was ignited.
        salience_weight_overrides = {"embodiment": 1.0 + registers.latency_strain}
        if prior_salience_overrides is not None:
            salience_weight_overrides.update(prior_salience_overrides)
```

(Keep the rest of `compute()` unchanged; only the signature and this one
block change. Update the module docstring's "Several fields ... have no
consumer yet" sentence to drop `salience_weight_overrides` from that list
and note it's now real as of Phase 5.)

**3b. `teic/daemon.py`** — in `__init__`, add:

```python
        self._prior_salience_overrides: dict[str, float] | None = None
```

In `_on_tick`, after the existing register/affect/modulation block (i.e.
right where the Phase 4 memory-write comment currently sits), replace the
Phase 4 memory-write block with this sequence (candidate collection must
happen *before* `store.create()` writes this tick's own memory, per scope
ruling 1):

```python
        # Phase 5: collect this tick's real candidates, arbitrate, persist
        # the broadcast, and fold every candidate's salience forward into
        # next tick's ModulationParams -- see phase5-plan.md scope ruling 1.
        assert self._memory_store is not None
        content = f"tick {tick_id}: valence={affect_state.valence:.3f} arousal={affect_state.arousal:.3f} " + " ".join(
            f"{channel}={value:.3f}" for channel, value in register_values.items()
        )
        mean_variance = sum(register_state.variances.values()) / len(register_state.variances)
        interoception_candidate = WorkspaceCandidate(
            source_module="interoception",
            content={"registers": register_values, "tick_id": tick_id},
            novelty=_clamp01(prediction_error),
            precision=_clamp01(1.0 - mean_variance),
            affective_weight=_clamp01((abs(affect_state.valence) + affect_state.arousal) / 2.0),
            goal_relevance=_clamp01(register_state.goal_gradient),
        )
        candidates = [interoception_candidate]
        memory_results = await self._memory_store.query(
            session_id=self._session_id,
            query_text=content,
            current_tick_id=tick_id,
            current_valence=affect_state.valence,
            current_arousal=affect_state.arousal,
            retrieval_affect_weight=modulation_params.retrieval_affect_weight,
            retrieval_k=1,
        )
        if memory_results:
            top = memory_results[0]
            candidates.append(
                WorkspaceCandidate(
                    source_module="memory",
                    content={"memory_id": top.record.memory_id, "content": top.record.content},
                    novelty=_clamp01(1.0 - top.activation_value),
                    precision=_clamp01(top.semantic_match),
                    affective_weight=_clamp01(abs(top.record.affect_valence)),
                    goal_relevance=0.3,
                )
            )
        broadcast = self._arbiter.select(candidates, affect_state, mood, tick_id)
        await self._conn.execute(
            "INSERT INTO workspace_broadcast (broadcast_id, tick_id, winner_source, salience_score, "
            "novelty, precision_w, affective_w, goal_relevance, ignited, content, mineness_tag) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                broadcast.broadcast_id, tick_id, broadcast.winner.source_module,
                broadcast.winner.salience, broadcast.winner.novelty, broadcast.winner.precision,
                broadcast.winner.affective_weight, broadcast.winner.goal_relevance,
                int(broadcast.ignited), json.dumps(broadcast.winner.content), broadcast.mineness_tag,
            ),
        )
        await self._conn.commit()
        self._prior_salience_overrides = salience_overrides(candidates, broadcast.winner)

        await self._memory_store.create(
            session_id=self._session_id,
            timescale="tau1_working",
            content=content,
            content_kind="episode",
            created_tick_id=tick_id,
            base_activation=1.0,
            decay_alpha=0.5,
            affect_valence=affect_state.valence,
            affect_arousal=affect_state.arousal,
        )
```

Add `_clamp01` as a tiny module-level helper (`max(0.0, min(1.0, x))`) and
the new imports: `from teic.models.workspace import WorkspaceCandidate`,
`from teic.workspace.arbiter import WorkspaceArbiter, salience_overrides`.
Instantiate `self._arbiter = WorkspaceArbiter()` in `start()` alongside the
other per-session objects.

Thread `self._prior_salience_overrides` into the *next* call to
`self._modulation.compute(...)` (the call currently earlier in `_on_tick`
that produces `modulation_params` — pass
`prior_salience_overrides=self._prior_salience_overrides`). Since that call
happens before this tick's own candidate collection, it naturally picks up
*last* tick's overrides — the tick-to-tick lag is the causal pathway being
tested.

Update the module docstring with a "Phase 5:" paragraph covering: real
`workspace_broadcast` rows per tick from real (if narrow, per scope ruling
1) candidates; that ignition never gates the memory write (Phase 4's
honest-proxy content keeps flowing regardless of `ignited`, since it's not
broadcast content); that no OpenRouter call happens on `ignited=True` yet
(scope ruling 2, Phase 6 wires it once viability accounting exists).

**Tests to add** (`tests/test_daemon.py`, extend):
- After `run_n_ticks(5)` on a fresh daemon, `SELECT COUNT(*) FROM
  workspace_broadcast` returns 5 (one row per tick, matching `tick`
  row count — mirrors Phase 4's `memory_record` row-count assertion).
- `SELECT ignited FROM workspace_broadcast` values are all `0` or `1`
  (never `NULL`) and every `mineness_tag` is `'self'` (per scope ruling 3,
  no live "other"/"ambiguous" source exists yet).
- A synthetic run with injected high `epistemic_tension`/`prediction_error`
  (same injection pattern Phase 3's gate test used) produces at least one
  `ignited=1` row where a calm/idle baseline run produces none — a coarse
  smoke assertion that the mechanism is live end-to-end, ahead of Task 4's
  precise dissociation gate.

**Verification:** `pytest tests/test_daemon.py tests/test_workspace -q`
and `mypy teic/daemon.py teic/interoception/modulation.py teic/workspace`.

- [ ] Steps: write the failing extended tests, run to confirm failure,
  make the edits above, run to confirm pass, run `mypy`, commit.

```bash
git add teic/daemon.py teic/interoception/modulation.py tests/test_daemon.py
git commit -m "Phase 5 Task 3: wire arbiter into tick loop, persist workspace_broadcast"
```

---

## Task 4: Phase 5 gate test, docs

Depends on Task 3.

1. `tests/test_gates/test_phase5.py` — the literal gate: "Sub-threshold
   candidate demonstrably modulates but never broadcasts/reports."

```python
"""Phase 5 gate -- PLAN.md Build Order row 5: "Sub-threshold candidate
demonstrably modulates but never broadcasts/reports."

Two-part dissociation, mirroring Phase 2/3/4's gate structure of
same-inputs-except-one-thing:

1. NEVER-BROADCASTS: a candidate engineered to be sub-threshold
   (ignited=False) has content that never reaches `assemble_prompt()`'s
   output and is never marked ignited in the persisted
   `workspace_broadcast` row.
2. DEMONSTRABLY-MODULATES: that same sub-threshold candidate's salience
   still changes `ModulationParams.salience_weight_overrides` on the next
   tick's compute() call, via `arbiter.salience_overrides()` -- proving the
   "can-modulate but cannot-be-broadcast" dual property, not just that
   sub-threshold candidates are silently dropped.
"""

from datetime import UTC, datetime

import pytest

from teic.interoception.modulation import ModulationCompute
from teic.models.affect import AffectState
from teic.models.registers import RegisterState
from teic.models.workspace import WorkspaceCandidate
from teic.workspace.arbiter import WorkspaceArbiter, salience_overrides
from teic.workspace.broadcast import render_prompt_if_ignited


def _affect() -> AffectState:
    return AffectState(valence=0.0, arousal=0.0, mood=0.0, tick_id=1, ts=datetime.now(UTC))


def _neutral_registers(**overrides: float) -> RegisterState:
    base = dict.fromkeys(
        ("context_pressure", "budget_reserve", "burn_rate", "prediction_error",
         "surprise_volatility", "effector_integrity", "latency_strain",
         "epistemic_tension", "goal_gradient", "memory_fragmentation", "social_contact"),
        0.0,
    )
    base.update(overrides)
    variances = dict.fromkeys(base, 0.01)
    return RegisterState(tick_id=1, ts=datetime.now(UTC), variances=variances, **base)


SECRET_MARKER = "sub-threshold-secret-content"
LOUD_MARKER = "supra-threshold-loud-content"


def test_subthreshold_candidate_never_reaches_rendered_prompt():
    weak = WorkspaceCandidate(
        source_module="memory", content={"text": SECRET_MARKER},
        novelty=0.1, precision=0.1, affective_weight=0.1, goal_relevance=0.1,
    )
    broadcast = WorkspaceArbiter().select([weak], _affect(), mood=0.0, tick_id=1)
    assert broadcast.ignited is False
    assert broadcast.winner.content["text"] == SECRET_MARKER  # arbiter still scored it

    modulation = ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=5.0).compute(
        _neutral_registers(), _affect(), mood=0.0
    )
    prompt = render_prompt_if_ignited(broadcast, narrative_tail=[], modulation=modulation)
    # The actual non-negotiable: below threshold, no prompt is even
    # constructed -- SECRET_MARKER never reaches a renderable message.
    assert prompt is None


def test_suprathreshold_candidate_does_reach_rendered_prompt():
    strong = WorkspaceCandidate(
        source_module="interoception", content={"text": LOUD_MARKER},
        novelty=0.95, precision=0.95, affective_weight=0.95, goal_relevance=0.95,
    )
    broadcast = WorkspaceArbiter().select([strong], _affect(), mood=0.0, tick_id=1)
    assert broadcast.ignited is True

    modulation = ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=5.0).compute(
        _neutral_registers(), _affect(), mood=0.0
    )
    prompt = render_prompt_if_ignited(broadcast, narrative_tail=[], modulation=modulation)
    assert prompt is not None
    rendered = " ".join(m["content"] for m in prompt.messages)
    assert LOUD_MARKER in rendered
    # Contrast case: this is what proves test_subthreshold... isn't just a
    # vacuously-always-None function -- ignition really does gate content
    # reaching a rendered prompt, in both directions.


def test_subthreshold_candidate_still_shifts_next_tick_salience_overrides():
    weak = WorkspaceCandidate(
        source_module="memory", content={"text": SECRET_MARKER},
        novelty=0.1, precision=0.1, affective_weight=0.1, goal_relevance=0.1,
    )
    strong_other = WorkspaceCandidate(
        source_module="interoception", content={}, novelty=0.5, precision=0.5,
        affective_weight=0.5, goal_relevance=0.5,
    )
    broadcast = WorkspaceArbiter().select([weak, strong_other], _affect(), mood=0.0, tick_id=1)
    assert broadcast.winner.source_module == "interoception"  # weak lost the competition
    assert broadcast.ignited is True  # winner happens to be supra-threshold this tick

    overrides = salience_overrides([weak, strong_other], broadcast.winner)
    compute = ModulationCompute(idle_tempo_hz=0.2, max_tempo_hz=5.0)
    without = compute.compute(_neutral_registers(), _affect(), mood=0.0)
    with_prior = compute.compute(
        _neutral_registers(), _affect(), mood=0.0, prior_salience_overrides=overrides
    )
    assert with_prior.salience_weight_overrides["memory"] == pytest.approx(1.0 + weak.salience)
    assert "memory" not in without.salience_weight_overrides
    # The losing, never-broadcast candidate still moved next tick's
    # modulation params -- the "demonstrably modulates" half of the gate.
```

2. `BUILD_STATUS.md`: mark Phase 5 row "**Complete**", add a "## Phase 5 —
   complete" section in the existing phases' style (bullets referencing
   this plan's four scope rulings in substance), plus a "How to verify
   this phase yourself" block matching Phases 0-4's format
   (`pytest -q`, `mypy`, `python -m teic` note about `workspace_broadcast`
   rows).
3. `ARCHITECTURE.md`: append "### Phase 5 — Workspace arbiter, ignition
   threshold, broadcast (complete)" to the Phase log, stating: the narrow
   two-source candidate scope and why (ruling 1); that no OpenRouter call
   is wired yet and why (ruling 2, deferred to Phase 6's viability
   accounting); that `mineness_tag` is a real dispatch that only ever
   returns `"self"` today, by data availability not by stub (ruling 3);
   the ignition threshold formula and that it's a documented design
   choice, not a literature citation (ruling 4); that
   `salience_weight_overrides` (computed with "no consumer yet" since
   Phase 2) is now real and consumed via `arbiter.salience_overrides()`
   folded into the next tick's `ModulationCompute.compute()`.
4. Commit `docs/plans/phase5-plan.md` itself alongside Task 1's commit
   (not deferred to this final task, per the note phase4-plan.md itself
   left about phase3-plan.md's oversight).

**Verification:** full `pytest -q` and project-wide `mypy` before
reporting done; include exact commands and output in the report. Phase 5
is not a named hard-stop in `PLAN.md`, but still report completion and
wait rather than starting Phase 6 unannounced in the same turn.
