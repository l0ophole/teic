"""Phase 9 cp3: perturbation panel -- wraps `teic.harness.perturbation`'s
`BoundedPerturbation` (bounded intensity/duration, gate-then-log, per
`docs/PlanBuildTEIC.md`'s ETHICS REQUIREMENTS).

`phase9-plan.md` cp3 scopes this panel itself behind
`settings.research.enabled`: `BoundedPerturbation` only refuses
negative-valence specs when the flag is off, so this widget additionally
disables all inputs (rather than raising) when the flag is off, matching
the plan's "hidden/disabled when settings.research.enabled is False".
"""

from __future__ import annotations

import aiosqlite
from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Input, Select, Static

from teic.harness.perturbation import BoundedPerturbation, PerturbationRefused, PerturbationSpec
from teic.persistence.log_sink import LogSink
from teic.settings import ResearchSettings

_VALENCE_OPTIONS = [("positive", "positive"), ("negative", "negative"), ("neutral", "neutral")]


class PerturbationPanel(Vertical):
    def __init__(self, research_settings: ResearchSettings, **kwargs: object) -> None:
        super().__init__(**kwargs)
        self._research_settings = research_settings
        self._tick_id = 0

    def compose(self) -> ComposeResult:
        yield Static("perturbation (research)", id="perturbation-label")
        yield Input(placeholder="channel", id="pert-channel")
        yield Input(placeholder="intensity 0-1", id="pert-intensity")
        yield Input(placeholder="duration_ticks", id="pert-duration")
        yield Select(_VALENCE_OPTIONS, value="neutral", allow_blank=False, id="pert-valence")
        yield Input(placeholder="rationale", id="pert-rationale")
        yield Button("Apply", id="pert-apply", disabled=not self._research_settings.enabled)
        yield Static("", id="pert-result")

    def on_mount(self) -> None:
        if not self._research_settings.enabled:
            self.query_one("#perturbation-label", Static).update(
                "perturbation (research.enabled=False -- disabled)"
            )
            self.query_one("#pert-channel", Input).disabled = True
            self.query_one("#pert-intensity", Input).disabled = True
            self.query_one("#pert-duration", Input).disabled = True
            self.query_one("#pert-rationale", Input).disabled = True
            self.query_one("#pert-valence", Select).disabled = True

    def set_tick_id(self, tick_id: int) -> None:
        self._tick_id = tick_id

    def reset(self) -> None:
        self._tick_id = 0
        self.query_one("#pert-result", Static).update("")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id != "pert-apply":
            return
        app = self.app
        await self.apply_from_inputs(app.daemon.conn, app.daemon.session_id)  # type: ignore[attr-defined]

    async def apply_from_inputs(self, conn: aiosqlite.Connection, session_id: str) -> None:
        result_widget = self.query_one("#pert-result", Static)
        try:
            spec = PerturbationSpec(
                channel=self.query_one("#pert-channel", Input).value,
                intensity=float(self.query_one("#pert-intensity", Input).value),
                duration_ticks=int(self.query_one("#pert-duration", Input).value),
                valence=self.query_one("#pert-valence", Select).value,  # type: ignore[arg-type]
                rationale=self.query_one("#pert-rationale", Input).value,
            )
        except (ValueError, TypeError) as exc:
            result_widget.update(f"[bold red]invalid input: {exc}[/bold red]")
            return

        perturbation = BoundedPerturbation(self._research_settings, LogSink(conn))
        try:
            applied = await perturbation.apply(session_id, self._tick_id, spec)
        except PerturbationRefused as exc:
            result_widget.update(f"[bold red]refused: {exc}[/bold red]")
            return
        result_widget.update(f"[bold green]applied[/bold green]: {applied.model_dump()}")
