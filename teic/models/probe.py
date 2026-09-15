from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel

Verdict = Literal["pass", "fail", "inconclusive"]


class ProbeResult(BaseModel):
    run_id: str
    probe_name: str
    seed: int
    verdict: Verdict
    metrics: dict[str, float]
    evidence: dict[str, Any]
    thresholds_used: dict[str, float]
    # Discounts how much the probe's own design pre-supposes the result it
    # measures -- 1.0 is undiscounted, lower values flag a probe that was
    # "designed in" per PlanBuildTEIC.md's ban on an unweighted consciousness score.
    evidential_weight: float = 1.0
    notes: str = ""
