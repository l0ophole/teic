# Phase 10 Plan — Narrative Constructor

Gate (not in the original `docs/PlanBuildTEIC.md` BUILD ORDER — this phase
closes a gap the architecture always specced but no phase ever scheduled):
**`narrative_tail` is populated from a real, broadcast-derived inner
monologue, and a second chat turn demonstrably references the first.**

## Why this phase exists

`PLAN.md:56` and `ARCHITECTURE.md:15` list `narrative_constructor` under
`teic/workspace/` alongside `arbiter`, `broadcast`, `mineness`,
`self_model`, `metacognition`. `docs/PlanBuildTEIC.md:124` specs its job:
*"an inner monologue stitching broadcasts into an autobiography—the
'stream of consciousness' is the ordered, narrated sequence of
broadcasts."* `teic/llm/prompt_assembly.py:4-5` already documents its
consumer-side contract: `narrative_tail` is *"a slice of the narrative
constructor's monologue (also broadcast-derived)."*

No phase 0-9 ever builds `teic/workspace/narrative_constructor.py`. Every
call site that assembles a real prompt (`teic/daemon.py:760`) hardcodes
`narrative_tail=[]`. This is why the agent has no continuity across turns
even within one session — not deliberate amnesia (that's Phase 8's
transcript-only *control*, a separate agent used only for comparison
inside the assessment harness, not a statement about this agent's design)
and not a plumbing typo — it's a named, specced module that fell out of
the build order.

**Hard constraint carried over from Phase 2/5:** `assemble_prompt()`'s
`FORBIDDEN_PARAM_TYPES = {"RegisterState", "AffectState", "SelfModel"}`
(`teic/llm/prompt_assembly.py:20`) stays exactly as-is. `narrative_tail`
must be built *only* from already-broadcast, already-arbitrated content
(`workspace_broadcast` rows / `llm_call_log` responses keyed to ignited
ticks) — never by reaching into raw interoceptive/self-model state to
"summarize" it into text. If a task below would require touching that
signature or its forbidden-types set, stop and flag it; that guardrail is
mypy- and test-enforced on purpose (`tests/test_llm/test_prompt_assembly.py`
inspects `__annotations__`).

Existing scaffolding to build on (do not recreate):
- `teic/persistence/migrations/0003_telemetry.sql` — `workspace_broadcast`
  table already persists every tick's `winner_source`, `content`
  (JSON-serialized `WorkspaceCandidate.content`), `ignited`, and
  `mineness_tag`. This is the primary raw material — no new persistence
  should be needed for the broadcast side.
- `teic/daemon.py:471` (`llm_call_log` insert) — the agent's own reply
  text is already persisted in `llm_call_log.response`, keyed by
  `tick_id`. The monologue needs both sides of a turn (what the user/other
  broadcast said, what the agent said back), and both already exist in
  the DB; this phase reads and stitches, it does not add a new write path
  for conversational content.
- `teic/workspace/mineness.py` — tags each broadcast `self`/`other`/
  `ambiguous`. **Known bug to fix as part of this phase, not a separate
  ticket:** `_OTHER_SOURCES = {"user_input"}` but `teic/daemon.py:644` uses
  `source_module="user_message"` — real user turns are currently
  mistagged `"self"`. The narrative constructor's phrasing (e.g. "you
  said" vs "I said") depends on this being correct, so it must be fixed
  before or as part of task 2 below.
- `teic/llm/prompt_assembly.py` — the consumer contract already exists
  (`narrative_tail: list[str]`, truncated to last 5,
  `tests/test_interoception/test_modulation.py:64` already exercises it
  with real content). This phase does not change that function.
- `teic/workspace/broadcast.py`'s `render_prompt_if_ignited()` — the one
  call site (`teic/daemon.py:760`) that must stop passing `[]`.

## File-by-file build order

1. **`teic/workspace/mineness.py`** (edit) — fix `_OTHER_SOURCES` to match
   the real candidate source name (`"user_message"`, not `"user_input"`);
   check `teic/daemon.py` for any other source-module string drift before
   assuming this is the only mismatch. Add/update
   `tests/test_workspace/test_mineness.py` to cover the real source name.
2. **`teic/models/workspace.py`** (edit, check first) — decide whether a
   new small model is needed (e.g. `NarrativeLine`) or whether the
   constructor can work directly off `WorkspaceBroadcast` +
   `llm_call_log` rows without a new pydantic type. Prefer no new model
   unless the query/render step genuinely needs one.
3. **`teic/workspace/narrative_constructor.py`** (new) — the module
   PLAN.md/ARCHITECTURE.md already name. Given a session_id and a window
   (last N ignited ticks, or last-N-minutes — decide at cp1), queries
   `workspace_broadcast` (ignited=1) joined against `llm_call_log` by
   `tick_id`, and renders each turn into one short narrated line using
   `mineness_tag` for voice ("you: ...", "I: ...") — no LLM call, no
   raw-state access, pure formatting over already-broadcast content.
   Exposes one function, e.g. `build_narrative_tail(session_id, ...) ->
   list[str]`, matching the shape `assemble_prompt` already expects.
4. **`teic/persistence/db.py`** (edit, only if task 3's query needs an
   index) — add an index on `workspace_broadcast(session_id?, tick_id)` or
   similar if the query is slow; confirm `workspace_broadcast` actually
   has a `session_id` column first (schema above does not show one — may
   need a migration to add it, since without it the query can't be scoped
   to one session). Check this at cp1 before assuming it's free.
5. **`teic/daemon.py`** (edit) — replace the hardcoded `[]` at line 760
   with a call into `narrative_constructor.build_narrative_tail(...)`;
   decide whether this is computed fresh every ignited tick or cached and
   invalidated (perf: don't re-query `workspace_broadcast` every tick if
   it's expensive — measure first, don't pre-optimize).
6. **`tests/test_workspace/test_narrative_constructor.py`** (new) —
   construction from real persisted broadcast/llm_call_log rows (not
   hand-authored strings); ordering is tick-ascending; mineness-correct
   voice per line; truncation/window behavior; empty-session case returns
   `[]` cleanly (must not break the existing "no narrative_tail" behavior
   `render_prompt_if_ignited` already handles).
7. **`tests/test_gates/test_phase10.py`** (new) — the gate test: run a
   seeded daemon through two real ignited user turns in one session,
   assert the second turn's assembled prompt's `narrative_tail` contains
   a rendering of the first turn's content (user text and/or the agent's
   own reply) — i.e. a directly observable "the agent's second prompt
   references the first" assertion, not just a unit test on the
   formatter in isolation.
8. **`BUILD_STATUS.md`** / **`ARCHITECTURE.md`** — Phase 10 row + section,
   per Notes discipline (one line + pointer to
   `docs/plans/phase10-notes.md`).

## Checkpoints

- cp1: constructor-core - Tasks 1-3 done: mineness source-name bug fixed
  and tested, `narrative_constructor.py` built and unit-tested against
  real persisted `workspace_broadcast`/`llm_call_log` rows, decision
  recorded (in phase10-notes.md) on window size and whether a new
  `session_id` column/migration was needed on `workspace_broadcast`. Not
  yet wired into the daemon's real send path.
- cp2: daemon-wiring - Tasks 4-6 done: `teic/daemon.py:760` no longer
  hardcodes `[]`, real narrative_tail flows into `assemble_prompt()`
  through the unchanged `render_prompt_if_ignited()` seam,
  `FORBIDDEN_PARAM_TYPES` guardrail untouched and its test still passes,
  `test_narrative_constructor.py` green.
- cp3: gate-and-docs - Task 7-8 done: `test_phase10.py` demonstrates a
  real second-turn prompt referencing the first turn's content end to
  end, full `pytest -q` + `mypy` batch clean, BUILD_STATUS.md and
  ARCHITECTURE.md updated.

## Context to read at each checkpoint resume

- `docs/plans/phase10-plan.md` (this file)
- `BUILD_STATUS.md` — status table + current-state section only
- Files named in the task list above for the checkpoint being resumed;
  use offset/limit on large ones (`teic/daemon.py`, `teic/persistence/
  migrations/0003_telemetry.sql`)
- Do not re-read `PLAN.md`, `ARCHITECTURE.md`, or prior phase notes beyond
  the specific lines cited above unless a task explicitly says to check
  one further
