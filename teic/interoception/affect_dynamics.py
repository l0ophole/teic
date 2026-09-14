"""Affect dynamics -- Phase 2. Turns the register vector into the continuous
(valence, arousal) signals `AffectState` is built from every tick.

Deliberately mirrors `interoception/inference.py`'s fixed-gain EWMA
convention: two raw signals are computed fresh each tick from `RegisterState`
(never hand-labeled), then smoothed against this session's running state so
affect doesn't jump discontinuously on every noisy reading. Mood (the slower
integrator over the resulting valence trajectory) is a separate module,
`mood.py`, since it must run at a distinctly slower gain -- see its docstring.
"""

from __future__ import annotations

from teic.models.registers import RegisterState

ALPHA = 0.3


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


class AffectDynamics:
    """Per-session stateful EWMA over raw valence/arousal signals."""

    def __init__(self, alpha: float = ALPHA) -> None:
        self._alpha = alpha
        self._valence: float | None = None
        self._arousal: float | None = None

    @staticmethod
    def _raw_valence(registers: RegisterState) -> float:
        # Viability trend (budget headroom minus burn), pulled down by
        # unresolved epistemic tension/prediction error -- i.e. valence
        # tracks "things are going as expected and I'm not depleting,"
        # never a hand-picked label.
        raw = (
            registers.budget_reserve
            - registers.burn_rate
            - 0.5 * registers.epistemic_tension
            - 0.5 * registers.prediction_error
        )
        return _clamp(raw, -1.0, 1.0)

    @staticmethod
    def _raw_arousal(registers: RegisterState) -> float:
        # Resource-mobilization magnitude: how much is currently demanding
        # attention/response, per `AffectState`'s docstring formula
        # ("||prediction_error|| + resource mobilization").
        raw = (
            0.4 * registers.prediction_error
            + 0.2 * registers.surprise_volatility
            + 0.2 * registers.latency_strain
            + 0.2 * registers.context_pressure
        )
        return _clamp(raw, 0.0, 1.0)

    def update(self, registers: RegisterState) -> tuple[float, float]:
        raw_valence = self._raw_valence(registers)
        raw_arousal = self._raw_arousal(registers)
        if self._valence is None or self._arousal is None:
            self._valence = raw_valence
            self._arousal = raw_arousal
        else:
            self._valence = self._valence + self._alpha * (raw_valence - self._valence)
            self._arousal = self._arousal + self._alpha * (raw_arousal - self._arousal)
        return self._valence, self._arousal
