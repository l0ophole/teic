# Phase 4 Plan — Memory timescales, power-law decay, consolidation

## Context

Sub-plan for **Phase 4** of `PLAN.md`'s Build Order table: "Memory
timescales, power-law decay, consolidation, sqlite-vec + sentence-transformers
embeddings" / gate: "Retrieval ranking shifts with affect; activation decay
fits power-law, not exponential." This implements `PLAN.md`'s own
**Power-law retrieval** section verbatim:
`activation(m,t) = base_activation * (1 + (t - last_access)/c)^(-alpha)`,
`score = activation * semantic_match * affective_tag_weight(current_affect)`,
retrieval resets the decay clock on read (reinforcement) without touching
`base_activation`. It also lands the `0002_memory.sql` tables
(`memory_record`, `prospective_commitment` -- out of scope, see below --,
`consolidation_event`) and the `memory_vec` sqlite-vec virtual table that
migration's own header comment explicitly deferred to "Phase 4" work.

Phase 3 (`4405ca9`) is complete; the user has given the go-ahead ("Continue
to Phase 4").

**Scope ruling 1 -- memory content this phase, stated explicitly (same
posture as Phase 3's "no real effector yet"):** there is no workspace
arbiter (Phase 5) or real LLM cognition loop yet, so there is no
`WorkspaceBroadcast` content to turn into an episodic memory. The only
genuinely-observable, non-hallucinated content this early is the daemon's
own per-tick interoceptive state. `_on_tick` therefore writes one
`tau1_working`/`episode` memory record per tick, `content` = a compact,
deterministic text serialization of that tick's `RegisterState` +
`AffectState` (e.g. `"tick 42: valence=-0.12 arousal=0.34 prediction_error=1.8 ..."`).
This is real, non-fabricated data -- not a placeholder string -- and gives
the decay/retrieval/consolidation machinery real rows to operate on. It is
explicitly **not** "the agent remembering a conversation"; that lands once
Phase 5's arbiter produces real broadcast content worth remembering. Every
module built this phase (`decay.py`, `retrieval.py`, `store.py`,
`vector_index.py`, `consolidation.py`) is written against the real
`MemoryRecord` model with no knowledge of *where* its content came from, so
nothing here needs revisiting when Phase 5 starts writing richer content
through the same `MemoryStore.create()` call.

**Scope ruling 2 -- consolidation content, stated explicitly:** `PLAN.md`'s
concurrency model names a `consolidation_task` (idle-gated tau4 background
job) but there is no LLM-backed summarization loop yet either (same
constraint as ruling 1). Phase 4's consolidation is therefore **structural,
not semantic**: given a cluster of low-activation `tau1_working`/
`tau2_episodic` records, `consolidate_group()` produces one
`tau4_consolidated` record whose content is a deterministic join of the
source contents (not an LLM summary), and marks each source's
`superseded_by` to point at it. Real LLM-backed summarization is Phase 5+
work (once `llm/client.py` is actually called from the tick loop) and will
slot into the same `consolidate_group()` seam without changing its callers.

**Scope ruling 3 -- `prospective_commitment` table, stated explicitly:**
`0002_memory.sql` also created `prospective_commitment` (Layer 0's
prospective memory). `PLAN.md`'s Build Order table does not name prospective
memory under Phase 4 -- it belongs with Layer 0's retention
buffer/specious-present work, which is *also* not yet built (Phase 3's plan
scoped those out explicitly too). This phase does not touch
`prospective_commitment` at all; it stays an unused table until whichever
phase actually needs it.

**Scope ruling 4 -- idle-gating, resolved per `PLAN.md`'s own open question
#7** ("Idle definition for consolidation -- must be wall-clock-based, not
tick-count-based, so low-tempo periods don't starve tau4 consolidation
disproportionately"): the `consolidation_task` measures idle time via
`time.monotonic()` deltas against the wall-clock timestamp of the daemon's
last `_on_tick` call, not a tick counter -- so idle-tempo (0.2Hz) sessions
still consolidate on a real-time schedule instead of waiting 25x longer in
tick-count terms than a busy (10Hz) session would.

**Embedding model device pin, verified in this environment and therefore a
binding constraint, not a style preference:** `SentenceTransformer(...)`
must be constructed with `device="cpu"` explicitly. Verified by hand: with
no `device` argument, `.encode()` on this machine raises
`torch.AcceleratorError: CUDA error: no kernel image is available for
execution on the device` (a real, reproduced GPU/driver mismatch, not a
hypothetical) -- the model itself downloads and runs fine once pinned to
CPU. `all-MiniLM-L6-v2` (384-dim, the standard small `sentence-transformers`
default) is the model; embedding load is ~1s once cached in
`~/.cache/huggingface` after first download.

## Global Constraints (binding on all tasks)

- No hand-authored magic thresholds without a named module-level constant --
  same convention as `inference.py`/`forward_model.py`/`modulation.py`.
- `decay.py`/`retrieval.py`/`consolidation.py`'s pure-computation functions
  must not touch the DB or read `Settings` directly -- same "pure
  computation, daemon/store does I/O" posture Phase 3 established for
  `ForwardModel`/`ProtentionBuffer`. `store.py`/`vector_index.py` are the
  only new modules allowed to do I/O.
- Time in `decay.py`'s formula is **tick-id based**
  (`t - last_access` = `current_tick_id - last_access_tick_id`), matching
  how `created_tick_id`/`last_access_tick_id` are already typed as `int` on
  `MemoryRecord` (not timestamps) -- consistent with the rest of the
  codebase's tick-indexed temporal bookkeeping.
- `ModulationParams.retrieval_k`/`retrieval_affect_weight` (Phase 2,
  `teic/interoception/modulation.py:32-33`) were computed from real inputs
  with "no consumer yet" recorded explicitly in `ARCHITECTURE.md`'s Phase 2
  section. This phase is that consumer: `retrieval.py`'s ranking function
  takes `retrieval_k`/`retrieval_affect_weight` as parameters and actually
  uses them. Say so in the module docstring, mirroring how Phase 3's
  `predicted_registers` naming pattern works.
- `mypy` (project-wide, per `pyproject.toml`'s `[tool.mypy] files` list --
  add `teic/memory` to that list as part of Task 1) must keep passing.
- Full `pytest -q` must pass, including every prior phase's gate test
  unmodified in behavior.
- `BUILD_STATUS.md`/`ARCHITECTURE.md` updates are part of "done" for the
  task that lands daemon wiring, not a follow-up.
- Do **not** implement the workspace arbiter, ignition, retention
  buffer/specious present/prospective memory, viability/allostasis, or any
  real LLM-backed consolidation summary -- those are later phases (3's
  unfinished Layer-0 pieces, 5, 6 as applicable).
- Phase 4 is **not** a named hard-stop in `PLAN.md` (only Phase 2 was) --
  report completion and wait rather than silently starting Phase 5 in the
  same turn.

---

## Task 1: `memory/decay.py` + `memory/retrieval.py` (pure, no I/O)

**Files to create:**

1. `teic/memory/decay.py`
   - Module constant: `DECAY_C = 20.0` (the formula's `c` -- ticks until
     activation has decayed to `2^(-alpha)` of its base value; 20 ticks is
     chosen so the effect is visible within a gate test's ~40-60 tick
     scenarios, matching the tick-count scale Phase 1-3's gate tests
     already use).
   - `def activation(record: MemoryRecord, current_tick_id: int) -> float`:
     implements `PLAN.md`'s formula verbatim:
     ```python
     def activation(record: MemoryRecord, current_tick_id: int) -> float:
         last_access = record.last_access_tick_id
         if last_access is None:
             last_access = record.created_tick_id
         elapsed = max(current_tick_id - last_access, 0)
         return record.base_activation * (1.0 + elapsed / DECAY_C) ** (-record.decay_alpha)
     ```
     Docstring states explicitly: this is a **power-law** (polynomial in
     `elapsed`), not `exp(-elapsed/tau)` -- the reason it has a heavier tail
     (slower long-run decay) than an exponential with a matched initial
     slope, which is exactly what the gate test proves quantitatively.
   - `def touch(record: MemoryRecord, tick_id: int) -> MemoryRecord`: returns
     a copy (`record.model_copy(update=...)`) with `last_access_tick_id=tick_id`
     and `access_count=record.access_count + 1` -- **does not** change
     `base_activation`, per `PLAN.md`'s "resets the decay clock on read
     (reinforcement) without touching `base_activation`" line. Pure function
     (no DB write); `store.py`'s `MemoryStore.touch()` in Task 2 is the
     thing that persists this.

2. `teic/memory/retrieval.py`
   - Module constant: `AFFECT_MATCH_SCALE = 0.5` (bounds how much affect
     congruence can move a score -- see below).
   - `def affective_tag_weight(record: MemoryRecord, current_valence: float, current_arousal: float, retrieval_affect_weight: float) -> float`:
     ```python
     def affective_tag_weight(
         record: MemoryRecord,
         current_valence: float,
         current_arousal: float,
         retrieval_affect_weight: float,
     ) -> float:
         valence_gap = abs(record.affect_valence - current_valence) / 2.0
         arousal_gap = abs(record.affect_arousal - current_arousal) / 2.0
         congruence = 1.0 - min((valence_gap + arousal_gap) / 2.0, 1.0)
         return 1.0 + AFFECT_MATCH_SCALE * retrieval_affect_weight * congruence
     ```
     (`retrieval_affect_weight` is `ModulationParams.retrieval_affect_weight`,
     already `_clamp(affect.valence, -1.0, 1.0)` from Phase 2 -- positive
     valence biases toward mood-congruent memories, negative valence biases
     *away* from them, exactly the "mood-congruent bias" `PLAN.md` names.)
     `congruence` in `[0, 1]`, so weight is always `> 0` for any
     `retrieval_affect_weight` in `[-1, 1]` and `AFFECT_MATCH_SCALE=0.5` --
     it can never zero out or invert a semantic match, only bias its rank
     among near-ties.
   - `@dataclass(frozen=True) class ScoredMemory`: `record: MemoryRecord`,
     `score: float`, `semantic_match: float`, `activation_value: float`.
   - `def rank(records: list[MemoryRecord], semantic_matches: dict[str, float], current_tick_id: int, current_valence: float, current_arousal: float, retrieval_affect_weight: float, retrieval_k: int) -> list[ScoredMemory]`:
     computes `score = activation(record, current_tick_id) * semantic_matches[record.memory_id] * affective_tag_weight(...)`
     for every record present in `semantic_matches`, sorts descending by
     `score`, returns the top `retrieval_k`. `semantic_matches` is supplied
     by the caller (Task 2's `vector_index.query_similar`) rather than
     computed here, keeping this module DB-free per the global constraint.

**Tests to add:**

- `tests/test_memory/test_decay.py`:
  - `activation()` at `elapsed=0` (current_tick_id == last_access)
    equals `base_activation` exactly.
  - `activation()` is strictly decreasing in `elapsed` for `decay_alpha > 0`.
  - **Power-law-not-exponential assertion (the literal gate wording)**:
    build two curves over `elapsed in [0, 200, 400, ..., 2000]` (needs a
    long tail to be discriminating) for the same `base_activation=1.0`,
    `decay_alpha` picked so the two curves start with the same
    activation at `elapsed=0` and the same value at `elapsed=DECAY_C`
    (i.e. matched "half-life"-style point) -- one from `activation()`,
    one from a locally-defined `exp_decay(elapsed) = base * exp(-elapsed * k)`
    with `k` solved so the two agree at `elapsed=DECAY_C`. Assert the
    power-law curve's value at the largest `elapsed` is **at least 3x**
    the exponential curve's value there -- the quantitative signature of a
    heavier tail. (Compute `k` directly:
    `k = -math.log(activation(..., DECAY_C) / base_activation) / DECAY_C`.)
  - `touch()` updates `last_access_tick_id`/`access_count` and leaves
    `base_activation` byte-identical (`==`, not approximately).
- `tests/test_memory/test_retrieval.py`:
  - `affective_tag_weight()` is larger for a memory whose
    `(affect_valence, affect_arousal)` matches `(current_valence,
    current_arousal)` exactly than for one far from it, when
    `retrieval_affect_weight > 0`; the ordering **flips** when
    `retrieval_affect_weight < 0` (mood-*in*congruent memories score
    higher) -- proving the sign, not just the magnitude, matters.
  - **Ranking-shifts-with-affect assertion (the other half of the literal
    gate wording)**: construct two `MemoryRecord`s with identical
    `base_activation`/`decay_alpha`/timestamps and identical
    `semantic_matches` (so `activation()` and `semantic_match` alone would
    tie them), but different `(affect_valence, affect_arousal)` -- one
    near `(current_valence, current_arousal)`, one far. Call `rank()` twice
    with the same records/semantic_matches but opposite-signed
    `retrieval_affect_weight`, and assert the **first-place record swaps**
    between the two calls. This is a same-inputs-except-affect,
    different-output test, the retrieval analogue of Phase 2's gate test
    pattern (byte-identical text, divergent params).
  - `rank()` respects `retrieval_k` (returns at most `k` results) and only
    ranks records present in `semantic_matches` (a record missing from the
    dict is silently excluded, not an error -- this is how Task 2's
    caller will pass a pre-filtered kNN result set).

**Verification:** `pytest tests/test_memory -q` and `mypy teic/memory`.

---

## Task 2: `memory/embeddings.py` + `memory/vector_index.py` + `memory/store.py`

Depends on Task 1.

**Files to create:**

1. `teic/memory/embeddings.py`
   - Module constant: `MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"`,
     `EMBEDDING_DIM = 384`.
   - `class EmbeddingModel`: wraps one lazily-constructed
     `sentence_transformers.SentenceTransformer(MODEL_NAME, device="cpu")`
     instance (constructed on first `.encode()` call, not at import time --
     importing `teic.memory.embeddings` must not touch disk/network so unit
     tests that don't need real embeddings stay fast). Docstring states the
     `device="cpu"` pin verbatim as a verified constraint (CUDA error
     reproduced on this machine without it -- see plan's scope-ruling
     section), not a style choice.
     - `def encode(self, text: str) -> list[float]`: returns
       `self._model.encode(text).tolist()`.
   - Module-level `_default_model: EmbeddingModel | None = None` +
     `def get_default_model() -> EmbeddingModel` (lazy singleton, same
     "constructed once per session" posture as `SensorArray`) -- avoids
     reloading the ~90MB model per call site.

2. `teic/memory/vector_index.py`
   - `async def ensure_loaded(conn: aiosqlite.Connection) -> None`: 
     `await conn.enable_load_extension(True)`; `await
     conn.load_extension(sqlite_vec.loadable_path())`; `await
     conn.enable_load_extension(False)` -- verified working against
     `aiosqlite.Connection` by hand (see plan context; `enable_load_extension`/
     `load_extension` are real awaitable methods on it, not sqlite3-only).
   - `async def ensure_table(conn: aiosqlite.Connection) -> None`:
     `CREATE VIRTUAL TABLE IF NOT EXISTS memory_vec USING
     vec0(embedding_ref INTEGER PRIMARY KEY, embedding float[384]
     distance_metric=cosine)` -- `distance_metric=cosine` verified to exist
     in the installed `sqlite-vec` version (`v0.1.9`) by hand. This is the
     virtual table `0002_memory.sql`'s header comment named as Phase 4's
     job, created here (not in a `.sql` migration file) exactly as that
     comment says, because it needs the extension loaded first.
   - `async def upsert(conn: aiosqlite.Connection, embedding_ref: int, embedding: list[float]) -> None`:
     `INSERT OR REPLACE INTO memory_vec(embedding_ref, embedding) VALUES
     (?, ?)` with `sqlite_vec.serialize_float32(embedding)`.
   - `async def query_similar(conn: aiosqlite.Connection, query_embedding: list[float], k: int) -> dict[int, float]`:
     runs `SELECT embedding_ref, distance FROM memory_vec WHERE embedding
     MATCH ? AND k = ? ORDER BY distance` (verified query shape by hand),
     returns `{embedding_ref: max(1.0 - distance, 0.0) for ...}` -- cosine
     distance to a `[0, 1]`-clamped similarity, the `semantic_match` value
     `retrieval.py`'s `rank()` expects.

3. `teic/memory/store.py`
   - `class MemoryStore`: constructed with an `aiosqlite.Connection` and an
     `EmbeddingModel` (injected, not the module singleton directly, so
     tests can pass a fake that skips the real model -- same DI posture as
     `Heartbeat`'s `time_source`).
     - `async def create(self, *, session_id: str, timescale: Timescale, content: str, content_kind: ContentKind, created_tick_id: int, base_activation: float, decay_alpha: float, affect_valence: float, affect_arousal: float) -> MemoryRecord`:
       generates `memory_id = str(uuid.uuid4())`, computes
       `embedding = self._embed.encode(content)`, inserts into
       `memory_record` (using `embedding_ref` = a small monotonic integer
       counter column reused as the `memory_vec` primary key -- simplest
       correct mapping: use `rowid` of the just-inserted row, read back via
       `cursor.lastrowid`), calls `vector_index.upsert(...)`, returns the
       constructed `MemoryRecord` (with `.embedding` populated).
     - `async def get(self, memory_id: str) -> MemoryRecord | None`.
     - `async def list_by_timescale(self, session_id: str, timescale: Timescale) -> list[MemoryRecord]`.
     - `async def touch(self, memory_id: str, tick_id: int) -> None`: reads
       the record, applies `decay.touch()`, writes back only
       `last_access_tick_id`/`access_count` (an `UPDATE`, not a full
       re-insert) -- the DB-side half of Task 1's pure `touch()`.
     - `async def query(self, session_id: str, query_text: str, current_tick_id: int, current_valence: float, current_arousal: float, retrieval_affect_weight: float, retrieval_k: int) -> list[ScoredMemory]`:
       encodes `query_text`, calls `vector_index.query_similar`, loads the
       matching `MemoryRecord`s via `get()`, calls `retrieval.rank(...)`,
       and -- per "retrieval resets the decay clock on read" -- calls
       `self.touch(...)` on every record in the returned top-`k` before
       returning. This is the one method that composes Task 1's pure
       functions with real I/O; it's the thing Phase 5's arbiter will
       eventually call for real (no consumer yet this phase, named
       explicitly here the same way `predicted_registers` was named in
       Phase 3).

**Tests to add:**

- `tests/test_memory/test_vector_index.py` (uses a real temp-file
  `aiosqlite` connection + real `sqlite-vec` extension -- no mocking; this
  is integration-level by nature): `ensure_loaded` + `ensure_table` then
  `upsert` three vectors and `query_similar` against a vector identical to
  one of them returns that one first with similarity `~1.0`.
- `tests/test_memory/test_store.py`: uses a real temp-file DB (migrations
  applied via `teic.persistence.db.open_db`) and a **fake** `EmbeddingModel`
  (a test double whose `.encode()` returns a deterministic hash-based
  fixed-length vector, so this test doesn't need the real ~90MB model or
  network access) satisfying the same `encode(text) -> list[float]`
  interface:
  - `create()` persists a row readable back via `get()`, with a populated
    `embedding`.
  - `touch()` updates `last_access_tick_id`/`access_count` in the DB
    without changing `base_activation`.
  - `query()` returns results ranked as `retrieval.rank()` would, and
    leaves `access_count` incremented on the returned records (reinforcement
    on read).

**Verification:** `pytest tests/test_memory -q` and `mypy teic/memory`. Note
in the report whether `test_vector_index.py`/`test_store.py`'s real-model
variant (if any) needed network access this run (it should not, given the
fake-embedder design above, but `sqlite-vec`'s extension load is real and
local so no network is needed for those either).

---

## Task 3: `memory/consolidation.py` + daemon wiring

Depends on Task 2.

**Files to create/modify:**

1. `teic/memory/consolidation.py`
   - Module constants: `CONSOLIDATION_ACTIVATION_FLOOR = 0.15` (records
     below this `activation()` value are consolidation candidates),
     `CONSOLIDATION_MIN_GROUP_SIZE = 3` (don't consolidate a single
     leftover record), `IDLE_THRESHOLD_S = 30.0` (wall-clock seconds of no
     `_on_tick` activity before the daemon's background task fires --
     small enough to actually trigger in a short manual smoke test, per
     `PLAN.md`'s wall-clock idle-gating resolution above).
   - `def find_consolidation_candidates(records: list[MemoryRecord], current_tick_id: int) -> list[MemoryRecord]`:
     pure function -- filters to `timescale in
     ("tau1_working","tau2_episodic")` and `superseded_by is None` and
     `decay.activation(r, current_tick_id) < CONSOLIDATION_ACTIVATION_FLOOR`,
     returns `[]` if fewer than `CONSOLIDATION_MIN_GROUP_SIZE` match (no
     group to consolidate).
   - `def consolidate_group(records: list[MemoryRecord], result_tick_id: int) -> MemoryRecord`:
     pure function. Builds the merged record: `content = " | ".join(sorted(r.content for r in records))`
     (deterministic join -- explicitly **not** an LLM summary, per this
     plan's scope ruling 2, stated again in this function's docstring),
     `timescale="tau4_consolidated"`, `content_kind="autobiography_entry"`,
     `base_activation = max(r.base_activation for r in records)` (the
     consolidated memory starts at least as strong as its strongest
     source), `decay_alpha` = the **mean** of source `decay_alpha`s
     (tau4 should decay slower on average as more/stronger sources feed
     in -- documented as this phase's chosen heuristic, not derived from a
     spec formula, since `PLAN.md` doesn't specify one), `affect_valence`/
     `affect_arousal` = mean of sources', `created_tick_id=result_tick_id`.
     Does **not** set `memory_id` (caller/`store.py` assigns it on
     persist) or touch the DB.
   - `async def run_consolidation_pass(store: MemoryStore, session_id: str, current_tick_id: int) -> ConsolidationEvent | None`:
     loads `tau1_working` + `tau2_episodic` records for the session via
     `store.list_by_timescale` (both calls), finds candidates, if any
     returns `None`; else calls `consolidate_group`, persists it via
     `store.create(...)`, marks every source's `superseded_by` via a new
     small `store.mark_superseded(memory_id, superseded_by) -> None`
     helper (add this one-line method to `MemoryStore` in this task, not
     Task 2, since it's consolidation-only), inserts a `consolidation_event`
     row (`trigger="idle_sleep_analog"`), and returns the `ConsolidationEvent`.

2. `teic/daemon.py`:
   - `__init__`: add `self._memory_store: MemoryStore | None = None`,
     `self._last_tick_wall_ts: float | None = None` (via `time.monotonic()`,
     for wall-clock idle gating), `self._consolidation_task:
     asyncio.Task[None] | None = None`.
   - `start()`: after existing setup, `await
     vector_index.ensure_loaded(self._conn)`, `await
     vector_index.ensure_table(self._conn)`, construct
     `self._memory_store = MemoryStore(self._conn,
     embeddings.get_default_model())`.
   - `_on_tick`: after the existing `affect_sample` insert/commit block
     (before the Phase 3 protention-push tail), add: build the tau1_working
     content string from this tick's `register_state`/`affect_state`
     (`f"tick {tick_id}: valence={affect_state.valence:.3f}
     arousal={affect_state.arousal:.3f} " + " ".join(f"{ch}={v:.3f}" for
     ch, v in register_values.items())`), call `await
     self._memory_store.create(session_id=self._session_id,
     timescale="tau1_working", content=..., content_kind="episode",
     created_tick_id=tick_id, base_activation=1.0, decay_alpha=0.5,
     affect_valence=affect_state.valence, affect_arousal=affect_state.arousal)`,
     and set `self._last_tick_wall_ts = time.monotonic()`.
   - `run()`/`run_n_ticks()`: wrap the existing heartbeat run in an
     `asyncio.TaskGroup` alongside a new `self._consolidation_loop()`
     coroutine (matches `PLAN.md`'s "single `asyncio.TaskGroup`" concurrency
     model) -- `_consolidation_loop` is `while True: await
     asyncio.sleep(5.0); if self._last_tick_wall_ts is not None and
     time.monotonic() - self._last_tick_wall_ts >= IDLE_THRESHOLD_S: await
     run_consolidation_pass(self._memory_store, self._session_id,
     <latest known tick_id>); ` -- guarded so it exits cleanly on
     `shutdown_event`/cancellation the same way `Heartbeat.stop()` already
     is respected. **`run_n_ticks()` (used by every prior gate test) must
     not hang waiting on this loop** -- structure it so `run_n_ticks`
     cancels the consolidation task after the heartbeat's `n` ticks
     complete, same pattern as how `stop()` already cancels the heartbeat.
   - Update the module docstring's phase-log comment block with a "Phase
     4:" paragraph: real per-tick `tau1_working` memory writes (the honest
     proxy-content scope ruling, stated in substance), wall-clock idle-gated
     structural (non-LLM) consolidation, and that real cognition-sourced
     memory content is Phase 5+.

**Tests to add:**

- `tests/test_memory/test_consolidation.py`:
  - `find_consolidation_candidates` excludes `tau3_semantic`/
    `tau4_consolidated` records and already-`superseded_by` records, and
    returns `[]` under `CONSOLIDATION_MIN_GROUP_SIZE`.
  - `consolidate_group` on 3 synthetic low-activation records produces one
    record whose `content` contains all three sources' content, and whose
    `base_activation`/`decay_alpha`/affect fields match the documented
    aggregation rules above exactly.
  - `run_consolidation_pass` (using the same fake-embedder `MemoryStore`
    test setup as `test_store.py`) against a seeded DB with enough
    low-activation records: returns a non-`None` `ConsolidationEvent`,
    the new `tau4_consolidated` record exists via `store.get()`, and every
    source record's `superseded_by` now points at it.
- `tests/test_daemon.py` (extend): a short synthetic run asserts
  `memory_record` rows accumulate (one `tau1_working` row per tick) and
  that `run_n_ticks()` returns promptly (doesn't hang on the
  consolidation loop) -- bounding the test's own wall-clock runtime (e.g.
  assert it completes in well under `IDLE_THRESHOLD_S`).

**Verification:** `pytest tests/test_memory tests/test_daemon -q` and
`mypy teic/memory teic/daemon.py`.

---

## Task 4: Phase 4 gate test, docs

Depends on Task 3.

1. `tests/test_gates/test_phase4.py`:
   - **Power-law-not-exponential** half of the gate: reuse (import, don't
     duplicate) Task 1's `test_decay.py` heavier-tail assertion at the gate
     level -- construct the same matched-half-life comparison and assert
     the power-law/exponential ratio at the largest `elapsed`, with a
     short comment pointing at `PLAN.md`'s literal gate wording.
   - **Retrieval-ranking-shifts-with-affect** half: drive a real
     `MemoryStore` (fake embedder, real temp-file DB) seeded with two
     memories as in Task 1's ranking-swap unit test, but this time through
     the full `store.query()` path (real `vector_index` kNN, not
     hand-passed `semantic_matches`), calling `query()` twice with opposite
     `retrieval_affect_weight` and asserting the top result swaps -- the
     same assertion as Task 1's unit test but exercised end-to-end through
     real SQL/sqlite-vec, which is what makes it a gate test rather than a
     restatement of the unit test.
   - Assert, for contrast (mirroring Phase 3's gate test's contrast
     pattern): with `retrieval_affect_weight=0.0`, the two memories rank
     by `semantic_match`/`activation` alone and the ranking is stable
     across repeated calls -- proving affect is what's moving the ranking
     in the assertion above, not noise.
2. `BUILD_STATUS.md`: mark Phase 4 "**Complete**" (update the status table
   row currently "Not started"), add a "## Phase 4 — complete" section in
   the existing phases' style (bullet list referencing this plan's four
   scope rulings verbatim in substance), plus a "How to verify this phase
   yourself" block matching Phase 0-3's format.
3. `ARCHITECTURE.md`: append "### Phase 4 — Memory timescales, power-law
   decay, consolidation (complete)" to the Phase log, stating: the
   honest-proxy-content scope ruling (tau1_working writes from real
   register/affect state, not real cognition -- that's Phase 5+); that
   `retrieval_k`/`retrieval_affect_weight` (computed with "no consumer yet"
   since Phase 2) are now consumed by `MemoryStore.query()`; that
   consolidation this phase is structural (deterministic content join), not
   LLM-summarized, and why; the wall-clock (not tick-count) idle-gating
   resolution per `PLAN.md`'s open question #7; and that
   `prospective_commitment` remains untouched, deferred to whichever phase
   builds retention buffer/specious present/prospective memory.
4. Also commit `docs/plans/phase3-plan.md` (currently untracked in this
   repo despite Phase 3 being complete and referencing it in commit
   messages -- an oversight from that session, noted here so it isn't
   repeated: **commit this plan file itself, `phase4-plan.md`, alongside
   Task 1's commit**, not deferred to this final task).

**Verification:** full `pytest -q` and project-wide `mypy` before reporting
done; include exact commands and output in the report. Phase 4 is not a
named hard-stop in `PLAN.md`, but still report completion and wait rather
than starting Phase 5 unannounced in the same turn.
