from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

REGISTER_CHANNELS: tuple[str, ...] = (
    "context_pressure",
    "budget_reserve",
    "burn_rate",
    "prediction_error",
    "surprise_volatility",
    "effector_integrity",
    "latency_strain",
    "epistemic_tension",
    "goal_gradient",
    "memory_fragmentation",
    "social_contact",
)


class RegisterState(BaseModel):
    """The 11-channel homeostatic vector.

    Never hand-authored: produced by interoception/inference.py from noisy
    sensor samples via a generative model. `variances` carries the posterior
    uncertainty per channel, parallel to the point estimates, so calibration
    can be checked (e.g. by the harness) rather than trusting point values alone.
    """

    context_pressure: float
    budget_reserve: float
    burn_rate: float
    prediction_error: float
    surprise_volatility: float
    effector_integrity: float
    latency_strain: float
    epistemic_tension: float
    goal_gradient: float
    memory_fragmentation: float
    social_contact: float
    variances: dict[str, float]
    tick_id: int
    ts: datetime

    def as_dict(self) -> dict[str, float]:
        return {ch: getattr(self, ch) for ch in REGISTER_CHANNELS}
