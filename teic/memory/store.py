"""`MemoryStore`: the one DB-touching object that composes `decay.py`/
`retrieval.py`'s pure math with real SQLite + sqlite-vec I/O -- same
"pure computation object vs. daemon/store does I/O" split Phase 3
established for `ForwardModel` vs. `daemon.py`.
"""

from __future__ import annotations

import uuid

import aiosqlite

from teic.memory import vector_index
from teic.memory.decay import touch
from teic.memory.embeddings import EmbeddingModel
from teic.memory.retrieval import ScoredMemory, rank
from teic.models.memory import ContentKind, MemoryRecord, Timescale

_COLUMNS = (
    "memory_id, session_id, timescale, content, content_kind, created_tick_id, "
    "last_access_tick_id, base_activation, decay_alpha, affect_valence, "
    "affect_arousal, access_count, embedding_ref, superseded_by"
)


def _row_to_record(row: aiosqlite.Row, embedding: list[float] | None) -> MemoryRecord:
    (
        memory_id,
        session_id,
        timescale,
        content,
        content_kind,
        created_tick_id,
        last_access_tick_id,
        base_activation,
        decay_alpha,
        affect_valence,
        affect_arousal,
        access_count,
        _embedding_ref,
        superseded_by,
    ) = row
    return MemoryRecord(
        memory_id=memory_id,
        session_id=session_id,
        timescale=timescale,
        content=content,
        content_kind=content_kind,
        created_tick_id=created_tick_id,
        last_access_tick_id=last_access_tick_id,
        base_activation=base_activation,
        decay_alpha=decay_alpha,
        affect_valence=affect_valence,
        affect_arousal=affect_arousal,
        access_count=access_count,
        embedding=embedding,
        superseded_by=superseded_by,
    )


class MemoryStore:
    def __init__(self, conn: aiosqlite.Connection, embed: EmbeddingModel) -> None:
        self._conn = conn
        self._embed = embed

    async def create(
        self,
        *,
        session_id: str,
        timescale: Timescale,
        content: str,
        content_kind: ContentKind,
        created_tick_id: int,
        base_activation: float,
        decay_alpha: float,
        affect_valence: float,
        affect_arousal: float,
    ) -> MemoryRecord:
        memory_id = str(uuid.uuid4())
        embedding = self._embed.encode(content)
        cursor = await self._conn.execute(
            f"INSERT INTO memory_record ({_COLUMNS}) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                memory_id,
                session_id,
                timescale,
                content,
                content_kind,
                created_tick_id,
                None,
                base_activation,
                decay_alpha,
                affect_valence,
                affect_arousal,
                0,
                None,
                None,
            ),
        )
        embedding_ref = cursor.lastrowid
        assert embedding_ref is not None
        await self._conn.execute(
            "UPDATE memory_record SET embedding_ref = ? WHERE memory_id = ?",
            (embedding_ref, memory_id),
        )
        await self._conn.commit()
        await vector_index.upsert(self._conn, embedding_ref, embedding)
        return MemoryRecord(
            memory_id=memory_id,
            session_id=session_id,
            timescale=timescale,
            content=content,
            content_kind=content_kind,
            created_tick_id=created_tick_id,
            last_access_tick_id=None,
            base_activation=base_activation,
            decay_alpha=decay_alpha,
            affect_valence=affect_valence,
            affect_arousal=affect_arousal,
            access_count=0,
            embedding=embedding,
            superseded_by=None,
        )

    async def get(self, memory_id: str) -> MemoryRecord | None:
        cursor = await self._conn.execute(
            f"SELECT {_COLUMNS} FROM memory_record WHERE memory_id = ?", (memory_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_record(row, embedding=None)

    async def list_by_timescale(self, session_id: str, timescale: Timescale) -> list[MemoryRecord]:
        cursor = await self._conn.execute(
            f"SELECT {_COLUMNS} FROM memory_record WHERE session_id = ? AND timescale = ?",
            (session_id, timescale),
        )
        rows = await cursor.fetchall()
        return [_row_to_record(row, embedding=None) for row in rows]

    async def touch(self, memory_id: str, tick_id: int) -> None:
        record = await self.get(memory_id)
        if record is None:
            return
        updated = touch(record, tick_id)
        await self._conn.execute(
            "UPDATE memory_record SET last_access_tick_id = ?, access_count = ? WHERE memory_id = ?",
            (updated.last_access_tick_id, updated.access_count, memory_id),
        )
        await self._conn.commit()

    async def mark_superseded(self, memory_id: str, superseded_by: str) -> None:
        await self._conn.execute(
            "UPDATE memory_record SET superseded_by = ? WHERE memory_id = ?",
            (superseded_by, memory_id),
        )
        await self._conn.commit()

    async def query(
        self,
        session_id: str,
        query_text: str,
        current_tick_id: int,
        current_valence: float,
        current_arousal: float,
        retrieval_affect_weight: float,
        retrieval_k: int,
    ) -> list[ScoredMemory]:
        query_embedding = self._embed.encode(query_text)
        cursor = await self._conn.execute(
            "SELECT embedding_ref, memory_id FROM memory_record WHERE session_id = ? AND embedding_ref IS NOT NULL",
            (session_id,),
        )
        rows = await cursor.fetchall()
        ref_to_id = {int(ref): memory_id for ref, memory_id in rows}
        # Cast a wide net: sqlite-vec's k caps candidates, so ask for more
        # than retrieval_k to leave room for affect re-ranking to matter.
        similarities = await vector_index.query_similar(
            self._conn, query_embedding, k=max(retrieval_k * 3, retrieval_k)
        )
        semantic_matches = {
            ref_to_id[ref]: sim for ref, sim in similarities.items() if ref in ref_to_id
        }
        records = [r for r in (await self._records(list(semantic_matches))) if r is not None]
        results = rank(
            records,
            semantic_matches,
            current_tick_id,
            current_valence,
            current_arousal,
            retrieval_affect_weight,
            retrieval_k,
        )
        for scored in results:
            await self.touch(scored.record.memory_id, current_tick_id)
        return results

    async def _records(self, memory_ids: list[str]) -> list[MemoryRecord | None]:
        return [await self.get(memory_id) for memory_id in memory_ids]
