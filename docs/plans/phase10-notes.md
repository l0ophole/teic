# Phase 10 Notes

## cp1: constructor-core

- **Mineness bug**: `_OTHER_SOURCES` said `"user_input"`; the only real
  external source `daemon.py` produces is `"user_message"` (checked all
  `source_module=` call sites — `interoception`, `user_message`,
  `viability`, `memory` — no other drift found).
- **No new model**: `narrative_constructor.py` queries
  `workspace_broadcast` + `llm_call_log` directly; no `NarrativeLine`
  pydantic type needed, matches plan's "prefer no new model" guidance.
- **No new migration/index**: `workspace_broadcast` has no `session_id`
  column, but scoping to a session doesn't need one — join through
  `tick.session_id` (same pattern `tests/test_daemon.py` already used).
  Deferred adding an index on `workspace_broadcast(tick_id)` (already the
  join key, already indexed via its FK/rowid path in sqlite for this
  table size) unless cp2/cp3 perf shows it's needed.
- **Window**: `max_ticks` param, default 20 most-recent ignited ticks
  (ascending order in the returned list); `assemble_prompt` already
  truncates to last 5 lines, so the constructor's window just needs to be
  "generous enough," not exactly tuned.
- **Line shape**: one ignited tick can yield up to two lines — `"you:
  {text}"` when the winning candidate is user-sourced (mineness "other",
  content has a `text` field), and `"I: {response}"` when that tick's
  `llm_call_log` row completed (`status == "ok"` and non-empty
  `response`). A self-sourced ignited tick with no completed response yet
  yields zero lines, not a placeholder.
- Not yet wired into `daemon.py:760` — still hardcoded `[]` (cp2).

## cp2: daemon-wiring

- `daemon.py:_on_tick` now calls `build_narrative_tail(self._conn,
  self._session_id)` and passes the result into `render_prompt_if_ignited`
  in place of `[]`. Only called when `broadcast.ignited` (matches cp1's
  "empty-session/no-ignition returns `[]`" contract; skips a DB round trip
  on non-ignited ticks).
- **Ordering fix vs. plan sketch**: the narrative-tail query now runs
  *before* the current tick's own `workspace_broadcast` INSERT, not after.
  Running it after would let the just-broadcast current-turn content (the
  same content `assemble_prompt` already puts in the `user` message) leak
  into its own "Recent inner monologue" system block as a redundant "you:
  ..." line one tick early. No `narrative_constructor.py` or test change
  needed for this — it's purely a call-site ordering choice in
  `daemon.py`.
- `FORBIDDEN_PARAM_TYPES` / `assemble_prompt` signature: untouched, per
  guardrail; `tests/test_llm/test_prompt_assembly.py` still passes.
- **Pre-existing unrelated hang found while verifying**:
  `tests/test_daemon.py::test_high_arousal_run_ignites_more_than_idle_run`
  hangs indefinitely (reproduced identically on unmodified `main` via
  `git stash`, so not caused by this phase's changes) — same class of
  issue as the post-phase-9 TUI hang (`04a1097`). Deselected for cp2
  verification; not investigated further here, out of scope for Phase 10's
  task list.
- Verified: `tests/test_workspace/`, `tests/test_llm/test_prompt_assembly.py`,
  `tests/test_daemon.py` (deselecting the hang above) all green, mypy
  clean. Full `pytest -q` batch still not run to completion in this
  environment (same as cp1 — see BUILD_STATUS.md).
