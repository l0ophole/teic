## Phase 4 — complete

- [x] `teic/memory/decay.py`: `activation()` implements `PLAN.md`'s
      power-law formula verbatim (`base_activation * (1 + elapsed/DECAY_C)
      ** (-decay_alpha)`, tick-id-based elapsed) -- verified quantitatively
      against a matched exponential to have a heavier tail, not just
      "decreasing." `touch()` resets the decay clock on read without
      touching `base_activation`, per `PLAN.md`'s "lossy by design"
      requirement even for reinforced memories.
- [x] `teic/memory/retrieval.py`: `rank()` implements `score = activation *
      semantic_match * affective_tag_weight(current_affect)`. **This is the
      consumer Phase 2's `retrieval_k`/`retrieval_affect_weight`
      (`ModulationParams`) were computed for with "no consumer yet"** --
      they now actually bias ranking toward (positive valence) or away
      from (negative valence) mood-congruent memories.
- [x] `teic/memory/embeddings.py`: `EmbeddingModel` wraps
      `sentence-transformers/all-MiniLM-L6-v2`, pinned to `device="cpu"` --
      a **verified** constraint (reproduced `torch.AcceleratorError`
      without the pin on this machine), not a style choice. Lazy
      construction so importing the module stays offline-safe.
- [x] `teic/memory/vector_index.py`: creates the `memory_vec` sqlite-vec
      virtual table `0002_memory.sql`'s header comment deferred to this
      phase (needs the extension loaded into the connection first), with
      `distance_metric=cosine`.
- [x] `teic/memory/store.py`: `MemoryStore` composes the above with real
      SQL -- `create()` persists a record + embedding, `query()` runs a
      real kNN then re-ranks via `retrieval.rank()`, reinforcing
      (`touch()`-ing) every returned result.
- [x] `teic/memory/consolidation.py`: **structural, not LLM-summarized**
      consolidation (no cognition loop exists yet -- see scope ruling 2 in
      `docs/plans/phase4-plan.md`) -- `consolidate_group()` deterministically
      joins low-activation records' content into one `tau4_consolidated`
      record and marks sources `superseded_by` it. Idle-gating is
      **wall-clock**, per `PLAN.md`'s own open question #7, not tick-count.
- [x] `teic/daemon.py`: `_on_tick` writes one real `tau1_working` memory
      record per tick from that tick's `RegisterState`/`AffectState` (the
      honest-proxy-content pattern Phase 1/3 established for their layers
      -- not real cognition, that's Phase 5+ once the workspace arbiter
      exists). `run()` (not `run_n_ticks()`, which every gate test drives
      directly and stays unmodified) also runs a background wall-clock-
      idle-gated consolidation loop alongside the heartbeat.
- [x] `prospective_commitment` (also created by `0002_memory.sql`) is
      untouched this phase -- it belongs with Layer 0's still-unbuilt
      retention buffer/specious present/prospective memory work, not
      Phase 4's Build Order scope.
- [x] `pytest` passes (59 tests: prior phases' gates + Phase 4 gate, plus
      new `teic/memory` unit/integration tests and two extended
      `tests/test_daemon.py` cases)
- [x] `mypy` passes project-wide (bare `mypy`, no args; added
      `teic/memory` to `pyproject.toml`'s mypy `files` list and a
      `sqlite_vec` `ignore_missing_imports` override -- no published stubs)
- [x] Gate test: `tests/test_gates/test_phase4.py` -- two independent
      halves per the gate's two clauses. (1) `activation()`'s value at a
      large `elapsed` is asserted at least 3x a matched exponential's value
      there -- the quantitative heavier-tail signature of a power law.
      (2) two memories with identical content/activation but opposite
      affect tags are ranked through the full `MemoryStore.query()` path
      (real sqlite-vec kNN, not hand-passed similarity) with opposite-signed
      `retrieval_affect_weight`, and the top result is asserted to swap --
      proving affect state, not noise, drives the ranking (a contrast case
      with `retrieval_affect_weight=0.0` shows the ranking is otherwise
      stable). Manually verified via `python -m teic`: real `tau1_working`
      rows land in `memory_record` with the documented content format.
