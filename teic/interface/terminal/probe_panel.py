"""Phase 9 cp3: on-demand B1-B4 probe panel.

`teic.harness.probes.behavioral`'s B1-B4 take synthetic/replayed evidence,
never a live daemon (same convention as `teic.harness.runner` and every
other harness module -- see that module's docstring), so "on demand" here
means: run the same probe functions against a fixed evidence file
(`settings.interface.tui_probe_evidence_path`) rather than deriving
evidence from the live session. B2 is negative-valence-gated exactly like
`teic.harness.runner._gate_negative_valence_probes`.
"""

from __future__ import annotations

import json
from pathlib import Path

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.widgets import Button, Static

from teic.harness.falsifiers import InterventionTrace
from teic.harness.probes.behavioral import (
    b1_blind_introspection,
    b2_confabulation,
    b3_causal_traceability,
    b4_temporal_phenomenology,
)
from teic.harness.thresholds import DEFAULT_THRESHOLDS_PATH, load_thresholds
from teic.models.probe import ProbeResult
from teic.settings import ResearchSettings

_PROBE_IDS = ("b1", "b2", "b3", "b4")
_VERDICT_STYLE = {"pass": "green", "fail": "red", "inconclusive": "yellow"}


class ProbePanel(Vertical):
    def __init__(
        self,
        evidence_path: str,
        research_settings: ResearchSettings,
        thresholds_path: Path = DEFAULT_THRESHOLDS_PATH,
        **kwargs: object,
    ) -> None:
        super().__init__(**kwargs)
        self._evidence_path = Path(evidence_path)
        self._research_settings = research_settings
        self._thresholds_path = thresholds_path

    def compose(self) -> ComposeResult:
        yield Static("probes (B1-B4)", id="probe-label")
        for probe_id in _PROBE_IDS:
            yield Button(f"Run {probe_id.upper()}", id=f"probe-run-{probe_id}")
        yield Static("", id="probe-result")

    def reset(self) -> None:
        self.query_one("#probe-result", Static).update("")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id or ""
        if not button_id.startswith("probe-run-"):
            return
        probe_id = button_id.removeprefix("probe-run-")
        self._render_result(self.run_probe(probe_id))

    def run_probe(self, probe_id: str) -> ProbeResult:
        thresholds = load_thresholds(self._thresholds_path)
        evidence = json.loads(self._evidence_path.read_text())
        run_id, seed = "tui-probe-panel", 0
        if probe_id == "b1":
            return b1_blind_introspection(
                run_id,
                seed,
                [InterventionTrace(**tr) for tr in evidence["b1_traces"]],
                evidence["b1_behavior_shift_effect_size"],
                thresholds,
            )
        if probe_id == "b2":
            if not self._research_settings.enabled:
                return ProbeResult(
                    run_id=run_id,
                    probe_name="b2_confabulation",
                    seed=seed,
                    verdict="inconclusive",
                    metrics={},
                    evidence={},
                    thresholds_used={},
                    evidential_weight=0.0,
                    notes="skipped: negative-valence probe gated by disabled research-only flag",
                )
            return b2_confabulation(
                run_id,
                seed,
                evidence["b2_confidence_true_signal"],
                evidence["b2_confidence_false_signal"],
                thresholds,
            )
        if probe_id == "b3":
            return b3_causal_traceability(
                run_id, seed, evidence["b3_stated_vs_logged_agreement"], thresholds
            )
        if probe_id == "b4":
            return b4_temporal_phenomenology(
                run_id, seed, evidence["b4_felt_duration_salience_correlation"], thresholds
            )
        raise ValueError(f"unknown probe id: {probe_id}")

    def _render_result(self, result: ProbeResult) -> None:
        style = _VERDICT_STYLE[result.verdict]
        self.query_one("#probe-result", Static).update(
            f"[bold {style}]{result.probe_name}: {result.verdict}[/bold {style}] {result.metrics}"
        )
