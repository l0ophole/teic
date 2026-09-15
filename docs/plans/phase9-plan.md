# Phase 9 plan — UI (terminal TUI)

Gate (from PlanBuildTEIC.md BUILD ORDER): user can chat, see status, and
optionally perturb state.

## UI collaboration checkpoint — decisions recorded

- **Interface type:** terminal TUI (`textual`/`rich`). New runtime
  dependency: `textual` (ask user to confirm the add per "no dependencies
  beyond the stack listed without asking" — flag at cp1).
- **Chat surface:** streaming tokens.
- **Status visibility (v1):** valence/arousal sparkline, tick tempo,
  viability budget reserve, workspace ignition events. (Memory/goal detail
  and full telemetry deferred to v2.)
- **Manual controls (v1):** pause/resume, session reset only. (Tick-rate
  adjustment, forced consolidation, injection, self-model editor, memory
  inspector deferred to v2.)
- **Perturbation control surface:** included in v1, gated behind
  `settings.research.enabled` (existing flag, `teic/harness/perturbation.py`
  pattern).
- **Notifications:** agent-initiated proactive messages on homeostatic
  threshold crossings render as inline system-style lines in the same
  pane (not a separate channel).
- **Tier B probes surfaced in UI (v1):** B1–B4 only, run on demand from a
  TUI action; B5–B8 stay CLI-only (`teic/harness/runner.py`) for v1.
- **Log surface (v1):** simple unfiltered tail. Filtering/search/replay
  deferred to v2.
- **Persistence/OpenRouter defaults:** unchanged — existing SQLite
  (`data/teic.db`) and `config/default.toml` primary/fallback models.
- **Web dashboard:** out of scope for v1 (`teic/interface/web/` stays an
  empty placeholder).

## Key architectural gap this phase closes

No prior phase makes a live OpenRouter network call: `_on_tick` in
`teic/daemon.py` calls `render_prompt_if_ignited()` and estimates cost via
`PricingCache`, but explicitly does not send (see `teic/daemon.py:540-547`
comment "No network call is made (out of scope)"). There is also no
"user chat message" workspace-candidate source — every current candidate
(`interoception`, `memory`, `viability`) is internally generated
(`teic/daemon.py:424-470`). Phase 9 must add both: a real
`ChatClient.stream()` call gated behind ignition + budget, and a user-input
candidate that can win arbitration and ignite.

## Context to read (this session only)

- `BUILD_STATUS.md` — status table + current state
- `docs/PlanBuildTEIC.md` lines 44–56 (UI collaboration checkpoint spec,
  now answered above) and line 195 (Phase 9 gate)
- `teic/daemon.py` — `_on_tick` (candidate construction ~L418-536, ignited
  send seam ~L540-560), `start()`/`stop()` lifecycle, signal handling
- `teic/workspace/broadcast.py`, `teic/workspace/arbiter.py` — ignition/
  candidate contract a new "user_message" candidate must match
- `teic/llm/client.py` — `ChatClient.stream()` signature (already built,
  unused by daemon until now)
- `teic/llm/cost.py` — `PricingCache.estimate_cost_usd()` (existing spend
  estimate to convert into real post-stream spend)
- `teic/harness/perturbation.py` — bounded perturbation API + research-flag
  gate pattern to reuse from the TUI's perturbation panel
- `teic/harness/runner.py` — B1–B4 probe invocation pattern to reuse for
  the TUI's on-demand probe action
- `teic/settings.py` — `InterfaceSettings` (currently only `web_host`/
  `web_port`, leftover placeholder; extend for TUI needs), `ResearchSettings`
- `teic/interface/terminal/__init__.py`, `teic/interface/web/__init__.py`
  (confirm still empty before writing into `terminal/`)
- Do not re-read Phase 0–8 notes; cite `docs/plans/phaseN-notes.md` by path
  if a mechanism needs recalling.

## File-by-file build order

### cp1 — real OpenRouter send + user-input candidate (headless, no TUI yet)
1. `pyproject.toml` (or wherever deps are declared) — add `textual`;
   confirm with user before committing this checkpoint's deps.
2. `teic/models/tick.py` or `teic/models/workspace.py` — add a
   `user_message` field/candidate-source enum value if not already
   representable by `WorkspaceCandidate`.
3. `teic/daemon.py` — add an async user-input queue the tick loop drains
   each tick; construct a `WorkspaceCandidate` from a pending user message
   (precision/affective_weight/goal_relevance per the interoception/memory
   candidates' pattern at L424-470) and append to `candidates`.
4. `teic/daemon.py` — replace the "No network call is made" seam
   (~L540-560): on ignited winner, call `ChatClient.stream()` with the
   rendered prompt, accumulate the streamed response, replace the
   pre-send `PricingCache.estimate_cost_usd()` charge with the real
   post-response cost, and emit a `LogEvent` per chunk or per completed
   turn (decide during implementation; log at minimum the full turn).
5. `tests/test_phase9.py` (new) — user-message candidate can win
   arbitration and ignite; streamed response is persisted and charged
   against the viability ledger; a mocked `ChatClient` (no live network
   call in CI, matching Phase 8's no-live-LLM test convention).
6. Verify + commit.

### cp2 — terminal TUI: chat, status panel, controls
7. `teic/interface/terminal/app.py` — `textual` `App` subclass; owns the
   `TeicDaemon` instance, runs the daemon's `run()` task alongside the
   TUI event loop (mirrors `teic/__main__.py`'s asyncio+signal pattern,
   replacing prints with widget updates).
8. `teic/interface/terminal/chat_view.py` — streaming chat pane; feeds
   user input into the cp1 input queue; renders streamed tokens as they
   arrive; renders proactive/system notifications inline (distinct style).
9. `teic/interface/terminal/status_panel.py` — valence/arousal sparkline,
   tick tempo, viability budget reserve, ignition-event feed; subscribes
   to daemon state (poll each tick or via a callback/event bus — decide
   during implementation, prefer the existing `on_tick` callback pattern
   over polling).
10. `teic/interface/terminal/controls.py` — pause/resume and session-reset
    actions wired to daemon lifecycle methods (add `pause()`/`resume()` to
    `TeicDaemon` if not present; reuse `stop()`/`start()` for reset).
11. `teic/interface/terminal/log_view.py` — unfiltered scrolling tail of
    `LogEvent` rows (existing `LogSink`/persistence layer, no new schema).
12. `teic/__main__.py` — new `--tui` flag (or a separate `python -m
    teic.interface.terminal`) launching the TUI instead of the headless
    print loop; keep the existing headless path for CI/non-interactive use.
13. `tests/test_phase9.py` — extend with TUI widget-level tests using
    `textual`'s test harness (pilot/snapshot testing) for chat send,
    status update on tick, pause/resume.
14. Verify + commit.

### cp3 — perturbation panel, on-demand probes, docs
15. `teic/interface/terminal/perturbation_panel.py` — research-only-gated
    panel wrapping `teic.harness.perturbation`'s bounded API; hidden/
    disabled when `settings.research.enabled` is `False`; every action logs
    through the existing permanent-logging hook.
16. `teic/interface/terminal/probe_panel.py` — on-demand B1–B4 trigger
    reusing `teic.harness.runner`'s probe invocation, rendering
    `ProbeResult` inline.
17. `teic/settings.py` — extend `InterfaceSettings` with any TUI-specific
    fields introduced during cp2/cp3 (e.g. log tail depth); leave
    `web_host`/`web_port` untouched for the deferred web dashboard.
18. `tests/test_phase9.py` — perturbation panel refuses when
    `research.enabled=False`; probe panel renders a result.
19. `docs/plans/phase9-notes.md` + `BUILD_STATUS.md` (Phase 9 row →
    Complete, one-liner) + `ARCHITECTURE.md` Phase 9 section (note v2
    deferrals: web dashboard, B5–B8 in-UI, filtered/searchable/replay
    logs, injection/self-model-editor/memory-inspector controls,
    tick-rate adjustment, forced consolidation).
20. Verify + commit.

## Checkpoints

- cp1: real-send-and-user-candidate - `ChatClient.stream()` is actually
  called on ignited winners with real post-response cost accounting, and
  a user-message candidate can win arbitration; headless, no TUI code yet.
- cp2: terminal-tui-core - chat (streaming), status panel (valence/
  arousal, tempo, budget, ignition feed), pause/resume/reset, and an
  unfiltered log tail are all live in a `textual` TUI.
- cp3: perturbation-probes-docs - research-flag-gated perturbation panel,
  on-demand B1–B4 probe panel, and Phase 9 docs (notes, BUILD_STATUS,
  ARCHITECTURE, v2 deferral list) are complete.
