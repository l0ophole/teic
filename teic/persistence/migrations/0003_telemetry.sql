-- log_event IS the structured JSON-lines log requirement: each row is one
-- JSON-serialized LogEvent. `teic export-logs` dumps rows as newline-delimited
-- JSON on demand -- single source of truth, no dual-write inconsistency
-- between a live JSONL file and SQLite.
CREATE TABLE log_event (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES session(session_id),
    tick_id    INTEGER REFERENCES tick(tick_id),
    ts         TEXT NOT NULL,
    level      TEXT NOT NULL CHECK(level IN ('DEBUG','INFO','WARN','ERROR')),
    subsystem  TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL
);
CREATE INDEX idx_log_event_session_ts ON log_event(session_id, ts);
CREATE INDEX idx_log_event_subsystem ON log_event(session_id, subsystem);
CREATE INDEX idx_log_event_type ON log_event(session_id, event_type);

CREATE TABLE workspace_broadcast (
    broadcast_id   TEXT PRIMARY KEY,
    tick_id        INTEGER NOT NULL REFERENCES tick(tick_id),
    winner_source  TEXT NOT NULL,
    salience_score REAL NOT NULL,
    novelty        REAL NOT NULL,
    precision_w    REAL NOT NULL,
    affective_w    REAL NOT NULL,
    goal_relevance REAL NOT NULL,
    ignited        INTEGER NOT NULL,
    content        TEXT NOT NULL,
    mineness_tag   TEXT NOT NULL CHECK(mineness_tag IN ('self','other','ambiguous'))
);

CREATE TABLE llm_call_log (
    call_id            TEXT PRIMARY KEY,
    tick_id            INTEGER REFERENCES tick(tick_id),
    model              TEXT NOT NULL,
    fallback_used      INTEGER NOT NULL DEFAULT 0,
    prompt             TEXT NOT NULL,
    response           TEXT,
    prompt_tokens      INTEGER,
    completion_tokens  INTEGER,
    estimated_cost_usd REAL,
    latency_ms         INTEGER,
    status             TEXT NOT NULL CHECK(status IN ('ok','timeout','error','retried')),
    error_detail       TEXT,
    started_at         TEXT NOT NULL,
    finished_at        TEXT
);

CREATE TABLE viability_ledger (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id         TEXT NOT NULL REFERENCES session(session_id),
    tick_id            INTEGER NOT NULL REFERENCES tick(tick_id),
    budget_reserve_usd REAL NOT NULL,
    delta_usd          REAL NOT NULL,
    reason             TEXT NOT NULL CHECK(reason IN ('llm_call','replenishment','low_power_halt')),
    ts                 TEXT NOT NULL
);
