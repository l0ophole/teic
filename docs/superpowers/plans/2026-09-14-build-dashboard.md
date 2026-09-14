# Build Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Live terminal dashboard showing build progress, per-segment token stats, quota usage, and reset countdowns.

**Architecture:** Orchestrator persists telemetry to three polled files (`usage.json`, `build-history.jsonl`, `current.json`); a separate `rich`-based TUI polls them every ~2s in the alternate screen. Strict writer/reader decoupling.

**Tech Stack:** Python stdlib (orchestrator changes), `rich` 15.0.0 from the project venv (dashboard only).

## Global Constraints

- Orchestrator stays stdlib-only; no new dependencies (`rich` already in venv 15.0.0)
- Dry-run must remain side-effect-free (no telemetry writes)
- All polled files written atomically (tmp + `Path.replace`)
- Probe sessions for verification ≤2 total (~35K billed tokens each)
- `scripts/` is outside mypy scope (`pyproject.toml:40`) — light typing acceptable
- Commit style: descriptive, matching `Phase N Task X: ...` pattern

---

### Task 1: Orchestrator telemetry

**Files:**
- Modify: `scripts/orchestrate_build.py`
- Create: `tests/test_orchestrator_telemetry.py`
- Modify: `.gitignore`

**Interfaces (produced):**
- `USAGE_FILE`, `HISTORY_FILE`, `CURRENT_FILE: Path` (project root)
- `write_usage(info: dict, path: Path = USAGE_FILE) -> None` — merges `rate_limit_info` into `{"updated_at", "windows": {"five_hour"/"seven_day"/...: {utilization, resets_at, status}}}`
- `record_segment(label: str, res: SegmentResult, outcome: str, path: Path = HISTORY_FILE) -> None` — appends `{ts, label, phase, kind, turns, billed_tokens, cache_read_tokens, cache_creation_tokens, output_tokens, duration_s, outcome, session_id}`
- `write_current(label) / remove_current()` — `current.json` lifecycle
- `SegmentResult` gains `cache_read_tokens, cache_creation_tokens, output_tokens, duration_s: int/float = 0`

- [ ] **Step 1: Failing tests** (`tests/test_orchestrator_telemetry.py`)

```python
import json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import orchestrate_build as ob

def test_write_usage_creates_and_merges(tmp_path):
    p = tmp_path / "usage.json"
    ob.write_usage({"rateLimitType": "five_hour", "utilization": 0.99,
                    "resetsAt": 1000, "status": "allowed_warning"}, path=p)
    ob.write_usage({"rateLimitType": "seven_day", "utilization": 0.31,
                    "resetsAt": 2000, "status": "allowed"}, path=p)
    data = json.loads(p.read_text())
    assert data["windows"]["five_hour"]["utilization"] == 0.99
    assert data["windows"]["seven_day"]["resets_at"] == 2000

def test_write_usage_recovers_from_corrupt(tmp_path):
    p = tmp_path / "usage.json"; p.write_text("{oops")
    ob.write_usage({"rateLimitType": "five_hour", "utilization": 0.5}, path=p)
    assert json.loads(p.read_text())["windows"]["five_hour"]["utilization"] == 0.5

def test_record_segment(tmp_path):
    p = tmp_path / "history.jsonl"
    res = ob.SegmentResult(); res.num_turns = 3; res.billed_tokens = 500
    res.duration_s = 12.0; res.session_id = "abc"
    ob.record_segment("phase6 cp1", res, "ok", path=p)
    rec = json.loads(p.read_text().splitlines()[0])
    assert (rec["label"], rec["phase"], rec["kind"], rec["outcome"]) == ("phase6 cp1", 6, "build", "ok")
    assert rec["billed_tokens"] == 500 and rec["session_id"] == "abc"

def test_record_segment_kinds(tmp_path):
    p = tmp_path / "history.jsonl"; res = ob.SegmentResult()
    for label, kind in [("phase6 plan", "plan"), ("phase7 cp1 repair", "repair")]:
        ob.record_segment(label, res, "ok", path=p)
    kinds = [json.loads(l)["kind"] for l in p.read_text().splitlines()]
    assert kinds == ["plan", "repair"]
```

- [ ] **Step 2: Run** `.venv/bin/pytest tests/test_orchestrator_telemetry.py -q` → FAIL (no `write_usage`/`record_segment`)
- [ ] **Step 3: Implement** — add constants + the three helpers (usage via `tmp.replace(path)` atomic write; `kind` derived: `"repair" if "repair" in label else "plan" if "plan" in label else "build"`; `phase` from `re.match(r"phase(\d+)", label)`). In `run_segment`: move `start = time.monotonic()` to right after `Popen`; write `current.json` after launch; on `rate_limit_event` call `write_usage(info)`; at final parse set the four new fields + `res.duration_s`; wrap the guard block in `try/except Halt` that records (`"rate_limited"` for `RateLimitedHalt`, else `"halt"`) then re-raises; record `"timeout"`/`"halt"` in the two early-exit branches; record `"ok"` before `return`; delete `current.json` in a `finally`. Dry-run path untouched (returns before any writes).
- [ ] **Step 4:** tests pass; `--dry-run` regression shows no new files in `git status`
- [ ] **Step 5:** Live probe (~31K tokens): run the existing one-turn probe, then assert `usage.json` exists, `current.json` is gone, last `build-history.jsonl` line has `outcome=ok`
- [ ] **Step 6:** `.gitignore` += `usage.json`, `current.json`, `build-history.jsonl`; commit `"Orchestrator telemetry: usage snapshot, segment history, current-segment marker"`

### Task 2: Dashboard data layer + single-frame render

**Files:**
- Create: `scripts/build_dashboard.py` (imports `STATE_FILE`, `USAGE_FILE`, `HISTORY_FILE`, `CURRENT_FILE`, `DEFAULT_TIMEOUT_S`, `parse_checkpoints` from `orchestrate_build` — same sys.path[0], zero duplication)
- Create: `tests/test_build_dashboard.py`

**Interfaces (produced):** `fmt_countdown(seconds: float) -> str` (`"47m 12s"`, `"2d 3h"`, `"passed"` for ≤0); `load_state/load_usage/load_current(tail-parsers returning None on missing)`; `load_history(path, tail=10)`; `load_current` returns None if `started_at` older than `DEFAULT_TIMEOUT_S` (crash staleness); `phase_totals(history) -> dict[int, dict]`; `bar(frac) -> rich.text.Text` with color green <0.70 / yellow <0.90 / red ≥0.90; `render_frame() -> rich.renderable` assembling: header, Progress (completed phases, current phase + cp done/total from plan regex, status), Running (label + elapsed, or idle), Segments table (last 10 + per-phase cumulative), Quota (bars + "updated Xm ago"), Resets (live countdowns).

- [ ] Steps 1–4: failing tests for `fmt_countdown` (0s / 47m12s / 2d3h / negative), loaders (missing → None, stale `current.json` → None, tail cut), `phase_totals` sum, `bar` colors; implement; pass.
- [ ] **Step 5:** `--once` flag prints one frame via plain `Console()`; run `python3 scripts/build_dashboard.py --once` against Task-1 probe data → visually verify all five sections
- [ ] **Step 6:** commit `"Dashboard: data loaders and single-frame render"`

### Task 3: Live TUI loop

**Files:** Modify: `scripts/build_dashboard.py`

- [ ] `main()`: `Live(render_frame(), refresh_per_second=0.5, screen=True)` + per-tick 2s `select` on stdin in cbreak mode; `q` or Ctrl+C exits; `termios` state restored in `finally`; clear error if `import rich` fails ("run with .venv/bin/python")
- [ ] Verify `--once` still works, syntax check, commit `"Dashboard: live TUI with q/Ctrl+C quit"`

### Task 4: End-to-end + docs

- [ ] Re-run probe once; `--once` dashboard reflects it (history row + fresh quota snapshot); orchestrator `--dry-run` regression; full new-test suite green
- [ ] `docs/plans/PROMPTS.md` orchestrator section += `.venv/bin/python scripts/build_dashboard.py  # watch in a second terminal`
- [ ] Commit `"Dashboard: docs pointer + end-to-end check"`

**Spec coverage:** usage snapshot ✓T1 · history incl. failures/repairs ✓T1 · current segment ✓T1/T2 · progress+cp totals ✓T2 · countdowns ✓T2 · colored bars ✓T2 · staleness ✓T2 · q/Ctrl+C ✓T3 · `--once` ✓T2 · gitignore ✓T1.
