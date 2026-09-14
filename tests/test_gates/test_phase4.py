"""Phase 4 gate: "Retrieval ranking shifts with affect; activation decay
fits power-law, not exponential." -- the literal Build Order wording.

Two independent halves, per the two clauses of that sentence:

1. **Power-law, not exponential**: `teic/memory/decay.py`'s `activation()`
   is compared against an exponential curve matched to agree at
   `elapsed=0` and `elapsed=DECAY_C`, and its value at a much larger
   `elapsed` must still be substantially higher (the heavier-tail
   signature a polynomial decay has and an exponential does not). This is
   the same assertion `tests/test_memory/test_decay.py::
   test_activation_power_law_has_heavier_tail_than_matched_exponential`
   makes at the unit level; it's repeated here (not imported) because gate
   tests are meant to stand alone as the single artifact that proves a
   phase's headline claim, per Phase 0-3's own gate test convention.

2. **Retrieval ranking shifts with affect**: unlike
   `tests/test_memory/test_retrieval.py::test_rank_top_result_swaps_with_affect_sign`
   (which calls `retrieval.rank()` directly with hand-supplied
   `semantic_matches`), this drives the *full* `MemoryStore.query()` path
   -- a real temp-file SQLite DB, real sqlite-vec kNN, real `retrieval.rank()`
   composition -- through a fake (hash-based) embedder so it needs neither
   network access nor the real ~90MB model. Exercising the whole
   `store.py` -> `vector_index.py` -> `retrieval.py` chain end-to-end,
   not just the pure ranking function, is what makes this a gate test
   rather than a restatement of the unit test.
"""

from __future__ import annotations

import math
from pathlib import Path

import aiosqlite

from teic.memory import vector_index
from teic.memory.decay import DECAY_C, activation
from teic.memory.store import MemoryStore
from teic.models.memory import MemoryRecord
from teic.persistence.db import open_db
from tests.test_memory.test_store import FakeEmbeddingModel


def _record(memory_id: str, **overrides: object) -> MemoryRecord:
    defaults: dict[str, object] = dict(
        memory_id=memory_id,
        session_id="s1",
        timescale="tau1_working",
        content="c",
        content_kind="episode",
        created_tick_id=0,
        last_access_tick_id=None,
        base_activation=1.0,
        decay_alpha=1.0,
        affect_valence=0.0,
        affect_arousal=0.0,
        access_count=0,
    )
    defaults.update(overrides)
    return MemoryRecord(**defaults)  # type: ignore[arg-type]


def test_activation_decay_has_power_law_not_exponential_tail() -> None:
    base = 1.0
    record = _record("m", base_activation=base, decay_alpha=1.0, created_tick_id=0)

    power_at_c = activation(record, current_tick_id=int(DECAY_C))
    k = -math.log(power_at_c / base) / DECAY_C

    def exp_decay(elapsed: float) -> float:
        return base * math.exp(-elapsed * k)

    large_elapsed = 2000
    power_value = activation(record, current_tick_id=large_elapsed)
    exp_value = exp_decay(large_elapsed)

    assert power_value >= 3 * exp_value, (
        f"expected the power-law formula's heavier tail at elapsed={large_elapsed} "
        f"(power={power_value}, matched-exponential={exp_value})"
    )


async def _seeded_store(tmp_path: Path) -> tuple[aiosqlite.Connection, MemoryStore]:
    conn = await open_db(tmp_path / "gate4.db")
    await vector_index.ensure_loaded(conn)
    await vector_index.ensure_table(conn)
    await conn.execute(
        "INSERT INTO session (session_id, started_at, config_snapshot) VALUES ('s1', '2026-01-01T00:00:00', '{}')"
    )
    await conn.execute(
        "INSERT INTO tick (tick_id, session_id, tick_index, wall_ts, dt_real, dt_subjective, tempo_hz) "
        "VALUES (1, 's1', 0, '2026-01-01T00:00:00', 1.0, 1.0, 1.0)"
    )
    await conn.commit()
    store = MemoryStore(conn, FakeEmbeddingModel())
    await store.create(
        session_id="s1", timescale="tau1_working", content="congruent memory content",
        content_kind="episode", created_tick_id=1, base_activation=1.0,
        decay_alpha=0.5, affect_valence=0.6, affect_arousal=0.6,
    )
    await store.create(
        session_id="s1", timescale="tau1_working", content="congruent memory content",
        content_kind="episode", created_tick_id=1, base_activation=1.0,
        decay_alpha=0.5, affect_valence=-0.8, affect_arousal=-0.8,
    )
    return conn, store


async def test_retrieval_ranking_top_result_swaps_with_retrieval_affect_weight_sign(
    tmp_path: Path,
) -> None:
    conn, store = await _seeded_store(tmp_path)
    try:
        # Both memories have identical content (=> identical semantic_match
        # from the same query), so only affect congruence can break the tie.
        positive = await store.query(
            session_id="s1", query_text="congruent memory content", current_tick_id=1,
            current_valence=0.6, current_arousal=0.6,
            retrieval_affect_weight=1.0, retrieval_k=2,
        )
        negative = await store.query(
            session_id="s1", query_text="congruent memory content", current_tick_id=1,
            current_valence=0.6, current_arousal=0.6,
            retrieval_affect_weight=-1.0, retrieval_k=2,
        )
        assert positive[0].record.affect_valence == 0.6
        assert negative[0].record.affect_valence == -0.8
        assert positive[0].record.memory_id != negative[0].record.memory_id
    finally:
        await conn.close()


async def test_retrieval_ranking_stable_without_affect_weight(tmp_path: Path) -> None:
    """Contrast, mirroring Phase 3's gate test contrast pattern: with
    retrieval_affect_weight=0.0, ranking is driven by semantic_match/
    activation alone and is stable across repeated identical calls --
    proving affect (not noise) is what moved the ranking above."""
    conn, store = await _seeded_store(tmp_path)
    try:
        first = await store.query(
            session_id="s1", query_text="congruent memory content", current_tick_id=1,
            current_valence=0.6, current_arousal=0.6,
            retrieval_affect_weight=0.0, retrieval_k=2,
        )
        second = await store.query(
            session_id="s1", query_text="congruent memory content", current_tick_id=1,
            current_valence=0.6, current_arousal=0.6,
            retrieval_affect_weight=0.0, retrieval_k=2,
        )
        assert [s.record.memory_id for s in first] == [s.record.memory_id for s in second]
    finally:
        await conn.close()
