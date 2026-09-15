"""Stitches already-broadcast, already-arbitrated content into an inner
monologue -- PLAN.md's `narrative_constructor` module, specced but never
built through Phase 0-9 (see phase10-plan.md).

Pure formatting over persisted rows: no LLM call, no raw interoceptive/
self-model access (that would violate `assemble_prompt`'s
`FORBIDDEN_PARAM_TYPES` guardrail one hop removed). Source material is
exactly the two tables Phase 5/9 already write:
`workspace_broadcast` (ignited=1 rows -- what was broadcast, and to whom
mineness attributes it) and `llm_call_log` (what the agent actually said
back, keyed by `tick_id`). `workspace_broadcast` has no `session_id`
column of its own; it is scoped to a session by joining through
`tick.session_id`, same pattern `tests/test_daemon.py` already uses --
no migration needed (see phase10-notes.md cp1 decision).

One ignited tick can produce up to two narrated lines, in turn order:
a "you: ..." line when the winning candidate is user-sourced (mineness
"other", content carries a `text` field), and an "I: ..." line when that
tick's `llm_call_log` row has a non-empty, successfully-completed
response. A tick can produce zero lines (e.g. a self-sourced ignited
candidate with no textual content and no completed LLM response yet).
"""

from __future__ import annotations

import json

import aiosqlite

DEFAULT_WINDOW_TICKS = 20


async def build_narrative_tail(
    conn: aiosqlite.Connection,
    session_id: str,
    max_ticks: int = DEFAULT_WINDOW_TICKS,
) -> list[str]:
    """Renders the last `max_ticks` ignited ticks of `session_id` into a
    tick-ascending list of narrated lines. Returns `[]` for a session with
    no ignited broadcasts yet -- callers must treat that identically to
    "no narrative_tail" (`render_prompt_if_ignited` already does)."""
    cursor = await conn.execute(
        "SELECT wb.tick_id, wb.mineness_tag, wb.content, "
        "llm.response, llm.status "
        "FROM workspace_broadcast wb "
        "JOIN tick t ON wb.tick_id = t.tick_id "
        "LEFT JOIN llm_call_log llm ON llm.tick_id = wb.tick_id "
        "WHERE t.session_id = ? AND wb.ignited = 1 "
        "ORDER BY wb.tick_id DESC LIMIT ?",
        (session_id, max_ticks),
    )
    rows = list(await cursor.fetchall())
    rows.reverse()

    lines: list[str] = []
    for tick_id, mineness, content_json, response, status in rows:
        content = json.loads(content_json)
        if mineness == "other":
            text = content.get("text")
            if text:
                lines.append(f"you: {text}")
        if status == "ok" and response:
            lines.append(f"I: {response}")
    return lines
