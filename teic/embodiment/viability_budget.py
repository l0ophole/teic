"""Phase 6's precariousness ledger.

Depletes `reserve_usd` from real per-call LLM spend (an amount the caller
computes via `teic.llm.cost.PricingCache.estimate_cost_usd`, threaded in
through `spend()` -- this module doesn't call OpenRouter or the pricing
cache itself, it just accounts for what already happened), never a
synthetic per-tick decay. Replenishment is a separate, explicit method:
nothing in this class calls it automatically, so restoring the reserve
requires a real effector action to invoke `replenish()` -- the concrete
mechanism behind "replenishment requires action, not a silent top-up."
"""

from __future__ import annotations

from teic.settings import ViabilitySettings


class ViabilityBudget:
    """Per-session ledger. `reserve_usd` starts at
    `settings.monthly_budget_usd` and only ever moves via `spend()` (real
    LLM cost) or `replenish()` (explicit effector action)."""

    def __init__(self, settings: ViabilitySettings) -> None:
        self._settings = settings
        self.reserve_usd = settings.monthly_budget_usd
        self.last_spend_usd = 0.0

    def spend(self, cost_usd: float) -> None:
        assert cost_usd >= 0.0, "cost_usd must be non-negative"
        self.reserve_usd = max(0.0, self.reserve_usd - cost_usd)
        self.last_spend_usd = cost_usd

    def replenish(self) -> float:
        """Explicit effector action: adds `replenishment_amount_usd` to the
        reserve and returns the new reserve. Only a real effector
        invocation (a workspace-arbitrated action, wired in cp3) should
        reach this -- the tick loop never calls it on its own."""
        self.reserve_usd += self._settings.replenishment_amount_usd
        return self.reserve_usd

    def reserve_channel(self) -> float:
        """Normalizes `reserve_usd` into the RegisterState `budget_reserve`
        channel's 0..1 scale (1.0 = full reserve, 0.0 = depleted)."""
        if self._settings.monthly_budget_usd <= 0.0:
            return 0.0
        return min(self.reserve_usd / self._settings.monthly_budget_usd, 1.0)

    def burn_rate_channel(self) -> float:
        """Normalizes the most recent `spend()` call's real cost into the
        RegisterState `burn_rate` channel's 0..1 scale, against the
        configured `max_burn_rate_usd_per_tick` depletion-rate parameter."""
        if self._settings.max_burn_rate_usd_per_tick <= 0.0:
            return 0.0
        return min(self.last_spend_usd / self._settings.max_burn_rate_usd_per_tick, 1.0)
