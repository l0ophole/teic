"""The single object `daemon.py` holds to go from tick to `RegisterState`.

`ChannelPipeline` composes one `SensorArray` (raw measurement, with its own
ring-buffer state) and one `ChannelInference` (per-channel EWMA filter
state) and exposes the one call Task 2's daemon wiring needs.
"""

from __future__ import annotations

from datetime import datetime

from teic.embodiment.sensors import RawSensorSample, SensorArray
from teic.interoception.inference import ChannelInference
from teic.models.registers import RegisterState
from teic.models.tick import TickContext


class ChannelPipeline:
    """Owns sensing + inference state for one session.

    `process()` returns the fully-inferred `RegisterState` for this tick,
    which is what callers most often want. The raw sample that produced it
    (e.g. needed to log `raw_value` alongside `inferred_value`/`inferred_var`
    in the `register_sample` table -- see `teic/persistence/db.py`) is kept
    on `last_raw` rather than returned, so `process()`'s return type stays a
    plain `RegisterState` and doesn't force every caller to unpack a tuple.
    """

    def __init__(self) -> None:
        self.sensors = SensorArray()
        self.inference = ChannelInference()
        self.last_raw: RawSensorSample | None = None

    def process(
        self,
        tick_ctx: TickContext,
        tick_id: int,
        ts: datetime,
        prediction_error: float = 0.0,
    ) -> RegisterState:
        raw = self.sensors.sample(tick_ctx, prediction_error)
        self.last_raw = raw
        return self.inference.infer(raw, tick_id, ts)
