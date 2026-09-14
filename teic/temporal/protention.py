"""One-tick-ahead prediction buffer holding explicit timestamped forecasts.

`ProtentionEntry` is a timestamped snapshot of the daemon's predictions:
the predicted tick timing latency (dt_real forecast via ForwardModel) and
a naive one-step carry-forward of the current interoceptive register vector
(the EWMA filter's current mean is its best forecast for the next observation
absent new evidence).

`ProtentionBuffer` is a single-slot holder for one such prediction at a time.
Phase 3's protention horizon is exactly one tick ahead; a multi-step horizon
is a future extension, not a current gap. The single-slot semantics allow
the heartbeat loop to always know what the daemon predicted it would do next,
for later comparison against what actually happened (closing the prediction
error loop).
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ProtentionEntry(BaseModel):
    """Explicit timestamped one-step-ahead prediction.

    Holds what the daemon predicted about its own next tick: timing latency
    and the full interoceptive state vector. Built once per tick by the
    heartbeat loop, held in ProtentionBuffer until the next tick observation
    arrives, then compared to update prediction_error in the register vector.
    """

    made_at_tick_id: int
    """Tick id when this prediction was made."""

    predicted_at: datetime
    """Wall-clock timestamp when this prediction was made."""

    predicted_dt_real: float
    """Forecasted latency for the next tick (seconds), from ForwardModel."""

    predicted_registers: dict[str, float]
    """Predicted interoceptive state vector for the next tick.

    Naive one-step carry-forward of the current tick's inferred RegisterState
    mean (not the variance). The EWMA filter's current estimate already is
    its best forecast for the next observation absent new evidence, so no
    separate per-channel forecaster is needed.
    """


class ProtentionBuffer:
    """Single-slot buffer for one-tick-ahead predictions.

    Holds exactly zero or one `ProtentionEntry` at a time. `push()` replaces
    any existing entry; `pop()` returns and clears it. This is not a ring
    buffer or queue -- it is a single predictive slot. Phase 3's protention
    horizon is exactly one tick; longer horizons are future extensions.
    """

    def __init__(self) -> None:
        """Initialize with no pending prediction."""
        self._pending: ProtentionEntry | None = None

    def push(self, entry: ProtentionEntry) -> None:
        """Store a prediction, replacing any previous one.

        Args:
            entry: The prediction to store.
        """
        self._pending = entry

    def pop(self) -> ProtentionEntry | None:
        """Retrieve and clear the stored prediction, if any.

        Returns:
            The stored entry, or None if no prediction is pending.
        """
        result = self._pending
        self._pending = None
        return result
