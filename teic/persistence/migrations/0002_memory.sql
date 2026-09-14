-- Relational memory tables. The `memory_vec` sqlite-vec virtual table is
-- created separately by teic/memory/vector_index.py once the sqlite-vec
-- extension is loaded (Phase 4) rather than here, so this migration has no
-- hard dependency on that extension being installed before Phase 4 work begins.

CREATE TABLE memory_record (
    memory_id            TEXT PRIMARY KEY,
    session_id           TEXT NOT NULL REFERENCES session(session_id),
    timescale            TEXT NOT NULL CHECK(timescale IN ('tau1_working','tau2_episodic','tau3_semantic','tau4_consolidated')),
    content              TEXT NOT NULL,
    content_kind         TEXT NOT NULL CHECK(content_kind IN ('episode','fact','commitment','autobiography_entry')),
    created_tick_id      INTEGER NOT NULL REFERENCES tick(tick_id),
    last_access_tick_id  INTEGER REFERENCES tick(tick_id),
    base_activation      REAL NOT NULL DEFAULT 1.0,
    decay_alpha          REAL NOT NULL,
    affect_valence       REAL NOT NULL,
    affect_arousal       REAL NOT NULL,
    access_count         INTEGER NOT NULL DEFAULT 0,
    embedding_ref        INTEGER,
    superseded_by        TEXT REFERENCES memory_record(memory_id)
);
CREATE INDEX idx_memory_timescale ON memory_record(session_id, timescale);

CREATE TABLE prospective_commitment (
    commitment_id    TEXT PRIMARY KEY,
    session_id       TEXT NOT NULL REFERENCES session(session_id),
    created_tick_id  INTEGER NOT NULL REFERENCES tick(tick_id),
    due_at           TEXT NOT NULL,
    description      TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','fulfilled','missed','cancelled')),
    resolved_tick_id INTEGER REFERENCES tick(tick_id)
);

CREATE TABLE consolidation_event (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id        TEXT NOT NULL REFERENCES session(session_id),
    tick_id           INTEGER NOT NULL REFERENCES tick(tick_id),
    source_memory_ids TEXT NOT NULL,
    result_memory_id  TEXT REFERENCES memory_record(memory_id),
    trigger           TEXT NOT NULL CHECK(trigger IN ('idle_sleep_analog','manual_forced'))
);
