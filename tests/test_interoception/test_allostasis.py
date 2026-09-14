from __future__ import annotations

from teic.interoception.allostasis import AllostaticForecaster
from teic.interoception.inference import ChannelInference


def test_forecast_is_zero_for_never_observed_channel() -> None:
    inference = ChannelInference()
    forecaster = AllostaticForecaster(inference, horizon_ticks=5)
    assert forecaster.forecast("budget_reserve") == [0.0] * 5


def test_forecast_is_flat_on_first_observation() -> None:
    inference = ChannelInference()
    inference.update("budget_reserve", 0.8)
    forecaster = AllostaticForecaster(inference, horizon_ticks=4)
    trajectory = forecaster.forecast("budget_reserve")
    # No trend observed yet (this is the only data point) -- flat at the
    # current mean, not a fabricated slope.
    assert trajectory == [0.8, 0.8, 0.8, 0.8]


def test_forecast_extrapolates_a_falling_trend() -> None:
    inference = ChannelInference()
    forecaster = AllostaticForecaster(inference, horizon_ticks=3)

    inference.update("budget_reserve", 1.0)
    forecaster.forecast("budget_reserve")  # seeds _last_mean at 1.0

    inference.update("budget_reserve", 0.9)  # real EWMA drop
    trajectory = forecaster.forecast("budget_reserve")
    mean, _ = inference.current("budget_reserve")  # type: ignore[misc]
    trend = mean - 1.0
    assert trajectory == [mean + trend * step for step in (1, 2, 3)]
    assert trend < 0.0
    assert trajectory[-1] < trajectory[0]


def test_anticipatory_pressure_fires_before_current_value_crosses_threshold() -> None:
    inference = ChannelInference()
    forecaster = AllostaticForecaster(inference, horizon_ticks=10)

    # Establish a sharply falling budget_reserve trend via consecutive
    # real EWMA updates, matching how ChannelInference is actually driven
    # from real per-tick raw samples.
    inference.update("budget_reserve", 1.0)
    forecaster.forecast("budget_reserve")
    inference.update("budget_reserve", 0.3)

    current_value, _ = inference.current("budget_reserve")  # type: ignore[misc]
    threshold = 0.1
    # The current inferred value has not yet crossed the danger threshold.
    assert current_value > threshold

    pressure = forecaster.anticipatory_pressure("budget_reserve", threshold=threshold)
    # But the forecast trajectory, extrapolating the real observed drop,
    # predicts a future crossing -- the pre-emptive signal is nonzero
    # while the present-tick value alone would still look safe.
    assert pressure > 0.0


def test_anticipatory_pressure_is_zero_when_no_crossing_is_forecast() -> None:
    inference = ChannelInference()
    forecaster = AllostaticForecaster(inference, horizon_ticks=5)
    inference.update("budget_reserve", 1.0)
    forecaster.forecast("budget_reserve")
    inference.update("budget_reserve", 1.0)  # flat, no trend
    assert forecaster.anticipatory_pressure("budget_reserve", threshold=0.1) == 0.0
