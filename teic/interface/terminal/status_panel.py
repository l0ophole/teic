"""Phase 9 cp2: status panel -- valence/arousal sparklines, tick tempo,
viability budget reserve, and a workspace-ignition-event feed. v1 scope
only (`phase9-plan.md`): memory/goal detail and full telemetry deferred.

Fed exclusively by `TeicDaemon.TickSnapshot` via `update_snapshot()` --
no direct database polling, matching the daemon's `add_tick_listener()`
seam.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Sparkline, Static

if TYPE_CHECKING:
    from teic.daemon import TickSnapshot

_HISTORY_LEN = 60
_IGNITION_FEED_LEN = 8


class StatusPanel(Vertical):
    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._valence_history: deque[float] = deque(maxlen=_HISTORY_LEN)
        self._arousal_history: deque[float] = deque(maxlen=_HISTORY_LEN)
        self._ignition_feed: deque[str] = deque(maxlen=_IGNITION_FEED_LEN)

    def compose(self) -> ComposeResult:
        yield Static("(waiting for first tick...)", id="status-summary")
        yield Static("valence")
        yield Sparkline([], id="valence-spark")
        yield Static("arousal")
        yield Sparkline([], id="arousal-spark")
        yield Static("ignition feed", id="ignition-feed-label")
        yield Static("", id="ignition-feed")

    def update_snapshot(self, snapshot: "TickSnapshot") -> None:
        self._valence_history.append(snapshot.valence)
        self._arousal_history.append(snapshot.arousal)
        self.query_one("#valence-spark", Sparkline).data = list(self._valence_history)
        self.query_one("#arousal-spark", Sparkline).data = list(self._arousal_history)

        summary = (
            f"tick {snapshot.tick_id}  tempo {snapshot.tempo_hz:.2f}Hz  "
            f"budget ${snapshot.budget_reserve_usd:.4f}  "
            f"pending {snapshot.pending_input_count}"
        )
        self.query_one("#status-summary", Static).update(summary)

        if snapshot.ignited:
            self._ignition_feed.appendleft(
                f"tick {snapshot.tick_id}: {snapshot.winner_source}"
            )
            self.query_one("#ignition-feed", Static).update("\n".join(self._ignition_feed))

    def reset(self) -> None:
        self._valence_history.clear()
        self._arousal_history.clear()
        self._ignition_feed.clear()
        self.query_one("#valence-spark", Sparkline).data = []
        self.query_one("#arousal-spark", Sparkline).data = []
        self.query_one("#ignition-feed", Static).update("")
        self.query_one("#status-summary", Static).update("(waiting for first tick...)")
