"""Tests for ForwardModel."""

import pytest

from teic.embodiment.forward_model import ForwardModel


class TestForwardModel:
    """Test the adaptive timing latency prediction model."""

    def test_perfect_predictions_converge_multiplier_to_one(self) -> None:
        """A model repeatedly observing actual == nominal should converge near 1.0."""
        model = ForwardModel()
        nominal_dt = 0.1

        # Run for multiple ticks with perfect predictions
        errors = []
        for _ in range(20):
            predicted = model.predict_dt_real(nominal_dt)
            actual = nominal_dt  # Perfect match
            error = model.observe(actual, nominal_dt, predicted)
            errors.append(error)

        # Multiplier should converge near 1.0
        assert abs(model._multiplier - 1.0) < 0.01
        # Errors should be consistently near 0.0
        assert all(e < 0.01 for e in errors[-5:])  # Last 5 errors especially small

    def test_step_change_produces_spike_then_decay(self) -> None:
        """A 3x timing change should produce a large error spike followed by adaptation."""
        model = ForwardModel()
        nominal_dt = 0.1

        # Establish stable regime
        for _ in range(10):
            predicted = model.predict_dt_real(nominal_dt)
            actual = nominal_dt
            model.observe(actual, nominal_dt, predicted)

        # Verify multiplier is near 1.0
        assert abs(model._multiplier - 1.0) < 0.01

        # Now observe a 3x change
        predicted_before_change = model.predict_dt_real(nominal_dt)
        actual_at_change = 3.0 * nominal_dt
        error_at_change = model.observe(actual_at_change, nominal_dt, predicted_before_change)

        # Error should be large (the spike)
        assert error_at_change > 1.0

        # Now observe several more ticks at the 3x regime
        errors_after_change = []
        for _ in range(10):
            predicted = model.predict_dt_real(nominal_dt)
            actual = 3.0 * nominal_dt
            error = model.observe(actual, nominal_dt, predicted)
            errors_after_change.append(error)

        # First error in new regime should be significantly smaller than spike
        # (the adaptation / decay)
        assert errors_after_change[0] < error_at_change * 0.5

        # Multiplier should have adapted toward 3.0
        assert model._multiplier > 2.0

    def test_clamping_of_error(self) -> None:
        """Error should be clamped at ERROR_CLAMP_MAX."""
        model = ForwardModel()

        # Force a very large mismatch
        nominal_dt = 0.1
        predicted_dt_real = 0.1
        actual_dt_real = 100.0  # 1000x too large

        error = model.observe(actual_dt_real, nominal_dt, predicted_dt_real)

        # Error should be clamped
        from teic.embodiment.forward_model import ERROR_CLAMP_MAX
        assert error <= ERROR_CLAMP_MAX
