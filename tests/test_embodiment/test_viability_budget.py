from __future__ import annotations

from teic.embodiment.viability_budget import ViabilityBudget
from teic.settings import ViabilitySettings


def _settings(**overrides: float) -> ViabilitySettings:
    return ViabilitySettings(**overrides)


def test_reserve_starts_at_monthly_budget() -> None:
    budget = ViabilityBudget(_settings(monthly_budget_usd=10.0))
    assert budget.reserve_usd == 10.0
    assert budget.reserve_channel() == 1.0


def test_spend_depletes_reserve_from_real_cost() -> None:
    budget = ViabilityBudget(_settings(monthly_budget_usd=10.0))
    budget.spend(3.0)
    assert budget.reserve_usd == 7.0
    assert budget.reserve_channel() == 0.7


def test_spend_never_drives_reserve_negative() -> None:
    budget = ViabilityBudget(_settings(monthly_budget_usd=1.0))
    budget.spend(5.0)
    assert budget.reserve_usd == 0.0
    assert budget.reserve_channel() == 0.0


def test_burn_rate_channel_normalizes_last_spend() -> None:
    budget = ViabilityBudget(_settings(monthly_budget_usd=10.0, max_burn_rate_usd_per_tick=0.5))
    budget.spend(0.25)
    assert budget.burn_rate_channel() == 0.5
    budget.spend(1.0)  # exceeds the per-tick cap
    assert budget.burn_rate_channel() == 1.0


def test_reserve_does_not_recover_without_explicit_replenish() -> None:
    budget = ViabilityBudget(_settings(monthly_budget_usd=10.0))
    budget.spend(4.0)
    reserve_after_spend = budget.reserve_usd
    # Repeated spend() calls with zero cost (standing in for ticks where no
    # LLM call happened) must never silently top the reserve back up.
    budget.spend(0.0)
    budget.spend(0.0)
    assert budget.reserve_usd == reserve_after_spend


def test_replenish_is_the_only_path_that_restores_reserve() -> None:
    budget = ViabilityBudget(_settings(monthly_budget_usd=10.0, replenishment_amount_usd=2.0))
    budget.spend(6.0)
    assert budget.reserve_usd == 4.0
    new_reserve = budget.replenish()
    assert new_reserve == 6.0
    assert budget.reserve_usd == 6.0
