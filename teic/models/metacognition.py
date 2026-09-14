from __future__ import annotations

from pydantic import BaseModel


class ConfidenceEstimate(BaseModel):
    """Second-order calibrated confidence (0..1).

    Derived from forward-model prediction error (lower error -> higher
    confidence) and self-model stability (how much the self-model changed
    this tick -- a self-model in flux is a self-model not yet trustworthy
    to act on). Consumed by `ModulationCompute` and the reportability gate
    so low confidence measurably raises retrieval/exploration and high
    confidence permits committing to action, rather than staying a number
    nothing reads.
    """

    confidence: float
    source_signals: dict[str, float]
    tick_id: int
