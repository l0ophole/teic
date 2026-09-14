"""Async SQLite connection management + a small hand-rolled migration runner.

No migrations framework (e.g. alembic) is used: a handful of numbered .sql
files applied in order, tracked in a `schema_migrations` table, is sufficient
for this project's schema churn and keeps the dependency list minimal.
"""

from __future__ import annotations

from pathlib import Path

import aiosqlite

MIGRATIONS_DIR = Path(__file__).resolve().parent / "migrations"


async def _ensure_migrations_table(conn: aiosqlite.Connection) -> None:
    await conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations (filename TEXT PRIMARY KEY, applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
    )
    await conn.commit()


async def _applied_migrations(conn: aiosqlite.Connection) -> set[str]:
    cursor = await conn.execute("SELECT filename FROM schema_migrations")
    rows = await cursor.fetchall()
    return {row[0] for row in rows}


def _split_statements(sql: str) -> list[str]:
    """Naive ';'-based statement splitter, sufficient for this project's
    migration files (no semicolons embedded in string literals or triggers)."""
    return [stmt.strip() for stmt in sql.split(";") if stmt.strip()]


async def run_migrations(conn: aiosqlite.Connection) -> list[str]:
    """Apply any .sql files in migrations/ not yet recorded as applied.

    Each migration is applied atomically: `sqlite3.Connection.executescript`
    implicitly commits any open transaction before running (even with
    isolation_level=None), so a single migration's statements are executed
    individually inside one explicit BEGIN/COMMIT here instead. That way a
    process killed mid-migration (e.g. SIGTERM) leaves the transaction
    uncommitted -- SQLite rolls it back on next open -- rather than leaving
    a half-applied schema with no record of having started.

    Returns the list of filenames applied this call (empty if already current).
    """
    await _ensure_migrations_table(conn)
    already_applied = await _applied_migrations(conn)
    applied_now: list[str] = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        if path.name in already_applied:
            continue
        statements = _split_statements(path.read_text())
        await conn.execute("BEGIN")
        try:
            for stmt in statements:
                await conn.execute(stmt)
            await conn.execute(
                "INSERT INTO schema_migrations (filename) VALUES (?)", (path.name,)
            )
        except Exception:
            await conn.rollback()
            raise
        else:
            await conn.commit()
        applied_now.append(path.name)
    return applied_now


async def open_db(db_path: str | Path) -> aiosqlite.Connection:
    """Open (creating parent dirs as needed) a WAL-mode connection with
    foreign keys enabled, and apply any pending migrations."""
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = await aiosqlite.connect(path, isolation_level=None)
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA foreign_keys=ON")
    await run_migrations(conn)
    return conn
