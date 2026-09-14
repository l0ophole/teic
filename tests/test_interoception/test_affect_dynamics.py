from __future__ import annotations

from datetime import UTC, datetime

from teic.interoception.affect_dynamics import AffectDynamics
from teic.models.registers import REGISTER_CHANNELS, RegisterState

_TS = datetime.now(UTC)


def _registers(**overrides: float) -> RegisterState:
    values = dict.fromkeys(REGISTER_CHANNELS, 0.0)
    values["budget_reserve"] = 1.0
    values.update(overrides)
    return RegisterState(
        **values,
        variances=dict.fromkeys(REGISTER_CHANNELS, 0.0),
        tick_id=1,
        ts=_TS,
    )


def test_high_budget_low_burn_gives_positive_valence() -> None:
    dynamics = AffectDynamics()
    registers = _registers(budget_reserve=1.0, burn_rate=0.0, epistemic_tension=0.0)
    valence, _ = dynamics.update(registers)
    assert valence > 0.0


def test_low_budget_high_burn_gives_negative_valence() -> None:
    dynamics = AffectDynamics()
    registers = _registers(budget_reserve=0.0, burn_rate=1.0, epistemic_tension=1.0)
    valence, _ = dynamics.update(registers)
    assert valence < 0.0


def test_high_error_and_volatility_gives_higher_arousal_than_calm() -> None:
    calm = _registers(prediction_error=0.0, surprise_volatility=0.0)
    strained = _registers(prediction_error=1.0, surprise_volatility=1.0, latency_strain=1.0)

    calm_dynamics = AffectDynamics()
    strained_dynamics = AffectDynamics()
    _, calm_arousal = calm_dynamics.update(calm)
    _, strained_arousal = strained_dynamics.update(strained)

    assert strained_arousal > calm_arousal


def test_repeated_identical_input_smooths_rather_than_jumping() -> None:
    dynamics = AffectDynamics()
    registers = _registers(budget_reserve=1.0, burn_rate=1.0)  # raw_valence == 0.0 on seed
    dynamics.update(registers)  # seeds state at raw value

    strained = _registers(budget_reserve=0.0, burn_rate=1.0, epistemic_tension=1.0)
    first_valence, _ = dynamics.update(strained)
    raw_valence = AffectDynamics._raw_valence(strained)

    # EWMA smoothing: the first exposure to a new raw value should not jump
    # all the way to that raw value.
    assert first_valence != raw_valence
    assert abs(first_valence - raw_valence) < abs(0.0 - raw_valence)
