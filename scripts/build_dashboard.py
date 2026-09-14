#!/usr/bin/env python
"""Build dashboard: data loaders + single-frame render (--once).

Live TUI loop arrives in Task 3; today main() prints one frame.
Run with the project venv (rich lives there):
    .venv/bin/python scripts/build_dashboard.py --once
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.console import Group
    from rich.table import Table
    from rich.text import Text
except ImportError:
    sys.exit("run with .venv/bin/python scripts/build_dashboard.py")

from orchestrate_build import (CURRENT_FILE, DEFAULT_TIMEOUT_S, HISTORY_FILE,
                               STATE_FILE, USAGE_FILE, parse_checkpoints)

WINDOW_ORDER = ["five_hour", "seven_day"]


# ------------------------------------------------------------------ formatting

def fmt_countdown(seconds: float) -> str:
    if seconds <= 0:
        return "passed" if seconds < 0 else "0s"
    if seconds < 60:
        return f"<{int(seconds)}s"
    if seconds < 3600:
        return f"{int(seconds // 60)}m {int(seconds % 60)}s"
    if seconds < 86400:
        return f"{int(seconds // 3600)}h {int(seconds % 3600 // 60)}m"
    return f"{int(seconds // 86400)}d {int(seconds % 86400 // 3600)}h"


def bar(frac: float) -> Text:
    frac = max(0.0, min(1.0, frac))
    filled = int(frac * 10)
    style = "green" if frac < 0.70 else "yellow" if frac < 0.90 else "red"
    return Text("█" * filled + "░" * (10 - filled), style=style)


def _to_epoch(value) -> float | None:
    """Accept epoch numbers or ISO strings; return None if unparseable."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return datetime.fromisoformat(str(value)).timestamp()
    except ValueError:
        return None


# ------------------------------------------------------------------ loaders

def load_json(path: Path):
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def load_state(path: Path):
    data = load_json(path)
    if not isinstance(data, dict):
        return None
    return data


def load_usage(path: Path):
    data = load_json(path)
    if not isinstance(data, dict):
        return None
    return data


def load_current(path: Path):
    data = load_json(path)
    if not isinstance(data, dict):
        return None
    started = _to_epoch(data.get("started_at"))
    if started is None:
        return None
    if time.time() - started > DEFAULT_TIMEOUT_S:
        return None  # stale: crashed orchestrator
    return data


def load_history(path: Path, tail: int = 10) -> list[dict]:
    try:
        lines = path.read_text().splitlines()
    except OSError:
        return []
    records = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue  # partial write; skip silently
        if not isinstance(parsed, dict):
            continue
        records.append(parsed)
    return records[-tail:]


def phase_totals(history: list[dict]) -> dict[int, dict]:
    totals: dict[int, dict] = {}
    for rec in history:
        phase = rec.get("phase")
        if phase is None:
            continue
        entry = totals.setdefault(
            phase, {"billed": 0, "turns": 0, "segments": 0})
        entry["billed"] += rec.get("billed_tokens") or 0
        entry["turns"] += rec.get("turns") or 0
        entry["segments"] += 1
    return totals


# ------------------------------------------------------------------ sections

def _dim(text: str) -> Text:
    return Text(text, style="dim")


def _header(state, now: float) -> Table:
    project = Path(__file__).resolve().parent.parent.name
    status = state.get("status", "?") if state else "?"
    phase = state.get("phase", "?") if state else "?"
    t = Table(box=None, show_header=False, padding=0)
    t.add_row(Text(
        f"{project}  ·  phase {phase} ({status})  ·  "
        f"{datetime.fromtimestamp(now).strftime('%Y-%m-%d %H:%M:%S')}",
        style="bold"))
    return t


def _progress(state) -> Table:
    t = Table(title="Progress", box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold")
    t.add_column()
    if not state:
        t.add_row("·", _dim("no data yet"))
        return t
    completed = state.get("completed_phases") or []
    t.add_row("completed phases",
              ", ".join(str(p) for p in completed) or _dim("none"))
    phase = state.get("phase")
    status = state.get("status", "?")
    t.add_row("current", f"phase {phase} — {status}")
    plan_path = state.get("plan")
    cps_total = cps_done = None
    if plan_path:
        plan = Path(plan_path)
        if not plan.is_absolute():
            plan = Path(__file__).resolve().parent.parent / plan
        if plan.exists():
            try:
                cps = parse_checkpoints(plan)
                cps_total = len(cps)
                done = state.get("checkpoints_done") or []
                if not isinstance(done, list):
                    done = []
                cps_done = sum(1 for cp in cps if cp in done)
            except Exception:
                pass
    if cps_total is not None:
        t.add_row("checkpoints", f"{cps_done}/{cps_total} done")
    else:
        t.add_row("checkpoints", _dim("no plan yet"))
    return t


def _running(now: float, current_path: Path = CURRENT_FILE) -> Table:
    t = Table(title="Running", box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold")
    t.add_column()
    current = load_current(current_path)
    if current:
        elapsed = now - (_to_epoch(current.get("started_at")) or now)
        t.add_row(current.get("label", "?"), f"{fmt_countdown(elapsed)} elapsed")
    else:
        t.add_row("·", _dim("idle"))
    return t


def _segments(history) -> Table:
    t = Table(title="Segments", box=None, padding=(0, 1))
    t.add_column("time")
    t.add_column("label")
    t.add_column("turns", justify="right")
    t.add_column("billed", justify="right")
    t.add_column("cache-read", justify="right")
    t.add_column("dur")
    t.add_column("outcome")
    if not history:
        t.add_row(_dim("no data yet"), "", "", "", "", "", "")
        return t
    for rec in history:
        ts = _to_epoch(rec.get("ts"))
        when = (datetime.fromtimestamp(ts).strftime("%H:%M")
                if ts else "?")
        dur = rec.get("duration_s") or 0
        dur_s = (f"{int(dur)}s" if dur < 60
                 else f"{int(dur // 60)}m" if dur < 3600
                 else f"{int(dur // 3600)}h")
        outcome = rec.get("outcome") or "?"
        t.add_row(when, rec.get("label") or "?",
                  str(rec.get("turns") or 0),
                  f"{rec.get('billed_tokens') or 0:,}",
                  f"{rec.get('cache_read_tokens') or 0:,}",
                  dur_s, outcome)
    totals = phase_totals(history)
    for phase, pt in sorted(totals.items()):
        t.add_row(_dim("Σ"), _dim(f"phase {phase}"),
                  _dim(str(pt["turns"])),
                  _dim(f"{pt['billed']:,}"),
                  _dim(f"{pt['segments']} seg"),
                  "", "")
    return t


def _sorted_windows(windows: dict) -> list[tuple[str, dict]]:
    def key(item):
        name = item[0]
        return (WINDOW_ORDER.index(name) if name in WINDOW_ORDER
                else len(WINDOW_ORDER), name)
    return sorted((windows or {}).items(), key=key)


def _quota(usage, now: float) -> Table:
    t = Table(title="Quota", box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold")
    t.add_column()
    windows = (usage or {}).get("windows")
    if not isinstance(windows, dict) or not windows:
        t.add_row("·", _dim("no data yet"))
        return t
    updated = _to_epoch((usage or {}).get("updated_at"))
    for name, w in _sorted_windows(windows):
        if not isinstance(w, dict):
            continue
        util = w.get("utilization")
        if util is None or not isinstance(util, (int, float)):
            t.add_row(name, _dim("unknown"))
            continue
        bar_w = bar(util)
        suffix = ""
        if updated is not None:
            age = max(0.0, now - updated)
            suffix = f"  updated {fmt_countdown(age).lstrip('<')} ago"
        t.add_row(name, bar_w, Text(f"{util:.0%}{suffix}"))
    return t


def _resets(usage, now: float) -> Table:
    t = Table(title="Resets", box=None, show_header=False, padding=(0, 1))
    t.add_column(style="bold")
    t.add_column()
    windows = (usage or {}).get("windows")
    if not isinstance(windows, dict) or not windows:
        t.add_row("·", _dim("no data yet"))
        return t
    for name, w in _sorted_windows(windows):
        if not isinstance(w, dict):
            continue
        resets_at = _to_epoch(w.get("resets_at"))
        if resets_at is None:
            t.add_row(name, _dim("unknown"))
        else:
            t.add_row(name, f"resets in {fmt_countdown(resets_at - now)}")
    return t


# ------------------------------------------------------------------ frame

def render_frame(state_path: Path = STATE_FILE, usage_path: Path = USAGE_FILE,
                 history_path: Path = HISTORY_FILE,
                 current_path: Path = CURRENT_FILE):
    now = time.time()
    state = load_state(state_path)
    usage = load_usage(usage_path)
    history = load_history(history_path)
    return Group(
        _header(state, now),
        _progress(state),
        _running(now, current_path),
        _segments(history),
        _quota(usage, now),
        _resets(usage, now),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build dashboard")
    parser.add_argument("--once", action="store_true",
                        help="render one frame and exit")
    args = parser.parse_args()
    console = Console()
    console.print(render_frame())
    if not args.once:
        console.print(_dim("(live mode arrives in Task 3)"))


if __name__ == "__main__":
    main()
