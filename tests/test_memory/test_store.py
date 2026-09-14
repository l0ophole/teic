"""Uses a fake `EmbeddingModel` (a deterministic hash-based vector) so this
test needs neither the real ~90MB sentence-transformers model nor network
access -- only `store.py`'s SQL/sqlite-vec composition is under test here,
not embedding quality."""

from __future__ import annotations

import hashlib
from pathlib import Path

import aiosqlite

from teic.memory import vector_index
from teic.memory.embeddings import EMBEDDING_DIM
from teic.memory.store import MemoryStore
from teic.persistence.db import open_db


class FakeEmbeddingModel:
    def encode(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode()).digest()
        return [(digest[i % len(digest)] / 255.0) for i in range(EMBEDDING_DIM)]


async def _open(tmp_path: Path) -> aiosqlite.Connection:
    """Opens a fresh migrated DB and seeds the `session`/`tick` rows
    `memory_record`'s foreign keys require (`session_id="s1"`,
    `tick_id in (1, 2)` -- matching the tick ids the tests below use)."""
    conn = await open_db(tmp_path / "store_test.db")
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


async def test_create_then_get_round_trips(tmp_path: Path) -> None:
    conn = await _open(tmp_path)
    try:
        store = MemoryStore(conn, FakeEmbeddingModel())
        created = await store.create(
            session_id="s1",
            timescale="tau1_working",
            content="tick 1: valence=0.1",
            content_kind="episode",
            created_tick_id=1,
            base_activation=1.0,
            decay_alpha=0.5,
            affect_valence=0.1,
            affect_arousal=0.0,
        )
        assert created.embedding is not None
        fetched = await store.get(created.memory_id)
        assert fetched is not None
        assert fetched.content == "tick 1: valence=0.1"
        assert fetched.base_activation == 1.0
    finally:
        await conn.close()


async def test_touch_updates_access_without_changing_base_activation(tmp_path: Path) -> None:
    conn = await _open(tmp_path)
    try:
        store = MemoryStore(conn, FakeEmbeddingModel())
        created = await store.create(
            session_id="s1", timescale="tau1_working", content="c",
            content_kind="episode", created_tick_id=1, base_activation=1.0,
            decay_alpha=0.5, affect_valence=0.0, affect_arousal=0.0,
        )
        await store.touch(created.memory_id, tick_id=2)
        fetched = await store.get(created.memory_id)
        assert fetched is not None
        assert fetched.last_access_tick_id == 2
        assert fetched.access_count == 1
        assert fetched.base_activation == 1.0
    finally:
        await conn.close()


async def test_query_ranks_by_semantic_and_affect(tmp_path: Path) -> None:
    conn = await _open(tmp_path)
    try:
        store = MemoryStore(conn, FakeEmbeddingModel())
        target = await store.create(
            session_id="s1", timescale="tau1_working", content="target content",
            content_kind="episode", created_tick_id=1, base_activation=1.0,
            decay_alpha=0.5, affect_valence=0.5, affect_arousal=0.5,
        )
        await store.create(
            session_id="s1", timescale="tau1_working", content="unrelated other",
            content_kind="episode", created_tick_id=1, base_activation=1.0,
            decay_alpha=0.5, affect_valence=-0.5, affect_arousal=-0.5,
        )
        results = await store.query(
            session_id="s1", query_text="target content", current_tick_id=2,
            current_valence=0.5, current_arousal=0.5,
            retrieval_affect_weight=1.0, retrieval_k=2,
        )
        assert results[0].record.memory_id == target.memory_id
        touched = await store.get(target.memory_id)
        assert touched is not None
        assert touched.access_count == 1
    finally:
        await conn.close()
