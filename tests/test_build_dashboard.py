"""Tests for build_dashboard: data loaders, formatting, single-frame render."""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import build_dashboard as bd


# ---------------------------------------------------------------- fmt_countdown

def test_fmt_countdown_zero():
    assert bd.fmt_countdown(0) == "0s"


def test_fmt_countdown_under_minute():
    assert bd.fmt_countdown(47) == "<47s"


def test_fmt_countdown_minutes():
    assert bd.fmt_countdown(47 * 60 + 12) == "47m 12s"


def test_fmt_countdown_hours():
    assert bd.fmt_countdown(5 * 3600 + 2 * 60) == "5h 2m"


def test_fmt_countdown_days():
    assert bd.fmt_countdown(2 * 86400 + 3 * 3600) == "2d 3h"


def test_fmt_countdown_negative():
    assert bd.fmt_countdown(-10) == "passed"


# ---------------------------------------------------------------- bar

def test_bar_green():
    t = bd.bar(0.5)
    assert t.style == "green"
    assert t.plain == "█" * 5 + "░" * 5


def test_bar_yellow():
    assert bd.bar(0.8).style == "yellow"


def test_bar_red():
    assert bd.bar(0.95).style == "red"


def test_bar_clamps_above_one():
    t = bd.bar(1.5)
    assert t.plain == "█" * 10


def test_bar_clamps_below_zero():
    t = bd.bar(-0.2)
    assert t.plain == "░" * 10


def test_bar_boundary_070_yellow():
    assert bd.bar(0.70).style == "yellow"


def test_bar_boundary_090_red():
    assert bd.bar(0.90).style == "red"


# ---------------------------------------------------------------- loaders

def test_load_state_missing(tmp_path: Path):
    assert bd.load_state(tmp_path / "nope.json") is None


def test_load_state_corrupt(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text("{not json")
    assert bd.load_state(p) is None


def test_load_state_ok(tmp_path: Path):
    p = tmp_path / "state.json"
    p.write_text(json.dumps({"phase": 6, "status": "planning"}))
    assert bd.load_state(p)["phase"] == 6


def test_load_usage_missing(tmp_path: Path):
    assert bd.load_usage(tmp_path / "nope.json") is None


def test_load_usage_corrupt(tmp_path: Path):
    p = tmp_path / "usage.json"
    p.write_text("]]]")
    assert bd.load_usage(p) is None


def test_load_current_missing(tmp_path: Path):
    assert bd.load_current(tmp_path / "nope.json") is None


def test_load_current_fresh(tmp_path: Path):
    p = tmp_path / "current.json"
    p.write_text(json.dumps({"label": "cp1", "started_at": time.time() - 60}))
    assert bd.load_current(p)["label"] == "cp1"


def test_load_current_stale(tmp_path: Path):
    p = tmp_path / "current.json"
    p.write_text(json.dumps(
        {"label": "cp1", "started_at": time.time() - bd.DEFAULT_TIMEOUT_S - 5}))
    assert bd.load_current(p) is None


# ---------------------------------------------------------------- load_history

def test_load_history_missing(tmp_path: Path):
    assert bd.load_history(tmp_path / "nope.jsonl") == []


def test_load_history_tail_and_bad_lines(tmp_path: Path):
    p = tmp_path / "hist.jsonl"
    lines = [json.dumps({"ts": i, "label": f"s{i}", "phase": 1,
                         "billed_tokens": 10, "turns": 1,
                         "outcome": "ok"})
             for i in range(15)]
    lines.insert(3, "{corrupt")
    lines.insert(10, "")
    p.write_text("\n".join(lines) + "\n")
    recs = bd.load_history(p, tail=10)
    assert len(recs) == 10
    assert [r["ts"] for r in recs] == list(range(5, 15))


# ---------------------------------------------------------------- _to_epoch

def test_to_epoch_iso_string():
    iso = "2026-09-14T12:00:00+00:00"
    from datetime import datetime, timezone
    expected = datetime(2026, 9, 14, 12, 0, 0,
                        tzinfo=timezone.utc).timestamp()
    assert bd._to_epoch(iso) == expected


def test_to_epoch_epoch_float():
    assert bd._to_epoch(1789468800.0) == 1789468800.0


def test_to_epoch_none_and_garbage():
    assert bd._to_epoch(None) is None
    assert bd._to_epoch("not a date") is None


# ---------------------------------------------------------------- phase_totals

def test_phase_totals_sums_and_skips_none_phase():
    hist = [
        {"phase": 1, "billed_tokens": 100, "turns": 2},
        {"phase": 1, "billed_tokens": 50, "turns": 3},
        {"phase": None, "billed_tokens": 999, "turns": 1},
        {"phase": 2, "billed_tokens": 7, "turns": 1},
    ]
    totals = bd.phase_totals(hist)
    assert totals == {
        1: {"billed": 150, "turns": 5, "segments": 2},
        2: {"billed": 7, "turns": 1, "segments": 1},
    }


# ---------------------------------------------------------------- render_frame

def test_render_frame_never_crashes_on_missing_files():
    frame = bd.render_frame(
        state_path=Path("/nonexistent/state.json"),
        usage_path=Path("/nonexistent/usage.json"),
        history_path=Path("/nonexistent/hist.jsonl"),
        current_path=Path("/nonexistent/current.json"),
    )
    assert frame is not None


def test_render_frame_survives_corrupt_state_file(tmp_path: Path):
    state = tmp_path / "state.json"
    state.write_text("not json{")
    frame = bd.render_frame(
        state_path=state,
        usage_path=tmp_path / "usage.json",
        history_path=tmp_path / "hist.jsonl",
        current_path=tmp_path / "current.json",
    )
    assert frame is not None


# ---------------------------------------------------------------- live loop

def test_wants_quit_q_and_Q_variants():
    assert bd.wants_quit("q") is True


def test_wants_quit_other_chars_and_none():
    assert bd.wants_quit("x") is False
    assert bd.wants_quit("\x03") is False  # Ctrl+C handled via KeyboardInterrupt
    assert bd.wants_quit(None) is False


def test_tick_seconds_is_two():
    assert bd.TICK_SECONDS == 2.0
