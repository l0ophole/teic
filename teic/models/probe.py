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
    notes: str = ""
