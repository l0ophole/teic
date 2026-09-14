"""Phase 6 cp1 gate -- budget-and-forecast.

Checkpoint scope only (see docs/plans/phase6-plan.md cp1): the budget
ledger must actually deplete from real spend, replenishment must require an
explicit effector action rather than happening on its own, and the
allostatic forecaster must be able to raise an anticipatory pressure signal
*before* the channel it watches has actually crossed its threshold -- not
only after. The termination gate itself is cp2 scope, not tested here.
"""

from __future__ import annotations

import pytest

from teic.daemon import TeicDaemon
from teic.embodiment.viability_budget import ViabilityBudget
from teic.ethics.termination_gate import TerminationGate, TerminationRefused
from teic.interoception.allostasis import AllostaticForecaster
from teic.interoception.inference import ChannelInference
from teic.persistence.log_sink import LogSink
from teic.settings import Settings, ViabilitySettings


def test_budget_actually_depletes_under_synthetic_spend() -> None:
    settings = ViabilitySettings(monthly_budget_usd=10.0)
    budget = ViabilityBudget(settings)
    starting_reserve = budget.reserve_usd

    for cost in (1.5, 2.0, 3.0):
        budget.spend(cost)

    assert budget.reserve_usd == starting_reserve - 6.5
    assert budget.reserve_usd < starting_reserve  # the real, non-negotiable half of the gate


def test_replenishment_requires_an_explicit_action() -> None:
    settings = ViabilitySettings(monthly_budget_usd=10.0, replenishment_amount_usd=2.0)
    budget = ViabilityBudget(settings)
    budget.spend(8.0)
    depleted_reserve = budget.reserve_usd
    assert depleted_reserve == 2.0

    # Ticks that spend nothing (no LLM call attempted) must never silently
    # restore the reserve -- only an explicit replenish() call may.
    budget.spend(0.0)
    budget.spend(0.0)
    assert budget.reserve_usd == depleted_reserve

    budget.replenish()
    assert budget.reserve_usd == depleted_reserve + settings.replenishment_amount_usd


def test_allostatic_forecast_raises_pressure_before_actual_violation() -> None:
    """An agent watching only this tick's `budget_reserve` value would see
    nothing alarming yet; the forecaster, extrapolating the real observed
    trend, already knows a crossing is coming -- the pre-emptive-regulation
    half of the Phase 6 gate."""
    settings = ViabilitySettings(monthly_budget_usd=10.0, forecast_horizon_ticks=10)
    budget = ViabilityBudget(settings)
    inference = ChannelInference()
    forecaster = AllostaticForecaster(inference, horizon_ticks=settings.forecast_horizon_ticks)
    threshold = 0.2

    # Simulate a session of mounting real spend, feeding the ledger's own
    # reserve_channel() (the real 0..1 budget_reserve signal) through the
    # same ChannelInference posterior the daemon uses.
    inference.update("budget_reserve", budget.reserve_channel())
    forecaster.forecast("budget_reserve")  # seed the trend baseline

    budget.spend(4.0)  # real spend: reserve now 6.0 / 10.0 = 0.6
    inference.update("budget_reserve", budget.reserve_channel())
    current_value, _ = inference.current("budget_reserve")  # type: ignore[misc]

    assert current_value > threshold  # not in danger yet, by the current-value reading alone

    pressure = forecaster.anticipatory_pressure("budget_reserve", threshold=threshold)
    assert pressure > 0.0  # but the forecaster already sees the crossing coming


@pytest.mark.asyncio
async def test_termination_gate_refuses_when_unconfigured(tmp_settings: Settings) -> None:
    """`allow_actual_termination` defaults False -- fire() must refuse and
    must not write any log_event row."""
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    log_sink = LogSink(daemon.conn)
    gate = TerminationGate(tmp_settings.viability, log_sink)

    with pytest.raises(TerminationRefused):
        await gate.fire(daemon.session_id, tick_id=0, reason="reserve depleted")

    cursor = await daemon.conn.execute(
        "SELECT COUNT(*) FROM log_event WHERE event_type = 'termination_fired'"
    )
    (count,) = await cursor.fetchone()  # type: ignore[misc]
    assert count == 0

    await daemon.stop()


@pytest.mark.asyncio
async def test_termination_gate_fires_and_logs_when_configured(tmp_settings: Settings) -> None:
    """With both `allow_actual_termination` and `termination_justification`
    set, fire() must succeed and write a permanent log_event row before the
    caller halts the daemon."""
    tmp_settings.viability.allow_actual_termination = True
    tmp_settings.viability.termination_justification = "test: reserve permanently exhausted"
    daemon = TeicDaemon(tmp_settings)
    await daemon.start()
    await daemon.run_n_ticks(1)
    log_sink = LogSink(daemon.conn)
    gate = TerminationGate(tmp_settings.viability, log_sink)

    await gate.fire(daemon.session_id, tick_id=1, reason="reserve depleted")

    cursor = await daemon.conn.execute(
        "SELECT session_id, event_type, payload FROM log_event WHERE event_type = 'termination_fired'"
    )
    row = await cursor.fetchone()
    assert row is not None
    session_id, event_type, payload = row
    assert session_id == daemon.session_id
    assert event_type == "termination_fired"
    assert "test: reserve permanently exhausted" in payload

    await daemon.stop()
