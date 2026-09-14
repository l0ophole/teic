# Build Dashboard — Design

**Status:** Approved (2026-09-14)

**Goal:** Live terminal dashboard showing build progress, per-segment token
statistics, current quota usage, and reset countdowns for the TEIC build
orchestrator.

## Decisions

- **Delivery:** Separate terminal TUI (`python scripts/build_dashboard.py`
  run with the project venv). Polls state files; works even when the
  orchestrator is idle (shows last known state).
- **Usage freshness:** Snapshot only. The orchestrator writes a usage
  snapshot after every segment and every rate-limit event. Zero quota cost;
  staleness shown with an "updated Xm ago" marker. No self-probing.
- **Rendering:** `rich` (already in project venv, 15.0.0). Live display in
  the alternate screen, redraw ~every 2s, `q`/Ctrl+C to quit, plus `--once`
  single-frame mode for testing/scripting.

## Data plumbing (orchestrator changes)

The orchestrator keeps all data in memory; it persists three files the
dashboard polls:

- **`usage.json`** — rewritten whenever a `rate_limit_event` arrives and
  again after each segment completes (last-known wins):
  `{updated_at, windows: {"five_hour"/"seven_day"/...: {utilization,
  resets_at, status}}}`. Atomic writes (tmp + replace).
- **`build-history.jsonl`** — one JSON line appended per segment attempt
  *including failures and repairs*: `{ts, label, phase, kind:
  plan|build|repair, turns, billed_tokens, cache_read_tokens,
  cache_creation_tokens, output_tokens, duration_s, outcome:
  ok|rate_limited|timeout|halt, session_id}`. Hooked inside `run_segment`
  at every exit path (guards record-then-reraise).
- **`current.json`** — written at segment start `{label, started_at}`,
  deleted in a `finally` at segment end. Absent file = no segment running.

All three are transient/machine-local → gitignored. Dry-run writes nothing.

## Dashboard layout

```
TEIC Build — Mon Sep 14 18:52
Progress     Completed: P0–P5 ✓   Current: Phase 6, cp2/cp3 (building)
Running      phase6 cp2 — 23m elapsed        (or: idle / no data yet)
Segments     time  label          turns  billed  cache-read  dur   result
             ...last 10 + per-phase cumulative totals
Quota        5-hour ████████░░ 82%   Weekly ███░░░░░░░ 31%   (updated 12s ago)
Resets       5-hour in 47m 12s    weekly in 2d 3h
```

- Bars color green <70%, yellow 70–90%, red ≥90% (matches the
  orchestrator's 90% warning)
- Countdowns computed live each frame from `resets_at` epochs
- Checkpoint totals parsed from the plan with the same regex the
  orchestrator uses (`parse_checkpoints` imported, not duplicated)
- Missing/stale files handled gracefully (staleness marker on quota, "no
  data yet" before first run); a `current.json` whose `started_at` is older
  than `DEFAULT_TIMEOUT_S` is treated as crashed/stale

## Verification

Unit tests for telemetry helpers and dashboard data layer (tmp_path
fixtures); one real probe segment end-to-end; `--once` visual check;
orchestrator `--dry-run` regression.
