# Phase 9 notes

See `docs/plans/phase9-plan.md` for the UI collaboration decisions and
build order; `ARCHITECTURE.md`'s Phase 9 section is the canonical summary.
This file records only what isn't already there.

## cp1

- `teic/daemon.py` constructor takes an optional `llm_client` seam so tests
  never make a live network call; production path builds a real
  `OpenRouterClient` in `start()`.
- The `user_message` candidate uses fixed max salience factors specifically
  so it always wins arbitration deterministically in tests (`ignition_
  threshold()`'s max is exactly 1.0, condition is `>=`) — not tuned to
  "usually win," which would make the cp1 gate test flaky.

## cp2

- `TickSnapshot` is a new dataclass (`teic/daemon.py`), dispatched to
  listeners at the end of every tick — deliberately not a poll, per the
  plan's explicit preference for the existing `on_tick` callback pattern.
- `ChatView` mounts a fresh `Static` per assistant turn rather than
  appending into one growing widget, because `Static` has no in-place
  append API; `end_streaming_turn()` (called from the tick listener) closes
  the current turn out.
- `tmp_tui_settings` in `tests/test_phase9.py` bumps `base_tempo_hz` to 200
  so pilot tests see real ticks inside a normal timeout — `TeicApp` always
  builds a real `Heartbeat` inside `TeicDaemon.start()`, so the fake-clock
  DI seam other phases' tests use isn't reachable through the TUI.

## cp3

- Both new panels are plain widgets with a synchronous/`async` method
  (`run_probe()`, `apply_from_inputs()`) callable directly in a unit test
  without going through Textual's pilot — only the "is the button wired /
  is it disabled" behavior needs a pilot test.
- `config/tui_probe_evidence_sample.json` is committed sample evidence for
  the probe panel's default path (`InterfaceSettings.
  tui_probe_evidence_path`); it is demo data, not a real session's
  telemetry — B1-B4 have no live-evidence-derivation path anywhere in the
  codebase (Phase 8 included).
- Textual's `pilot.click()` requires the target to be within the current
  terminal size (default is small); `test_tui_probe_panel_renders_
  result_on_button_press` passes `size=(120, 60)` to `run_test()` to keep
  the stacked side-column panels on-screen.
