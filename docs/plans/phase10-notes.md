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
