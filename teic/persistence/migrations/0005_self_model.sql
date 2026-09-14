CREATE TABLE self_model (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id             TEXT NOT NULL REFERENCES session(session_id),
    tick_id                INTEGER NOT NULL REFERENCES tick(tick_id),
    version                INTEGER NOT NULL,
    body                   TEXT NOT NULL,
    agency                 REAL NOT NULL,
    interoception_summary  TEXT NOT NULL,
    history_summary        TEXT NOT NULL,
    identity_traits        TEXT NOT NULL,
    mental_state_estimate  TEXT NOT NULL,
    temporal_self          TEXT NOT NULL,
    confidence             REAL NOT NULL,
    ts                     TEXT NOT NULL
);
