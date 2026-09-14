"""Token/cost accounting against the viability budget.

Pricing is fetched once from OpenRouter's GET /models and cached to
data/pricing_cache.json. If OpenRouter is unreachable at startup, the daemon
boots in degraded mode using the last cached pricing (or zero-cost estimates
with a WARN log if no cache exists yet) rather than blocking startup -- see
PLAN.md risk #3.
"""

from __future__ import annotations

import json
from pathlib import Path

import httpx

DEFAULT_CACHE_PATH = Path("data/pricing_cache.json")


class PricingCache:
    def __init__(self, cache_path: str | Path = DEFAULT_CACHE_PATH) -> None:
        self._cache_path = Path(cache_path)
        self._prices: dict[str, dict[str, float]] = {}

    def load_from_disk(self) -> bool:
        if not self._cache_path.exists():
            return False
        self._prices = json.loads(self._cache_path.read_text())
        return True

    def save_to_disk(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(json.dumps(self._prices))

    async def refresh(self, client: httpx.AsyncClient, base_url: str) -> bool:
        """Best-effort refresh from OpenRouter's model catalog. Returns True on success."""
        try:
            resp = await client.get(f"{base_url}/models", timeout=10.0)
            resp.raise_for_status()
        except httpx.HTTPError:
            return False
        data = resp.json().get("data", [])
        prices: dict[str, dict[str, float]] = {}
        for model in data:
            pricing = model.get("pricing", {})
            prices[model["id"]] = {
                "prompt": float(pricing.get("prompt", 0.0)),
                "completion": float(pricing.get("completion", 0.0)),
            }
        self._prices = prices
        self.save_to_disk()
        return True

    def estimate_cost_usd(
        self, model: str, prompt_tokens: int, completion_tokens: int
    ) -> float:
        price = self._prices.get(model)
        if price is None:
            return 0.0
        return prompt_tokens * price["prompt"] + completion_tokens * price["completion"]
