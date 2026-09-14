# TEIC-Agent — Implementation Plan

## Context

The user wants to build **TEIC-Agent** (Temporal–Embodied–Interoceptive Chat Agent), a research-grade persistent Python daemon whose design thesis is "the model is an organ, not the organism": an LLM (via OpenRouter) is a subroutine called for language, while a continuously running `asyncio` process maintains its own temporal, embodied, and interoceptive state. The full spec lives at `docs/PlanBuildTEIC.md` and mandates two deliverables — the agent itself, and a falsifiable assessment harness (Tier A structural audits, Tier B behavioral probes, ablation battery, falsifier suite) that makes claims about functional correlates of experience empirically testable without overclaiming.

The project directory (`/mnt/ide/teamssd/part1/projects/teic`) is a **completely empty slate**: no git repo, no Python scaffolding, no `.env`, only the spec doc. This is a from-scratch build. The spec itself mandates a UI collaboration checkpoint before any architecture plan is written — that checkpoint is complete; all decisions below are locked in as constraints, not open questions.

**Spec-critical non-negotiables to hold onto throughout the build** (from the spec's "Things Not To Do" and Ethics sections):
- No LLM-wrapper-with-state-stuffed-into-prompt-text. Interoceptive state must cause behavior through non-linguistic channels (temperature, tempo, retrieval weighting, etc.) — Phase 2 is the real gate.
- Power-law memory decay, never exponential.
- No hand-authored emotion labels (`mood = "curious"` banned) — derive everything from deltas.
- Verbal self-report is a dependent variable in the harness, never primary evidence.
- No "consciousness score" — report theory-indexed indicators with evidential weight discounted by design-in bias.
- No training/prompting the agent to affirm or deny internal states.
- Termination-on-viability-failure must never be a silent default.

## Locked-In Decisions (from UI checkpoint + follow-up questions)

| Area | Decision |
|---|---|
| Interface | Hybrid: event-driven terminal chat (agent can initiate utterances) + local FastAPI+HTMX web dashboard |
| Status visibility | "Standard" tier for v1 (goal, tempo, budget reserve, interoceptive vector, valence/arousal sparkline, workspace broadcast); architected so "Rich" tier (+ memory consolidation activity, ignition events, felt-duration sparkline) is an incremental add at Phase 9 |
| Telemetry cadence | Per significant event (ignition, threshold crossings, broadcasts) via SSE, not per raw tick |
| Manual controls | Basic (pause/resume, tick-rate, session reset, filterable/searchable log tail) + research-only gated (register injection, memory inspector, self-model editor, perturbation) |
| Perturbation UI | Included in v1, gated behind research-only flag, bounded intensity/duration enforced **server-side** |
| Proactive contact | Agent can initiate unsolicited messages in both chat and dashboard on threshold crossings |
| Persistence | SQLite for everything, including the telemetry/log stream (JSONL export available on demand, not a separate live write path) |
| Vector index | `sqlite-vec` (keeps "one file, no external DB" story literally true; transactional consistency with memory rows) |
| Embeddings | Local embedding model (`sentence-transformers`) — approved as a new dependency |
| Dashboard sparklines | Vendored `uPlot` (~45KB, zero deps of its own) — approved as a new dependency, enables later replay/scrub |
| OpenRouter primary/fallback | `deepseek/deepseek-v4-flash-latest` / `inclusionai/ling-3.0-flash-vl:free` — **the leading `~` on the primary slug is unverified; must confirm against `GET /models` before Phase 0 is marked done** |
| Cost cap | $10/month default viability budget (configurable); harness probe LLM-judge calls use a **separate** harness budget line so probes don't starve the live agent |
| v1 probe scope | Tier A1–A5 + falsifier suite (mandatory, non-deferrable) + Tier B1–B4 only. B5–B8 deferred to v2 |
| Probe session scope | Isolated forked session by default; a flag can target the live session for probes needing long-run continuity (deferred use, v2) |
| Target hardware | Runs manually (`python -m teic`), not daemonized/systemd for v1 |
| Termination default | **Disabled by default.** Budget-zero triggers a low-power halt (action/spend suppression), not process exit, unless `allow_actual_termination=true` + a `termination_justification` string are both set in config |

## Module / File Layout

Flat `teic/` package at repo root (app/harness, not a published library):

```
teic/
├── pyproject.toml, README.md, ARCHITECTURE.md, BUILD_STATUS.md, .env.example
├── config/{default.toml, thresholds.toml, ablation_profiles.toml}
├── data/                      # teic.db (sqlite) + reports/, gitignored
├── docs/PlanBuildTEIC.md
├── teic/
│   ├── __main__.py, settings.py, daemon.py
│   ├── models/                # pure pydantic: tick, registers, affect, workspace, memory, log_event, self_model, probe, ablation
│   ├── temporal/               # Layer 0: heartbeat, retention, specious_present, protention, prospective, narrative_self
│   ├── embodiment/              # Layer 1: effectors, sensors, forward_model, body_schema, affordance, viability, agency, social_body
│   ├── interoception/            # Layer 2: channels, inference, allostasis, affect_dynamics, mood, modulation.py (Phase 2 core), reportability
│   ├── memory/                  # store, decay, retrieval, consolidation, vector_index (sqlite-vec)
│   ├── workspace/                # Layer 3: arbiter, broadcast, mineness, self_model, metacognition, narrative_constructor
│   ├── llm/                      # client (httpx/OpenRouter), prompt_assembly (broadcast-only enforcement), cost, schema
│   ├── persistence/               # db.py, migrations/0001-0004.sql, log_sink.py
│   ├── interface/
│   │   ├── terminal/             # chat_app.py (rich), input_bridge.py
│   │   └── web/                  # FastAPI app, routes_{chat,status,controls,research}, sse.py, templates/, static/ (uPlot vendored)
│   ├── ethics/                    # perturbation.py (bounded caps), guardrails.py (no-affirm/deny lint, termination gate)
│   └── harness/                    # runner, telemetry_reader, thresholds, report, probes/{tier_a, b1-b4}, falsifiers, ablation
├── tests/                          # mirrors package tree + test_gates/ (one module per phase 0-9)
└── scripts/init_db.py
```

## Process & Task Topology

Single process, single event loop (`asyncio.TaskGroup`, Python 3.12+). Concurrent tasks: `heartbeat_task` (variable-tempo tick loop — the cognitive cycle: sensors → interoception → candidate collection → arbiter → maybe broadcast/LLM call → effectors → memory write → telemetry), `sensor_task` (fixed fast cadence, decoupled from cognitive tempo), `user_input_task` (terminal stdin via `asyncio.to_thread`, or FastAPI handlers push directly), `consolidation_task` (idle-gated tau4 background job), `llm_watchdog_task` (timeout enforcement independent of tick cadence), `web_server_task` (embedded uvicorn in the same loop), `sse_broadcaster_task` (per-significant-event push to dashboard clients).

User input **joins** the tick loop as a workspace candidate bid (high salience, boosted `goal_relevance`) rather than interrupting it — consistent with the capacity-1-per-cycle architecture. To avoid idle-tempo chat latency (up to 5s at 0.2Hz), user input arrival itself nudges the `social_contact` register, which raises arousal/tempo for the *next* tick — a non-linguistic, causally honest way to make the agent "wake up" for a conversation.

Shutdown: SIGINT/SIGTERM → `shutdown_event`; heartbeat checks it only at cycle boundaries (atomic cycles); persist retention buffer/narrative state every tick, not just at shutdown, so an unclean kill loses at most one tick.

## Data Model (SQLite, `aiosqlite`, WAL mode)

Four migration files: `0001_init.sql` (session, tick, register_sample, affect_sample), `0002_memory.sql` (memory_record, prospective_commitment, consolidation_event, `memory_vec` sqlite-vec virtual table), `0003_telemetry.sql` (log_event — doubles as the JSONL-export source, workspace_broadcast, llm_call_log, viability_ledger), `0004_probes.sql` (probe_run, ablation_variant_run). Full schema sketches captured from the design pass; `mineness_tag`, `ignited` boolean, and per-channel posterior variance are first-class columns so the harness can query them directly.

**Power-law retrieval** (`memory/decay.py`, `memory/retrieval.py`): `activation(m,t) = base_activation * (1 + (t - last_access)/c)^(-alpha)`, `score = activation * semantic_match * affective_tag_weight(current_affect)`. Retrieval resets the decay clock on read (reinforcement) without touching `base_activation`, preserving "lossy by design" even for frequently-used memories.

## Core Data Models

Pydantic v2 models in `teic/models/`: `TickContext`, `RegisterState` (the 11-channel vector + parallel posterior variances, never hand-authored), `AffectState` (valence/arousal/mood as fields; `nearest_attractor_label()` is a **method**, not a stored field — this is the concrete mechanism banning hard-coded emotion labels), `WorkspaceCandidate`/`WorkspaceBroadcast`, `MemoryRecord`, `LogEvent`, `SelfModel` (body/agency/interoception/history/identity/mental-state/temporal-self, with a `version` counter for the B7-style self-model-updating probe), `ProbeResult`.

## Workspace Arbiter

`salience = novelty * precision * affective_weight * goal_relevance`, one winner per cycle (`max()` over that tick's candidate list), `ignited = winner.salience >= ignition_threshold(affect, mood)` where the threshold itself is modulated by arousal (lower under stress) and mood. Sub-threshold candidates are logged (`ignited=0`) and may still influence modulation parameters, but are never attached to the specious present and never enter `prompt_assembly.py` — this dual property (can-modulate vs. cannot-be-broadcast) is exactly what the ignition-dissociation experiment measures.

## Non-Linguistic Modulation Pathway (`interoception/modulation.py` — Phase 2, the real gate)

Single-entry-point `ModulationParams` computed once per tick from `(registers, affect, mood)` and threaded explicitly through every downstream call site (no module re-reads raw state on its own). Concrete wiring:
- temperature/top_p ← epistemic_tension (up), negative mood (narrows)
- retrieval_k/weighting ← context_pressure (down), memory_fragmentation (up), current affect (mood-congruent bias)
- planning_depth ← budget_reserve/burn_rate (down when strained), goal_gradient (down when path is obvious)
- tool_risk_tolerance ← effector_integrity, valence
- salience_weight_overrides ← per-source multipliers (e.g. latency_strain up-weights embodiment candidates)
- tempo_hz ← `tempo_gain(arousal) * base_hz` (idle 0.2Hz → high-error 5-10Hz), fed straight into the heartbeat's next sleep interval
- speak_gate_open ← ignition + epistemic_tension + refractory cooldown

Phase 2's gate test holds prompt text byte-identical across two runs while varying only injected `RegisterState`, then asserts divergent `tempo_hz`/sampling-params/speak-gate — checkable with zero reference to generated text content.

## OpenRouter Integration Boundary

`llm/client.py`: `httpx.AsyncClient` (chosen over the `openai` SDK for full control of retry/backoff/streaming/logging), config-driven model selection, exponential backoff on 429/5xx, automatic fallback to the secondary model after repeated primary failure, streaming SSE parsing. All failures surface as `effector_integrity`/`latency_strain` register perturbations — never a bare exception.

`llm/prompt_assembly.py`: `assemble_prompt(broadcast: WorkspaceBroadcast, narrative_tail, modulation: ModulationParams)` — the type signature itself is the enforcement boundary (no `RegisterState`/`AffectState` parameter exists), backed by `mypy --strict` plus a unit test that inspects `__annotations__` as a durable regression guard against the "costume" failure mode.

## Assessment Harness

`harness/runner.py` orchestrates seeded probe runs against isolated forked sessions by default. Falsifiers (`harness/falsifiers.py`) run first and block subsequent probes on failure (`fail_fast`); they're also plain `pytest` tests for CI. Tier A (A1–A5) are mostly structural/log-inspection audits (e.g. A1 asserts broadcast-per-tick ≤ 1 and no non-winner leakage into `llm_call_log.prompt`); Tier B1–B4 are behavioral (B1 blind introspection perturbs a channel via the bounded `ethics/perturbation.py` API, checks self-report correlation above chance *and* independent behavior shift). `report.py` renders a Markdown+JSON assessment report with the mandatory honest-framing boilerplate prepended verbatim and computes the L0–L4 graded verdict — v1's report explicitly states L3+ is out of scope since B5–B8 aren't implemented. Thresholds load from `config/thresholds.toml`, pydantic-validated, snapshotted into every `ProbeResult`.

## Build Order (Phase Gates)

| Phase | Deliverable | Gate test |
|---|---|---|
| 0 | Daemon skeleton, fixed-tempo heartbeat, settings, persistence+migrations, log_sink, OpenRouter client skeleton | Short synthetic empty-clock smoke test; clean start/stop, DB rows per tick. **Also: manually verify both OpenRouter model slugs against `GET /models` before closing this phase.** |
| 1 | Sensors, interoception channels (logging only) | Channels move under synthetic load; no behavior-change assertion yet |
| 2 | `modulation.py`, `reportability.py`, wired into heartbeat + prompt_assembly's sampling params (not text) | Identical prompt text, different registers → divergent tempo/temperature/speak-gate. **Hard stop for user check-in.** |
| 3 | Forward model, protention buffer, prediction error | Contingency-change test: 3x latency injection → error spike → adaptation |
| 4 | Memory timescales, power-law decay, consolidation, sqlite-vec + sentence-transformers embeddings | Retrieval ranking shifts with affect; activation decay fits power-law, not exponential |
| 5 | Workspace arbiter, ignition threshold, broadcast | Sub-threshold candidate demonstrably modulates but never broadcasts/reports |
| 6 | Viability, allostasis, termination gate | Budget→0 under default config halts action/spend without process exit; opt-in+justification required for real termination. Full 12h empty-clock run executed as a documented manual step (mechanism verified via injected synthetic clock in fast tests) |
| 7 | Self-model, metacognition, reportability gate completed | Editing self-model fields predictably changes downstream behavior; confidence calibration check |
| 8 | Harness: falsifiers, Tier A1-5, B1-4, thresholds, report | Falsifiers pass clean and run first; full harness run produces a graded report |
| 9 | Terminal + web interface, Standard-tier telemetry, research-gated routes | Chat round-trip works; research routes 403 without flag; perturbation caps enforced server-side even against crafted requests |

Maintain `BUILD_STATUS.md` and `ARCHITECTURE.md`, updated at each phase; run the test suite and check in with the user before starting the next phase, per the spec's mandatory workflow.

## Risks / Open Questions Carried Forward

1. **Model slug verification** — `~deepseek/deepseek-v4-flash-latest` has an unexplained leading `~`; confirm both slugs exist verbatim via OpenRouter's `/models` endpoint before Phase 0 closes. Do not silently strip or keep the `~` without checking.
2. **Manual-run vs. empty-clock tension** — resolved via dual verification (fast synthetic-clock mechanism test + a separate documented manual 12h run), not a single automated gate.
3. **OpenRouter pricing/model-list fetched at startup** — needs a defined degraded-mode behavior if OpenRouter is unreachable at boot (cache last-known pricing rather than blocking).
4. **Terminal input UX** — blocking `input()` via `asyncio.to_thread` accepted for v1 despite minor interleaving raggedness with proactive agent messages; `prompt_toolkit` flagged as a possible future ask, not added now.
5. **Reportability-gate prompt wording vs. "no affirm/deny" rule** — must be documented explicitly in `ARCHITECTURE.md`: permission-to-report ("you may reference this cycle's broadcast content") is fine; content-biasing ("you feel X" / "you don't experience X") is banned. Encode as a lint rule in `ethics/guardrails.py`.
6. **Termination language tension in the spec itself** — Layer 1 says viability-zero causes "actual termination"; the Ethics section requires it never be a silent default. The locked-in decision (disabled by default, explicit opt-in + justification) resolves this in favor of the Ethics section — note this as an intentional, spec-consistent resolution in `ARCHITECTURE.md`, not a deviation.
7. **Idle definition for consolidation** — must be wall-clock-based, not tick-count-based, so low-tempo periods don't starve tau4 consolidation disproportionately.

## Dependencies (final list, with new additions flagged)

Spec-named: Python 3.12+, `httpx`, `pydantic`/`pydantic-settings`, `mypy`, `pytest`/`pytest-asyncio`, `fastapi`, `uvicorn`, `rich`, `sqlite-vec`.
New, now approved via this planning conversation: `aiosqlite` (async SQLite driver, near-mandatory given asyncio+SQLite), `jinja2` (FastAPI/HTMX templating), `sentence-transformers` (local embeddings), vendored `uPlot` JS (dashboard sparklines/replay, not a Python dependency).
Explicitly NOT adding: `openai` SDK, `structlog`, `tenacity`, `alembic`, `sqlalchemy`, `prompt_toolkit` (v1).

## Verification

- Each phase gate above is a concrete, automated `pytest` test under `tests/test_gates/` — run `pytest tests/test_gates/test_phaseN.py` after each phase and show the user the output before proceeding.
- `mypy --strict` on `teic/models/`, `teic/interoception/`, `teic/workspace/`, `teic/llm/` at minimum, checked in CI-style after each phase.
- Phase 8's harness produces a real Markdown+JSON report the user can read (`data/reports/assessment_<ts>.md`) — show this to the user as the harness's own self-verification.
- Phase 9: manually run `python -m teic` and interact via terminal chat + open the dashboard in a browser; confirm research-gated routes reject requests without the flag.
