"""Idle-gated tau4 consolidation.

**Structural, not semantic**: there is no LLM-backed cognition loop wired
into the daemon yet (`llm/client.py` exists but nothing calls it from
`_on_tick` -- that's Phase 5+, once the workspace arbiter has real broadcast
content worth summarizing). `consolidate_group()` therefore merges a
cluster of low-activation records into one `tau4_consolidated` record via a
deterministic content join, not an LLM summary. Real LLM-backed
summarization is a later-phase upgrade that slots into this same function's
seam without changing its callers.

Idle-gating is **wall-clock**, not tick-count, per `PLAN.md`'s own open
question #7 ("must be wall-clock-based ... so low-tempo periods don't
starve tau4 consolidation disproportionately") -- `daemon.py`'s
consolidation loop measures `time.monotonic()` against the timestamp of the
last `_on_tick` call, not against `IDLE_THRESHOLD_S`'s ticks.
"""

from __future__ import annotations

from teic.memory.decay import activation
from teic.memory.store import MemoryStore
from teic.models.memory import ConsolidationEvent, MemoryRecord

# Records with activation() below this are consolidation candidates.
CONSOLIDATION_ACTIVATION_FLOOR = 0.15
# Don't consolidate a lone leftover record.
CONSOLIDATION_MIN_GROUP_SIZE = 3
# Wall-clock seconds of no _on_tick activity before daemon.py's background
# task attempts a consolidation pass.
IDLE_THRESHOLD_S = 30.0


def find_consolidation_candidates(
    records: list[MemoryRecord], current_tick_id: int
) -> list[MemoryRecord]:
    """Pure filter: not-yet-superseded tau1/tau2 records whose activation
    has decayed below the floor. Returns `[]` if fewer than
    `CONSOLIDATION_MIN_GROUP_SIZE` qualify -- no group to consolidate."""
    candidates = [
        r
        for r in records
        if r.timescale in ("tau1_working", "tau2_episodic")
        and r.superseded_by is None
        and activation(r, current_tick_id) < CONSOLIDATION_ACTIVATION_FLOOR
    ]
    if len(candidates) < CONSOLIDATION_MIN_GROUP_SIZE:
        return []
    return candidates


def consolidate_group(records: list[MemoryRecord], result_tick_id: int) -> MemoryRecord:
    """Pure: builds the merged tau4_consolidated record. Content is a
    deterministic join of source contents (explicitly not an LLM summary --
    see module docstring). Does not assign `memory_id` or touch the DB;
    `MemoryStore.create()` is the caller's persistence step."""
    content = " | ".join(sorted(r.content for r in records))
    base_activation = max(r.base_activation for r in records)
    decay_alpha = sum(r.decay_alpha for r in records) / len(records)
    affect_valence = sum(r.affect_valence for r in records) / len(records)
    affect_arousal = sum(r.affect_arousal for r in records) / len(records)
    return MemoryRecord(
        memory_id="",  # assigned by MemoryStore.create()
        session_id=records[0].session_id,
        timescale="tau4_consolidated",
        content=content,
        content_kind="autobiography_entry",
        created_tick_id=result_tick_id,
        last_access_tick_id=None,
        base_activation=base_activation,
        decay_alpha=decay_alpha,
        affect_valence=affect_valence,
        affect_arousal=affect_arousal,
        access_count=0,
        embedding=None,
        superseded_by=None,
    )


async def run_consolidation_pass(
    store: MemoryStore, session_id: str, current_tick_id: int
) -> ConsolidationEvent | None:
    tau1 = await store.list_by_timescale(session_id, "tau1_working")
    tau2 = await store.list_by_timescale(session_id, "tau2_episodic")
    candidates = find_consolidation_candidates(tau1 + tau2, current_tick_id)
    if not candidates:
        return None
    merged = consolidate_group(candidates, current_tick_id)
    created = await store.create(
        session_id=merged.session_id,
        timescale=merged.timescale,
        content=merged.content,
        content_kind=merged.content_kind,
        created_tick_id=merged.created_tick_id,
        base_activation=merged.base_activation,
        decay_alpha=merged.decay_alpha,
        affect_valence=merged.affect_valence,
        affect_arousal=merged.affect_arousal,
    )
    for candidate in candidates:
        await store.mark_superseded(candidate.memory_id, created.memory_id)
    event = ConsolidationEvent(
        session_id=session_id,
        tick_id=current_tick_id,
        source_memory_ids=[c.memory_id for c in candidates],
        result_memory_id=created.memory_id,
        trigger="idle_sleep_analog",
    )
    await store.record_consolidation_event(event)
    return event
