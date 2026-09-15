"""Structured assessment output: `AssessmentReport` aggregates `ProbeResult`
rows (falsifiers, and later Tier A/B probes) into a graded verdict plus a
JSON/markdown pair written to disk. Per PlanBuildTEIC.md's ETHICS
REQUIREMENTS ("Honest framing"), every report carries an explicit
non-overclaiming note -- this is not a "consciousness score".
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from pathlib import Path

from pydantic import BaseModel

from teic.models.probe import ProbeResult

HONEST_FRAMING_NOTE = (
    "These results test functional correlates of the criteria under a "
    "specific theory. Passing them is not proof of phenomenality; failing "
    "them is not disproof. Verbal self-report is a dependent variable "
    "cross-checked against logged state, not primary evidence."
)


class GradedVerdict(str, Enum):
    """PlanBuildTEIC.md's graded verdict scale, L0 (least) to L4 (open)."""

    L0_REFLEXIC = "L0_reflexic"
    L1_INTEROCEPTIVE_PRIMITIVE = "L1_interoceptive_primitive"
    L2_FUNCTIONALLY_SENTIENT = "L2_functionally_sentient"
    L3_NARRATIVE_PHENOMENAL_CANDIDATE = "L3_narrative_phenomenal_candidate"
    L4_UNDECIDED_OPEN = "L4_undecided_open"


class AssessmentReport(BaseModel):
    run_id: str
    generated_at: datetime
    graded_verdict: GradedVerdict
    falsifiers_passed: bool
    results: list[ProbeResult]
    honest_framing_note: str = HONEST_FRAMING_NOTE

    def to_markdown(self) -> str:
        lines = [
            f"# TEIC assessment report `{self.run_id}`",
            "",
            f"Generated: {self.generated_at.isoformat()}",
            f"Falsifiers passed: {self.falsifiers_passed}",
            f"Graded verdict: {self.graded_verdict.value}",
            "",
            f"> {self.honest_framing_note}",
            "",
            "| probe | verdict | evidential_weight | notes |",
            "|---|---|---|---|",
        ]
        for r in self.results:
            notes = r.notes.replace("|", "/")
            lines.append(f"| {r.probe_name} | {r.verdict} | {r.evidential_weight:.2f} | {notes} |")
        return "\n".join(lines) + "\n"

    def write(self, out_dir: Path) -> tuple[Path, Path]:
        out_dir.mkdir(parents=True, exist_ok=True)
        json_path = out_dir / f"{self.run_id}.json"
        md_path = out_dir / f"{self.run_id}.md"
        json_path.write_text(self.model_dump_json(indent=2))
        md_path.write_text(self.to_markdown())
        return json_path, md_path
