CREATE TABLE session (
    session_id       TEXT PRIMARY KEY,
    started_at       TEXT NOT NULL,
    ended_at         TEXT,
    config_snapshot  TEXT NOT NULL,
    ablation_profile TEXT NOT NULL DEFAULT 'full'
);

CREATE TABLE tick (
    tick_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id    TEXT NOT NULL REFERENCES session(session_id),
    tick_index    INTEGER NOT NULL,
    wall_ts       TEXT NOT NULL,
    dt_real       REAL NOT NULL,
    dt_subjective REAL NOT NULL,
    tempo_hz      REAL NOT NULL,
    UNIQUE(session_id, tick_index)
);

CREATE TABLE register_sample (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_id        INTEGER NOT NULL REFERENCES tick(tick_id),
    channel        TEXT NOT NULL,
    raw_value      REAL,
    inferred_value REAL NOT NULL,
    inferred_var   REAL NOT NULL,
    ts             TEXT NOT NULL
);
CREATE INDEX idx_register_sample_tick ON register_sample(tick_id);
CREATE INDEX idx_register_sample_channel_ts ON register_sample(channel, ts);

CREATE TABLE affect_sample (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_id         INTEGER NOT NULL REFERENCES tick(tick_id),
    valence         REAL NOT NULL,
    arousal         REAL NOT NULL,
    mood            REAL NOT NULL,
    attractor_label TEXT,
    ts              TEXT NOT NULL
);
CREATE INDEX idx_affect_sample_tick ON affect_sample(tick_id);
