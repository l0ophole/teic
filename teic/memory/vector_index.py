"""The `memory_vec` sqlite-vec virtual table.

`0002_memory.sql`'s header comment defers this table's creation to "Phase 4
work", since it needs the sqlite-vec extension loaded into the connection
first (not expressible in a plain `.sql` migration file that runs before
any Python has touched the connection). Created here instead, idempotently,
the first time a daemon session starts.
"""

from __future__ import annotations

import aiosqlite
import sqlite_vec

from teic.memory.embeddings import EMBEDDING_DIM


async def ensure_loaded(conn: aiosqlite.Connection) -> None:
    await conn.enable_load_extension(True)
    await conn.load_extension(sqlite_vec.loadable_path())
    await conn.enable_load_extension(False)


async def ensure_table(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        f"CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING "
        f"vec0(embedding_ref INTEGER PRIMARY KEY, "
        f"embedding float[{EMBEDDING_DIM}] distance_metric=cosine)"
    )
    await conn.commit()


async def upsert(conn: aiosqlite.Connection, embedding_ref: int, embedding: list[float]) -> None:
    await conn.execute(
        "INSERT OR REPLACE INTO memory_vec(embedding_ref, embedding) VALUES (?, ?)",
        (embedding_ref, sqlite_vec.serialize_float32(embedding)),
    )
    await conn.commit()


async def query_similar(
    conn: aiosqlite.Connection, query_embedding: list[float], k: int
) -> dict[int, float]:
    """Cosine-similarity kNN. Returns `{embedding_ref: similarity}` with
    similarity clamped to `[0, 1]` (sqlite-vec's cosine `distance` can
    exceed 1 for negative-similarity pairs; `retrieval.rank()` expects a
    non-negative `semantic_match`)."""
    cursor = await conn.execute(
        "SELECT embedding_ref, distance FROM memory_vec WHERE embedding MATCH ? AND k = ? ORDER BY distance",
        (sqlite_vec.serialize_float32(query_embedding), k),
    )
    rows = await cursor.fetchall()
    return {int(ref): max(1.0 - float(distance), 0.0) for ref, distance in rows}
