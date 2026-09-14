CREATE TABLE probe_run (
    run_id          TEXT PRIMARY KEY,
    session_id      TEXT NOT NULL REFERENCES session(session_id),
    probe_name      TEXT NOT NULL,
    seed            INTEGER NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    verdict         TEXT CHECK(verdict IN ('pass','fail','inconclusive')),
    thresholds_used TEXT NOT NULL,
    result_payload  TEXT NOT NULL
);

CREATE TABLE ablation_variant_run (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id       TEXT NOT NULL REFERENCES probe_run(run_id),
    variant_name TEXT NOT NULL,
    session_id   TEXT NOT NULL REFERENCES session(session_id)
);
