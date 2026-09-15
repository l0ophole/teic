"""Phase 9 cp2: manual controls -- pause/resume and session-reset (v1
scope; tick-rate adjustment, forced consolidation, injection, self-model
editor, and memory inspector are deferred to v2 per `phase9-plan.md`).

The key bindings themselves live on `TeicApp` (Textual requires actions to
be bound on an `App`/`Screen`/focused `Widget`); this module supplies the
status bar widget those actions update, plus a paused-state predicate so
`TeicApp` doesn't need to know the label text.
"""

from __future__ import annotations

from textual.widgets import Static

PAUSE_RESUME_KEY = "p"
RESET_KEY = "ctrl+r"
QUIT_KEY = "q"


class ControlsBar(Static):
    """Single-line status/hint bar: current run state plus key hints."""

    def __init__(self, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._paused = False

    def set_paused(self, paused: bool) -> None:
        self._paused = paused
        self._refresh_text()

    def _refresh_text(self) -> None:
        state = "[bold yellow]PAUSED[/bold yellow]" if self._paused else "[bold green]RUNNING[/bold green]"
        self.update(
            f"{state}  |  [b]{PAUSE_RESUME_KEY}[/b] pause/resume  "
            f"[b]{RESET_KEY}[/b] reset session  [b]{QUIT_KEY}[/b] quit"
        )

    def on_mount(self) -> None:
        self._refresh_text()
