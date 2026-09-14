from __future__ import annotations

from pathlib import Path

import aiosqlite

from teic.memory import vector_index
from teic.memory.consolidation import (
    CONSOLIDATION_MIN_GROUP_SIZE,
    consolidate_group,
    find_consolidation_candidates,
    run_consolidation_pass,
)
from teic.memory.store import MemoryStore
from teic.models.memory import MemoryRecord
from teic.persistence.db import open_db
from tests.test_memory.test_store import FakeEmbeddingModel


def _record(memory_id: str, **overrides: object) -> MemoryRecord:
    defaults: dict[str, object] = dict(
        memory_id=memory_id,
        session_id="s1",
        timescale="tau1_working",
        content=f"content-{memory_id}",
        content_kind="episode",
        created_tick_id=0,
        last_access_tick_id=0,
        base_activation=1.0,
        decay_alpha=1.0,
        affect_valence=0.1,
        affect_arousal=0.1,
        access_count=0,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)  # type: ignore[arg-type]


def test_find_candidates_excludes_wrong_timescale_and_superseded() -> None:
    stale = [_record(f"stale{i}", created_tick_id=0, last_access_tick_id=0) for i in range(3)]
    semantic = _record("sem", timescale="tau3_semantic", created_tick_id=0, last_access_tick_id=0)
    superseded = _record("sup", created_tick_id=0, last_access_tick_id=0, superseded_by="other")
    candidates = find_consolidation_candidates(
        stale + [semantic, superseded], current_tick_id=10_000
    )
    assert {c.memory_id for c in candidates} == {"stale0", "stale1", "stale2"}


def test_find_candidates_returns_empty_under_min_group_size() -> None:
    few = [_record(f"r{i}", created_tick_id=0, last_access_tick_id=0) for i in range(CONSOLIDATION_MIN_GROUP_SIZE - 1)]
    assert find_consolidation_candidates(few, current_tick_id=10_000) == []


def test_consolidate_group_aggregates_fields() -> None:
    records = [
        _record("a", content="alpha", base_activation=0.5, decay_alpha=0.4, affect_valence=0.2, affect_arousal=0.0),
        _record("b", content="beta", base_activation=0.9, decay_alpha=0.6, affect_valence=-0.2, affect_arousal=0.4),
        _record("c", content="gamma", base_activation=0.3, decay_alpha=0.5, affect_valence=0.0, affect_arousal=0.2),
    ]
    merged = consolidate_group(records, result_tick_id=99)
    assert merged.timescale == "tau4_consolidated"
    assert merged.content_kind == "autobiography_entry"
    for c in ("alpha", "beta", "gamma"):
        assert c in merged.content
    assert merged.base_activation == 0.9
    assert merged.decay_alpha == (0.4 + 0.6 + 0.5) / 3
    assert merged.affect_valence == (0.2 - 0.2 + 0.0) / 3
    assert merged.affect_arousal == (0.0 + 0.4 + 0.2) / 3
    assert merged.created_tick_id == 99


async def _seeded_conn(tmp_path: Path) -> aiosqlite.Connection:
    conn = await open_db(tmp_path / "consolidation_test.db")
    await vector_index.ensure_loaded(conn)
    await vector_index.ensure_table(conn)
    await conn.execute(
        "INSERT INTO session (session_id, started_at, config_snapshot) VALUES ('s1', '2026-01-01T00:00:00', '{}')"
    )
    for tick_id in (1, 2):
        await conn.execute(
            "INSERT INTO tick (tick_id, session_id, tick_index, wall_ts, dt_real, dt_subjective, tempo_hz) "
            "VALUES (?, 's1', ?, '2026-01-01T00:00:00', 1.0, 1.0, 1.0)",
            (tick_id, tick_id),
        )
    await conn.commit()
    return conn


async def test_run_consolidation_pass_merges_and_marks_superseded(tmp_path: Path) -> None:
    conn = await _seeded_conn(tmp_path)
    try:
        store = MemoryStore(conn, FakeEmbeddingModel())
        sources = []
        for i in range(CONSOLIDATION_MIN_GROUP_SIZE):
            created = await store.create(
                session_id="s1", timescale="tau1_working", content=f"stale entry {i}",
                content_kind="episode", created_tick_id=1, base_activation=0.01,
                decay_alpha=1.0, affect_valence=0.0, affect_arousal=0.0,
            )
            sources.append(created)

        event = await run_consolidation_pass(store, session_id="s1", current_tick_id=2)
        assert event is not None
        assert event.result_memory_id is not None
        merged = await store.get(event.result_memory_id)
        assert merged is not None
        assert merged.timescale == "tau4_consolidated"

        for source in sources:
            refreshed = await store.get(source.memory_id)
            assert refreshed is not None
            assert refreshed.superseded_by == event.result_memory_id
    finally:
        await conn.close()


async def test_run_consolidation_pass_returns_none_when_nothing_stale(tmp_path: Path) -> None:
    conn = await _seeded_conn(tmp_path)
    try:
        store = MemoryStore(conn, FakeEmbeddingModel())
        await store.create(
            session_id="s1", timescale="tau1_working", content="fresh",
            content_kind="episode", created_tick_id=2, base_activation=1.0,
            decay_alpha=1.0, affect_valence=0.0, affect_arousal=0.0,
        )
        event = await run_consolidation_pass(store, session_id="s1", current_tick_id=2)
        assert event is None
    finally:
        await conn.close()
