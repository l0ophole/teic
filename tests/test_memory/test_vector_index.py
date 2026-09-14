from __future__ import annotations

from pathlib import Path

import aiosqlite
import pytest

from teic.memory import vector_index


async def test_query_similar_returns_closest_vector_first(tmp_path: Path) -> None:
    conn = await aiosqlite.connect(tmp_path / "vec_test.db")
    try:
        await vector_index.ensure_loaded(conn)
        await vector_index.ensure_table(conn)

        dim = [1.0, 0.0, 0.0, 0.0] + [0.0] * 380
        other_a = [0.0, 1.0, 0.0, 0.0] + [0.0] * 380
        other_b = [0.0, 0.0, 1.0, 0.0] + [0.0] * 380

        await vector_index.upsert(conn, 1, dim)
        await vector_index.upsert(conn, 2, other_a)
        await vector_index.upsert(conn, 3, other_b)

        results = await vector_index.query_similar(conn, dim, k=3)
        assert results[1] == pytest.approx(1.0, abs=1e-6)
        assert results[1] > results[2]
        assert results[1] > results[3]
    finally:
        await conn.close()
